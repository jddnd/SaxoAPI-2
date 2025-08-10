import os
import requests
import yaml
from datetime import datetime, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential

class SaxoClient:
    def __init__(self, config_path="config.yaml"):
        self.config_path = config_path
        self._load_config()
        self.base_url = self.config["saxo"]["base_url"]
        self.client_id = self.config["saxo"]["client_id"]
        self.client_secret = self.config["saxo"]["client_secret"]
        self.redirect_uri = self.config["saxo"]["redirect_uri"]
        self.access_token = self.config["saxo"]["access_token"]
        self.refresh_token = self.config["saxo"]["refresh_token"]
        self.account_key = self.config["saxo"]["account_key"]

    def _load_config(self):
        with open(self.config_path, "r") as f:
            self.config = yaml.safe_load(f)

    def _save_config(self):
        with open(self.config_path, "w") as f:
            yaml.safe_dump(self.config, f)

    def _refresh_access_token(self):
        print("Refreshing Saxo access token...")
        url = f"{self.base_url}/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "redirect_uri": self.redirect_uri
        }
        auth = (self.client_id, self.client_secret)
        resp = requests.post(url, data=data, auth=auth)
        if resp.status_code != 200:
            raise Exception(f"Token refresh failed: {resp.text}")
        tokens = resp.json()
        self.access_token = tokens["access_token"]
        self.refresh_token = tokens["refresh_token"]
        self.config["saxo"]["access_token"] = self.access_token
        self.config["saxo"]["refresh_token"] = self.refresh_token
        self._save_config()
        print("Token refreshed and saved.")

    def _auth_headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    def _request(self, method, endpoint, **kwargs):
        url = f"{self.base_url}{endpoint}"
        resp = requests.request(method, url, headers=self._auth_headers(), **kwargs)
        if resp.status_code == 401:
            self._refresh_access_token()
            kwargs["headers"] = self._auth_headers()
            resp = requests.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def get_account_key(self):
        if self.account_key:
            return self.account_key
        data = self._request("GET", "/port/v1/accounts/me")
        if "Data" in data and len(data["Data"]) > 0:
            self.account_key = data["Data"][0]["AccountKey"]
            self.config["saxo"]["account_key"] = self.account_key
            self._save_config()
            return self.account_key
        raise Exception("No account key found")

    def get_option_chain(self, symbol):
        return self._request("GET", f"/ref/v1/instruments/contractoptionspaces/{symbol}?OptionSpaceSegment=All")

    def place_option_order(self, uic, expiry, strike, call_put, qty):
        account_key = self.get_account_key()
        order = {
            "AccountKey": account_key,
            "AssetType": "StockOption",
            "BuySell": "Buy",
            "OrderType": "Market",
            "Amount": qty,
            "Uic": uic,
            "StrikePrice": strike,
            "ExpiryDate": expiry,
            "PutCall": call_put
        }
        return self._request("POST", "/trade/v2/orders", json=order)
