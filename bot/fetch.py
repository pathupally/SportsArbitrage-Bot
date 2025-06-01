import os
import requests
import pandas as pd
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional, Tuple
import time

# Load environment variables (e.g. ODDS_API_KEY) from a .env file.
load_dotenv()


class ArbitrageCalculator:
    """
    A helper class to compute arbitrage opportunities given a list of odds dictionaries.
    Arbitrage betting (or "surebet") is a risk-free strategy where the sum of the reciprocals of the odds (in decimal) is less than 1.
    """

    @staticmethod
    def compute_arbitrage(odds_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Compute arbitrage opportunity (if any) from a list of odds dictionaries.
        Each dict is expected to have keys: 'sport', 'home_team', 'away_team', 'bookmaker', 'home_odds', 'away_odds'.
        Returns a dict with arbitrage details (sport, home_team, away_team, home_bookmaker, away_bookmaker, home_odds, away_odds, profit_percent) if an arbitrage is found, else None.
        """
        if not odds_list:
            return None

        # Group odds by sport, home_team, away_team (i.e. by event) so that we compare odds for the same event.
        event_odds: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
        for odd in odds_list:
            key = (odd["sport"], odd["home_team"], odd["away_team"])
            if key not in event_odds:
                event_odds[key] = []
            event_odds[key].append(odd)

        arbitrage_opportunities = []
        for (sport, home, away), odds_group in event_odds.items():
            # For each event, compare home_odds (from one bookmaker) and away_odds (from another bookmaker).
            for i, odd1 in enumerate(odds_group):
                for odd2 in odds_group[i + 1:]:
                    # odd1: home_odds (decimal) from bookmaker odd1["bookmaker"]
                    # odd2: away_odds (decimal) from bookmaker odd2["bookmaker"]
                    home_odds = odd1["home_odds"]
                    away_odds = odd2["away_odds"]
                    # Arbitrage exists if (1/home_odds + 1/away_odds) < 1.
                    arb_sum = (1.0 / home_odds) + (1.0 / away_odds)
                    if arb_sum < 1.0:
                        profit_percent = (1.0 / arb_sum - 1.0) * 100.0
                        arb_dict = {
                            "sport": sport,
                            "home_team": home,
                            "away_team": away,
                            "home_bookmaker": odd1["bookmaker"],
                            "away_bookmaker": odd2["bookmaker"],
                            "home_odds": home_odds,
                            "away_odds": away_odds,
                            "profit_percent": profit_percent
                        }
                        arbitrage_opportunities.append(arb_dict)

        if arbitrage_opportunities:
            # Arbitrarily return the first arbitrage opportunity found.
            return arbitrage_opportunities[0]
        else:
            return None


class Fetch:
    """
    A class to fetch sports and odds from the Odds API, compute arbitrage opportunities (using ArbitrageCalculator),
    and save the results into a CSV file. It uses caching (via a class variable) to reduce the number of requests sent.
    """

    # Class variable to cache sports (so that fetch_sports() is called only once per session).
    _cached_sports: Optional[List[str]] = None

    def __init__(self):
        self.api_key = os.getenv("ODDS_API_KEY")
        if not self.api_key:
            raise ValueError("ODDS_API_KEY not found in environment variables.")
        self.sports_url = "https://api.the-odds-api.com/v4/sports"
        self.odds_url = "https://api.the-odds-api.com/v4/sports/{sport}/odds/?apiKey={apiKey}&regions=us,us2"
        # A list to store raw odds data (each entry is a dict with keys: sport, home_team, away_team, bookmaker, home_odds, away_odds).
        self.odds_data: List[Dict[str, Any]] = []

    def fetch_sports(self) -> List[str]:
        """
        Fetches a list of available sports (keys) from the Odds API.
        Uses a class-level cache (_cached_sports) to avoid repeated requests.
        """
        if Fetch._cached_sports is not None:
            return Fetch._cached_sports

        sports = []
        try:
            response = requests.get(f"{self.sports_url}?api_key={self.api_key}")
            if response.status_code == 200:
                for sport in response.json():
                    sports.append(sport["key"])
                Fetch._cached_sports = sports
            else:
                print(f"Error fetching sports: status code {response.status_code}.")
        except requests.exceptions.RequestException as e:
            print(f"Request error fetching sports: {e}.")
        except Exception as e:
            print(f"Unexpected error fetching sports: {e}.")
        return sports

    def fetch_odds(self, sport: str) -> None:
        """
        Fetches odds for a given sport from the Odds API and appends the parsed odds (home/away) into self.odds_data.
        """
        url = self.odds_url.format(sport=sport, apiKey=self.api_key)
        try:
            response = requests.get(url)
            if response.status_code != 200:
                print(f"Error fetching odds for sport {sport}: status code {response.status_code}.")
                return
            data = response.json()
            for game in data:
                home_team = game.get("home_team", "N/A")
                away_team = game.get("away_team", "N/A")
                for book in game.get("bookmakers", []):
                    bookmaker = book.get("key", "N/A")
                    for market in book.get("markets", []):
                        if market.get("key") == "h2h":
                            for outcome in market.get("outcomes", []):
                                if outcome.get("name") == home_team:
                                    home_odds = outcome.get("price", 0.0)
                                elif outcome.get("name") == away_team:
                                    away_odds = outcome.get("price", 0.0)
                            # Append a dict with keys: sport, home_team, away_team, bookmaker, home_odds, away_odds.
                            self.odds_data.append({
                                "sport": sport,
                                "home_team": home_team,
                                "away_team": away_team,
                                "bookmaker": bookmaker,
                                "home_odds": home_odds,
                                "away_odds": away_odds
                            })
        except requests.exceptions.RequestException as e:
            print(f"Request error fetching odds for sport {sport}: {e}.")
        except Exception as e:
            print(f"Unexpected error fetching odds for sport {sport}: {e}.")

    def run(self) -> None:
        """
        Main method to orchestrate the arbitrage bot:
        1. Fetch sports (using caching to reduce requests).
        2. Fetch odds for each sport (and append into self.odds_data).
        3. Compute arbitrage opportunities (using ArbitrageCalculator).
        4. Save arbitrage opportunities (if any) into a CSV file (arbitrage_opportunities.csv).
        """
        print("Arbitrage bot is starting...")
        sports = self.fetch_sports()
        if not sports:
            print("No sports data available. Exiting.")
            return

        for sport in sports:
            print(f"Fetching odds for sport: {sport}...")
            self.fetch_odds(sport)
            # Sleep a little to avoid hitting rate limits (if any) on the API.
            time.sleep(0.5)

        print("Computing arbitrage opportunities...")
        arb_calc = ArbitrageCalculator()
        arb_opportunities = []
        # Arbitrarily, we compute arbitrage for the first 1000 odds (or less) to avoid an infinite loop.
        for odd in self.odds_data[:1000]:
            arb = arb_calc.compute_arbitrage([odd])
            if arb:
                arb_opportunities.append(arb)

        if arb_opportunities:
            df = pd.DataFrame(arb_opportunities)
            df.to_csv("arbitrage_opportunities.csv", index=False)
            print("Arbitrage opportunities saved into arbitrage_opportunities.csv.")
        else:
            print("No arbitrage opportunity found.")



