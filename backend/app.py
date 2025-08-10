from typing import Optional, List
import os
import yaml
from fastapi import FastAPI, HTTPException, Body, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from saxo_client import SaxoClient
from strategies import PLANS
from utils import pct_spread

app = FastAPI(title="Saxo Auto Trader (Options)")

# Serve React frontend
app.mount("/", StaticFiles(directory="../frontend/build", html=True), name="static")

# Add CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update to your Render URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Config ----
CFG = {}
config_path = os.getenv("CONFIG_PATH", "config.yaml")
if os.path.exists(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        CFG = yaml.safe_load(f) or {}

CFG.setdefault("saxo", {})
CFG["saxo"]["access_token"] = os.getenv("SAXO_ACCESS_TOKEN", CFG["saxo"].get("access_token", ""))
CFG["saxo"]["refresh_token"] = os.getenv("SAXO_REFRESH_TOKEN", CFG["saxo"].get("refresh_token", ""))
CFG["saxo"]["account_key"] = os.getenv("SAXO_ACCOUNT_KEY", CFG["saxo"].get("account_key", ""))
CFG["saxo"]["base_url"] = os.getenv("SAXO_BASE_URL", CFG["saxo"].get("base_url", "https://gateway.saxobank.com/sim/openapi"))
CFG["saxo"]["client_id"] = os.getenv("SAXO_CLIENT_ID", CFG["saxo"].get("client_id", ""))
CFG["saxo"]["client_secret"] = os.getenv("SAXO_CLIENT_SECRET", CFG["saxo"].get("client_secret", ""))
CFG["saxo"]["redirect_uri"] = os.getenv("SAXO_REDIRECT_URI", CFG["saxo"].get("redirect_uri", "http://localhost/callback"))

CFG.setdefault("risk", {})
CFG["risk"].setdefault("max_spread_pct", float(os.getenv("MAX_SPREAD_PCT", 0.5)))
CFG["risk"].setdefault("default_qty", int(os.getenv("DEFAULT_QTY", 1)))

CFG.setdefault("security", {})
TV_SECRET = os.getenv("TV_SHARED_SECRET", CFG["security"].get("tv_shared_secret", ""))

saxo = SaxoClient(CFG)

# ---- Models ----
class Signal(BaseModel):
    symbol: str
    price: Optional[float] = None
    rule: Optional[str] = None
    first30Green: Optional[bool] = None
    volumeStrong: Optional[bool] = None
    BTC: Optional[float] = None
    GOLD: Optional[float] = None
    date: Optional[str] = None

class TVAlert(BaseModel):
    ticker: Optional[str] = None
    price: Optional[float] = None
    close: Optional[float] = None
    rule: Optional[str] = None
    BTC: Optional[float] = None
    GOLD: Optional[float] = None
    volumeStrong: Optional[bool] = None
    first30Green: Optional[bool] = None
    date: Optional[str] = None
    secret: Optional[str] = None

# ---- Helpers ----
def condition_met(plan, sig: Signal) -> bool:
    r = plan.entry_condition
    p = sig.price or 0.0
    if r == "price>=190":
        return p >= 190.0
    if r == "price>=430":
        return p >= 430.0
    if r == "price>=540":
        return p >= 540.0
    if r == "price>=75 AND volume_strong":
        return (p >= 75.0) and bool(sig.volumeStrong)
    if r == "date==2025-08-14 AND price>=76":
        return (sig.date == "2025-08-14") and (p >= 76.0)
    if r == "open>=7 AND first30_green":
        return (p >= 7.0) and bool(sig.first30Green)
    if r == "close>7.25":
        return (p > 7.25)
    if r == "dip_to_52_53":
        return 52.0 <= p <= 53.0
    if r == "pullback_to_13_2_13_4":
        return 13.2 <= p <= 13.4
    if r == "BTC>74500":
        return (sig.BTC or 0.0) > 74500.0
    if r == "GOLD>2500":
        return (sig.GOLD or 0.0) > 2500.0
    return False

def lazy_account_key() -> Optional[str]:
    try:
        return saxo.ensure_account_key()
    except Exception:
        return None

def _check_secret(x_webhook_token: Optional[str], body_secret: Optional[str]):
    if not TV_SECRET:
        return True
    if x_webhook_token == TV_SECRET:
        return True
    if body_secret == TV_SECRET:
        return True
    raise HTTPException(status_code=401, detail="Invalid or missing webhook secret.")

def _tv_to_signal(tv: TVAlert) -> Signal:
    sym = (tv.ticker or "").split(":")[-1] if tv.ticker else ""
    px = tv.price if tv.price is not None else tv.close
    return Signal(
        symbol=sym,
        price=px,
        rule=tv.rule,
        BTC=tv.BTC,
        GOLD=tv.GOLD,
        volumeStrong=tv.volumeStrong,
        first30Green=tv.first30Green,
        date=tv.date
    )

# ---- Routes ----
@app.get("/health")
def health():
    return {"ok": True}

@app.post("/signal")
def receive_signal(sig: Signal):
    matches = [pl for pl in PLANS if pl.underlying_keywords.upper() == sig.symbol.upper()]
    if not matches:
        raise HTTPException(status_code=404, detail=f"No strategy for symbol {sig.symbol}")

    executed = []
    for plan in matches:
        if not condition_met(plan, sig):
            continue

        account_key = lazy_account_key()
        if not account_key:
            raise HTTPException(
                status_code=401,
                detail="Saxo token invalid or expired. Update SAXO_ACCESS_TOKEN env var or config.yaml."
            )

        try:
            opt = saxo.find_option_uic(plan.underlying_keywords, plan.expiry_iso, plan.strike, plan.put_call)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"UIC lookup failed: {e}")

        try:
            snap = saxo.info_prices(opt["Uic"], opt["AssetType"], amount=1)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Price snapshot failed: {e}")

        quote = (snap or {}).get("Quote", {})
        bid, ask = quote.get("Bid"), quote.get("Ask")
        spread = pct_spread(bid, ask)
        max_spread = CFG["risk"]["max_spread_pct"]
        if spread is None or spread > max_spread:
            raise HTTPException(
                status_code=409,
                detail=f"Spread too wide ({spread}); aborting order. Tighten the strike or adjust MAX_SPREAD_PCT."
            )

        try:
            res = saxo.place_option_order_bracket(
                account_key,
                opt["Uic"],
                opt["AssetType"],
                CFG["risk"]["default_qty"],
                tp_pct=plan.tp_pct,
                sl_pct=plan.sl_pct,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Order placement failed: {e}")

        executed.append({"plan": plan.__dict__, "orderResponse": res})

    if not executed:
        return {"status": "ignored", "reason": "no conditions met"}
    return {"status": "ok", "executed": executed}

@app.post("/tv")
def tv_webhook(tv: TVAlert, x_webhook_token: Optional[str] = Header(default=None)):
    _check_secret(x_webhook_token, tv.secret)
    sig = _tv_to_signal(tv)
    if not sig.symbol:
        raise HTTPException(status_code=400, detail="Missing symbol/ticker in payload.")
    return receive_signal(sig)

@app.get("/debug/instrument")
def debug_instrument(symbol: str):
    data = saxo.search_instruments(symbol)
    out = []
    for it in data.get("Data", []):
        try:
            det = saxo.instrument_details(it["Identifier"], it["AssetType"])
            roots = det.get("RelatedOptionRootsEnhanced") or det.get("RelatedOptionRoots") or []
            out.append({
                "Identifier": it["Identifier"],
                "Symbol": it.get("Symbol"),
                "Description": it.get("Description"),
                "AssetType": it.get("AssetType"),
                "ExchangeId": it.get("ExchangeId"),
                "HasOptionRoots": bool(roots),
                "RootCount": len(roots)
            })
        except Exception as e:
            out.append({"Identifier": it.get("Identifier"), "error": str(e)})
    return {"results": out}

@app.get("/debug/option_space")
def debug_option_space(symbol: str, expiry: str):
    search = saxo.search_instruments(symbol)
    for it in search.get("Data", []):
        try:
            det = saxo.instrument_details(it["Identifier"], it["AssetType"])
            roots = det.get("RelatedOptionRootsEnhanced") or det.get("RelatedOptionRoots") or []
            if not roots:
                continue
            root_id = roots[0].get("OptionRootId") or roots[0].get("Id") or roots[0]
            space = saxo.option_space(root_id, underlying_uic=it["Identifier"], expiry_dates=expiry)
            return {"instrument": it, "space": space}
        except Exception:
            continue
    return {"error": "No option roots / space found for symbol"}

@app.post("/debug/bulk_roots")
def debug_bulk_roots(symbols: List[str] = Body(..., embed=True)):
    results = []
    for s in symbols:
        try:
            data = saxo.search_instruments(s)
            has_any = False
            rows = []
            for it in data.get("Data", []):
                try:
                    det = saxo.instrument_details(it["Identifier"], it["AssetType"])
                    roots = det.get("RelatedOptionRootsEnhanced") or det.get("RelatedOptionRoots") or []
                    row = {
                        "SymbolQuery": s,
                        "Identifier": it["Identifier"],
                        "Symbol": it.get("Symbol"),
                        "Description": it.get("Description"),
                        "AssetType": it.get("AssetType"),
                        "ExchangeId": it.get("ExchangeId"),
                        "HasOptionRoots": bool(roots),
                        "RootCount": len(roots),
                    }
                    if roots:
                        has_any = True
                    rows.append(row)
                except Exception as e:
                    rows.append({"SymbolQuery": s, "Identifier": it.get("Identifier"), "Error": str(e)})
            results.append({"query": s, "hasAnyRoots": has_any, "candidates": rows})
        except Exception as e:
            results.append({"query": s, "error": str(e)})
    return {"results": results}