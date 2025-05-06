import requests
from datetime import datetime, timezone
import schedule
import time
import logging
import json
from typing import Dict, List, Optional
import signal
import sys
import argparse
import csv
from tabulate import tabulate
from supabase import create_client, Client
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('blowout_checker.log'),
        logging.StreamHandler()
    ]
)

# Configuration
CONFIG = {
    'RUN_THRESHOLD': 5,  # Minimum run difference for a blowout
    'SCHEDULE_TIME': '02:00',  # Time to run the check
    'MLB_API_URL': 'https://statsapi.mlb.com/api/v1/schedule',
    'SPORT_ID': 1
}

class BlowoutChecker:
    def __init__(self):
        self.running = True
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)
        
        # Initialize Supabase client
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        if not supabase_url or not supabase_key:
            raise ValueError("Missing Supabase credentials. Please set SUPABASE_URL and SUPABASE_KEY environment variables.")
        self.supabase: Client = create_client(supabase_url, supabase_key)

    def _handle_exit(self, signum, frame):
        logging.info("Received exit signal. Shutting down...")
        self.running = False

    def update_supabase(self, game_data: Dict):
        """Update Supabase database with game results"""
        try:
            # Prepare the data for Supabase
            data = {
                'game_id': game_data['game_pk'],
                'date': game_data['date'],
                'away_team': game_data['away_team'],
                'home_team': game_data['home_team'],
                'away_score': game_data['away_score'],
                'home_score': game_data['home_score'],
                'is_blowout': game_data['is_blowout'],
                'through_6_lead': game_data['analysis'].get('through_6_lead', None),
                'maintained_lead': game_data['analysis'].get('maintained_lead', None),
                'status': game_data['status'],
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            # Upsert the data (insert if not exists, update if exists)
            result = self.supabase.table('mlb_blowouts').upsert(data).execute()
            
            if hasattr(result, 'error') and result.error:
                logging.error(f"Error updating Supabase: {result.error}")
            else:
                logging.info(f"Successfully updated Supabase for game {game_data['game_pk']}")

        except Exception as e:
            logging.error(f"Error updating Supabase: {str(e)}")

    def fetch_schedule(self, date: str) -> Optional[Dict]:
        try:
            response = requests.get(
                CONFIG['MLB_API_URL'],
                params={
                    'sportId': CONFIG['SPORT_ID'],
                    'date': date
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            logging.debug(f"Raw API response for {date}: {json.dumps(data, indent=2)}")
            return data
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching schedule: {e}")
            return None

    def fetch_game_data(self, game_pk: str) -> Optional[Dict]:
        try:
            url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching game data: {e}")
            return None

    def is_blowout(self, game: Dict) -> tuple[bool, Dict]:
        try:
            linescore = game.get("linescore", {})
            innings = linescore.get("innings", [])
            
            if not innings:
                return False, {}

            # Compute cumulative runs through 6th inning
            cum_home = sum(i.get("home", {}).get("runs", 0) for i in innings[:6])
            cum_away = sum(i.get("away", {}).get("runs", 0) for i in innings[:6])
            
            # Store the analysis details
            analysis = {
                "through_6_home": cum_home,
                "through_6_away": cum_away,
                "through_6_lead": abs(cum_home - cum_away),
                "maintained_lead": True
            }
            
            # If lead is < threshold, it's not a blowout
            if abs(cum_home - cum_away) < CONFIG['RUN_THRESHOLD']:
                return False, analysis

            # Check if cushion never dips below threshold
            for inning in innings[6:]:
                cum_home += inning.get("home", {}).get("runs", 0)
                cum_away += inning.get("away", {}).get("runs", 0)
                if abs(cum_home - cum_away) < CONFIG['RUN_THRESHOLD']:
                    analysis["maintained_lead"] = False
                    return False, analysis

            return True, analysis
        except (KeyError, TypeError) as e:
            logging.error(f"Error processing game data: {e}")
            return False, {}

    def check_blowouts(self, date: Optional[str] = None):
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        logging.info(f"Checking for blowouts on {date}")
        
        data = self.fetch_schedule(date)
        if not data:
            logging.error("No data received from API")
            return

        dates = data.get("dates", [])
        if not dates:
            logging.error(f"No dates found in API response for {date}")
            return

        games = dates[0].get("games", [])
        if not games:
            logging.info(f"No games scheduled for {date}")
            return

        logging.info(f"Found {len(games)} games to check")
        game_results = []
        
        for game in games:
            game_pk = game.get("gamePk")
            if not game_pk:
                continue

            # Get team names and scores
            away_team = game.get("teams", {}).get("away", {}).get("team", {}).get("name", "Unknown")
            home_team = game.get("teams", {}).get("home", {}).get("team", {}).get("name", "Unknown")
            away_score = game.get("teams", {}).get("away", {}).get("score", 0)
            home_score = game.get("teams", {}).get("home", {}).get("score", 0)
            
            # Skip games that haven't finished
            status = game.get("status", {}).get("codedGameState")
            if status != "F":  # F means Final
                game_data = {
                    "game_pk": game_pk,
                    "date": date,
                    "away_team": away_team,
                    "home_team": home_team,
                    "away_score": away_score,
                    "home_score": home_score,
                    "status": "In Progress",
                    "is_blowout": False,
                    "analysis": {}
                }
                self.update_supabase(game_data)
                continue

            # Fetch detailed game data
            detailed_data = self.fetch_game_data(game_pk)
            if not detailed_data:
                continue

            # Update game data with linescore
            game["linescore"] = detailed_data.get("liveData", {}).get("linescore", {})
            
            # Check if it's a blowout
            is_blowout, analysis = self.is_blowout(game)
            
            game_data = {
                "game_pk": game_pk,
                "date": date,
                "away_team": away_team,
                "home_team": home_team,
                "away_score": away_score,
                "home_score": home_score,
                "status": "Final",
                "is_blowout": is_blowout,
                "analysis": analysis
            }
            
            # Update Supabase
            self.update_supabase(game_data)
            game_results.append(game_data)

        # Display results in a table
        table_data = []
        for result in game_results:
            status_symbol = "✓" if result["is_blowout"] else "✗" if result["status"] == "Final" else "⋯"
            table_data.append([
                f"{result['away_team']} @ {result['home_team']}",
                f"{result['away_score']}-{result['home_score']}",
                result["status"],
                status_symbol
            ])

        print(f"\nResults for {date}:")
        print(tabulate(table_data, headers=["Game", "Score", "Status", "Blowout"], tablefmt="grid"))

    def run(self, date: Optional[str] = None):
        if date:
            # If a specific date is provided, just check that date and exit
            self.check_blowouts(date)
            return
        
        # Otherwise, run on schedule
        schedule.every().day.at(CONFIG['SCHEDULE_TIME']).do(self.check_blowouts)
        
        # Run immediately on startup
        self.check_blowouts()
        
        logging.info(f"Blowout checker started. Will run daily at {CONFIG['SCHEDULE_TIME']}")
        while self.running:
            schedule.run_pending()
            time.sleep(1)  # Check every second instead of every minute

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Check MLB games for blowouts')
    parser.add_argument('--date', type=str, help='Check specific date (YYYY-MM-DD)')
    args = parser.parse_args()
    
    checker = BlowoutChecker()
    checker.run(args.date)