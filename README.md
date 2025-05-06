# MLB Blowout Checker

A Python script that monitors MLB games and identifies blowouts based on run differentials. The script tracks games throughout the season and stores the results in a Supabase database.

## Features

- Monitors MLB games in real-time
- Identifies blowouts based on run differentials after 6 innings
- Stores game data and blowout analysis in Supabase
- Generates CSV reports of blowout games
- Scheduled daily checks for game results

## Requirements

- Python 3.7+
- Required packages:
  - requests
  - schedule
  - supabase
  - python-dotenv
  - tabulate

## Installation

1. Clone the repository:
```bash
git clone [your-repo-url]
cd mlb-blowout-check
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with your Supabase credentials:
```
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
```

## Usage

Run the script:
```bash
python mlb_blowout.py
```

To check a specific date:
```bash
python mlb_blowout.py --date YYYY-MM-DD
```

## Configuration

The script can be configured by modifying the `CONFIG` dictionary in `mlb_blowout.py`:

- `RUN_THRESHOLD`: Minimum run difference for a blowout (default: 5)
- `SCHEDULE_TIME`: Time to run the daily check (default: "02:00")
- `MLB_API_URL`: MLB Stats API endpoint
- `SPORT_ID`: MLB sport ID (1)

## Database Schema

The script stores data in a Supabase table with the following structure:

- `game_id`: Unique game identifier
- `date`: Game date
- `away_team`: Away team name
- `home_team`: Home team name
- `away_score`: Away team score
- `home_score`: Home team score
- `is_blowout`: Blowout status
- `through_6_lead`: Run difference after 6 innings
- `maintained_lead`: Whether lead was maintained
- `status`: Game status
- `updated_at`: Last update timestamp

## License

[Your chosen license] 