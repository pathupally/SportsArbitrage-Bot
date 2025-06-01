# Import Fetch from the local module (using a relative import) so that the Fetch class (from fetch.py) is used.
from .fetch import Fetch

def main():
    """
    Main entry point for the arbitrage bot. It instantiates a Fetch object and calls its run() method.
    """
    print("Arbitrage bot is starting...")
    bot = Fetch()
    bot.run()

if __name__ == "__main__":
    main()