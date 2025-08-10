# oauth_refresh_token.py
import requests
import yaml
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "config.yaml"

def refresh_token():
    with open(CONFIG_FILE, "r") as f:
        config = yaml.safe_load(f)

    client_id = config["saxo"]["client_id"]
    client_secret = config["saxo"]["client_secret"]
    refresh_token = config["saxo"]["refresh_token"]

    url = "https://sim.logonvalidation.net/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret
    }

    r = requests.post(url, data=data)
    if r.status_code != 200:
        print(f"Error refreshing token: {r.status_code} {r.text}")
        return

    tokens = r.json()
    access_token = tokens.get("access_token")
    refresh_token_new = tokens.get("refresh_token", refresh_token)
    expires_in = tokens.get("expires_in")

    # Update config.yaml
    config["saxo"]["access_token"] = access_token
    config["saxo"]["refresh_token"] = refresh_token_new
    with open(CONFIG_FILE, "w") as f:
        yaml.safe_dump(config, f)

    print("✅ Token refreshed successfully")
    print(f"access_token: {access_token[:40]}... (len={len(access_token)})")
    print(f"expires_in: {expires_in} seconds")

if __name__ == "__main__":
    refresh_token()
