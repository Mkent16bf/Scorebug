from flask import Flask, jsonify, render_template
from flask_cors import CORS
import requests
import threading
import time
from datetime import datetime, timedelta

app = Flask(__name__, template_folder='.', static_folder='.')
CORS(app)

# Configuration
BROADCAST_DELAY_SECONDS = 15
POLL_INTERVAL = 10
state_history = []

TEAMS = [
    {"name": "Bills", "url": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"},
    {"name": "Sabres", "url": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"},
    {"name": "Yankees", "url": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"}
]

def fetch_game_data():
    while True:
        game_found = False
        for team in TEAMS:
            try:
                res = requests.get(team["url"]).json()
                for event in res.get("events", []):
                    competitors = event["competitions"][0]["competitors"]
                    team_names = [c["team"]["name"] for c in competitors]
                    
                    if team["name"] in team_names:
                        home = next(c for c in competitors if c["homeAway"] == "home")
                        away = next(c for c in competitors if c["homeAway"] == "away")
                        situation = event["competitions"][0].get("situation", {})
                        
                        payload = {
                            "active": True,
                            "sport": team["name"],
                            "home": {
                                "name": home["team"]["abbreviation"],
                                "score": home.get("score", "0"),
                                "primary_color": home["team"].get("color", "000000"),
                                "timeouts": situation.get("homeTimeouts", 3) if team["name"] == "Bills" else ""
                            },
                            "away": {
                                "name": away["team"]["abbreviation"],
                                "score": away.get("score", "0"),
                                "primary_color": away["team"].get("color", "FFFFFF"),
                                "secondary_color": away["team"].get("alternateColor", "CCCCCC"),
                                "timeouts": situation.get("awayTimeouts", 3) if team["name"] == "Bills" else ""
                            },
                            "down_distance": situation.get("downDistanceText", ""),
                            "field_position": situation.get("possessionText", ""),
                            "last_play": situation.get("lastPlay", {}).get("text", "No recent play"),
                            "possession": situation.get("possession", "")
                        }
                        state_history.append({"time": datetime.now(), "data": payload})
                        game_found = True
                        break
            except Exception as e:
                print(f"Error fetching {team['name']}: {e}")
            if game_found:
                break
                
        if not game_found:
            state_history.append({"time": datetime.now(), "data": {"active": False, "message": "No preferred teams are currently active."}})
            
        # Cleanup old history to prevent memory leak
        if len(state_history) > 30:
            state_history.pop(0)
            
        time.sleep(POLL_INTERVAL)
thread_started = False

@app.before_request
def start_background_thread():
    global thread_started
    if not thread_started:
        threading.Thread(target=fetch_game_data, daemon=True).start()
        thread_started = True
@app.route('/api/score')
def get_score():
    target_time = datetime.now() - timedelta(seconds=BROADCAST_DELAY_SECONDS)
    # Find the closest historical state before the target time
    valid_states = [s for s in state_history if s["time"] <= target_time]
    if valid_states:
        return jsonify(valid_states[-1]["data"])
    return jsonify({"active": False, "message": "Syncing stream..."})

@app.route('/')
def index():
    return render_template('index.html')

# Start the background polling thread so Gunicorn runs it
threading.Thread(target=fetch_game_data, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
