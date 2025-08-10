# oauth_get_tokens.py
import http.server
import socketserver
import threading
import urllib.parse as urlparse
import webbrowser
import requests
import yaml
import os
import sys

AUTH_URL = "https://sim.logonvalidation.net/authorize"
TOKEN_URL = "https://sim.logonvalidation.net/token"

# ----- read config.yaml (for client_id/secret/redirect_uri) -----
CFG_PATH = "config.yaml"
if not os.path.exists(CFG_PATH):
    print("config.yaml not found. Create it with your client_id/client_secret first.")
    sys.exit(1)

with open(CFG_PATH, "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f) or {}

saxo = cfg.get("saxo", {})
client_id = os.getenv("SAXO_CLIENT_ID", saxo.get("client_id", "").strip())
client_secret = os.getenv("SAXO_CLIENT_SECRET", saxo.get("client_secret", "").strip())
redirect_uri = saxo.get("redirect_uri", "http://localhost:8001/callback").strip()

if not client_id or not client_secret:
    print("Missing client_id or client_secret. Put them in config.yaml under saxo:,")
    print("or set env vars SAXO_CLIENT_ID and SAXO_CLIENT_SECRET.")
    sys.exit(1)

# We strongly suggest using http://localhost:8001/callback in the Saxo portal
parsed = urlparse.urlparse(redirect_uri)
if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1"):
    print(f"redirect_uri '{redirect_uri}' must be an http://localhost style URL.")
    sys.exit(1)
host = parsed.hostname
path = parsed.path or "/callback"
port = parsed.port or 80  # if no port specified, it’s 80 (will require admin)

received_code = {"code": None, "error": None}

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed_qs = urlparse.urlparse(self.path)
        if parsed_qs.path != path:
            self.send_response(404); self.end_headers()
            self.wfile.write(b"Not here.")
            return

        qs = urlparse.parse_qs(parsed_qs.query)
        code = qs.get("code", [None])[0]
        error = qs.get("error", [None])[0]
        if error:
            received_code["error"] = error
        else:
            received_code["code"] = code

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h2>Auth received. You can close this tab.</h2>")

def run_server():
    with socketserver.TCPServer((host, port), Handler) as httpd:
        httpd.timeout = 300
        # Serve a single request then stop
        httpd.handle_request()

# Start local listener
srv = threading.Thread(target=run_server, daemon=True)
srv.start()

# Build authorize URL
auth_params = {
    "client_id": client_id,
    "response_type": "code",
    "redirect_uri": redirect_uri,
    "scope": "trade",
}
auth_url = AUTH_URL + "?" + urlparse.urlencode(auth_params)
print("\nOpen this URL to log in (we'll open your browser automatically):")
print(auth_url)
try:
    webbrowser.open(auth_url)
except Exception:
    pass

# Wait for the handler to set code/error (basic loop)
for _ in range(600):  # up to ~60s
    if received_code["code"] or received_code["error"]:
        break
    import time; time.sleep(0.1)

if received_code["error"]:
    print(f"Authorization failed: {received_code['error']}")
    sys.exit(1)

if not received_code["code"]:
    print("No 'code' received. Did you approve the app? Is redirect URL registered in the portal?")
    sys.exit(1)

code = received_code["code"]
print("\nExchanging code for tokens...")

# Token exchange
data = {
    "grant_type": "authorization_code",
    "code": code,
    "redirect_uri": redirect_uri,
    "client_id": client_id,
    "client_secret": client_secret,
}
r = requests.post(TOKEN_URL, data=data)
try:
    r.raise_for_status()
except Exception:
    print("Token exchange failed:")
    print(r.status_code, r.text)
    sys.exit(1)

tok = r.json()
access_token = tok.get("access_token")
refresh_token = tok.get("refresh_token")
expires_in = tok.get("expires_in")

if not access_token:
    print("No access_token returned. Response:")
    print(tok)
    sys.exit(1)

print("\nSUCCESS ✅")
print(f"access_token: {access_token[:40]}... (len={len(access_token)})")
print(f"refresh_token: {str(refresh_token)[:40]}...")
print(f"expires_in: {expires_in}")

# Write back to config.yaml
cfg.setdefault("saxo", {})
cfg["saxo"]["access_token"] = access_token
cfg["saxo"]["refresh_token"] = refresh_token or ""
with open(CFG_PATH, "w", encoding="utf-8") as f:
    yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)

print(f"\nSaved tokens into {CFG_PATH}. Restart your server and you’re good to go.")
