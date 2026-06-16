"""
Swing Trading System — Market Data Fetcher
------------------------------------------
Fetches NSE data via yfinance, calculates 21/50/200 EMA,
writes market_data.json (read by dashboard + Claude).

Runs via GitHub Actions daily at 4 PM IST.
Can also be run locally: python3 fetch_data.py
"""

import yfinance as yf
import json
import os
from datetime import datetime

# ── FIXED SYMBOLS ─────────────────────────────────────────────────────
INDICES = [
    ("Nifty 50",         "^NSEI"),
    ("Bank Nifty",       "^NSEBANK"),
    ("Nifty Midcap100",  "^CNXMDCP"),
]

COMMODITIES = [
    ("Gold",      "GC=F"),
    ("Crude Oil", "CL=F"),
]

# ── LOAD WATCHLIST FROM JSON ───────────────────────────────────────────
def load_watchlist():
    path = os.path.join(os.path.dirname(__file__), "watchlist.json")
    if not os.path.exists(path):
        print("  watchlist.json not found — skipping stocks")
        return []
    with open(path) as f:
        return json.load(f)

# ── EMA CALCULATION ───────────────────────────────────────────────────
def calc_ema(series, period):
    if len(series) < period:
        return None
    return float(series.ewm(span=period, adjust=False).mean().iloc[-1])

def ema_status(price, ema):
    if ema is None or price is None:
        return "unknown"
    pct = (price - ema) / ema * 100
    if pct > 2:   return "above"
    if pct < -2:  return "below"
    return "near"

# ── FETCH ONE SYMBOL ──────────────────────────────────────────────────
def fetch_symbol(symbol):
    try:
        df = yf.download(symbol, period="1y", interval="1d",
                         progress=False, auto_adjust=True)
        if df.empty:
            return None

        closes = df["Close"].dropna()
        if len(closes) < 21:
            return None

        price   = float(closes.iloc[-1])
        prev    = float(closes.iloc[-2]) if len(closes) > 1 else price
        chg_pct = (price - prev) / prev * 100 if prev else 0
        e21     = calc_ema(closes, 21)
        e50     = calc_ema(closes, 50)
        e200    = calc_ema(closes, 200)

        return {
            "price":    round(price, 2),
            "changePct": round(chg_pct, 2),
            "ema21":    round(e21,  2) if e21  else None,
            "ema50":    round(e50,  2) if e50  else None,
            "ema200":   round(e200, 2) if e200 else None,
            "status21":  ema_status(price, e21),
            "status50":  ema_status(price, e50),
            "status200": ema_status(price, e200),
        }
    except Exception as e:
        print(f"    ERROR {symbol}: {e}")
        return None

# ── MAIN ──────────────────────────────────────────────────────────────
def main():
    now = datetime.utcnow()
    data = {
        "fetchedAt":   now.strftime("%d %b %Y %H:%M UTC"),
        "fetchedAtIST": (now.strftime("%d %b %Y") + " (IST ≈ UTC+5:30)"),
        "indices":     {},
        "commodities": {},
        "watchlist":   [],
    }

    print("\n📊 Indices")
    for name, sym in INDICES:
        r = fetch_symbol(sym)
        if r:
            data["indices"][name] = r
            icon = "✅" if r["status21"] == "above" else "⚠️ " if r["status21"] == "near" else "🔴"
            print(f"  {icon} {name}: ₹{r['price']:,.0f} | 21EMA ₹{r['ema21']:,.0f} ({r['changePct']:+.2f}%)")
        else:
            print(f"  ✗ {name}: no data")

    print("\n🥇 Commodities")
    for name, sym in COMMODITIES:
        r = fetch_symbol(sym)
        if r:
            data["commodities"][name] = r
            print(f"  {name}: ${r['price']:,.2f} ({r['changePct']:+.2f}%)")
        else:
            print(f"  ✗ {name}: no data")

    watchlist = load_watchlist()
    print(f"\n👁 Watchlist ({len(watchlist)} stocks)")
    for w in watchlist:
        r = fetch_symbol(w["symbol"])
        if r:
            r["name"]   = w["name"]
            r["symbol"] = w["symbol"]
            r["sector"] = w.get("sector", "")
            r["setup"]  = w.get("setup", "21EMA")
            r["notes"]  = w.get("notes", "")
            # Flag stocks near their target EMA
            target_status = r.get(f"status{r['setup'].replace('EMA','')}", r["status21"])
            r["alert"] = (target_status == "near")
            data["watchlist"].append(r)
            icon = "🎯" if r["alert"] else ("✅" if r["status21"] == "above" else "🔴")
            print(f"  {icon} {w['name']}: ₹{r['price']:,.1f} | {r['setup']} {target_status}")
        else:
            print(f"  ✗ {w['name']}: no data")

    # Derive overall market signal: Nifty above 21 EMA = GO
    nifty = data["indices"].get("Nifty 50")
    data["marketSignal"] = "GO" if nifty and nifty["status21"] != "below" else "NO-GO"
    data["alertCount"]   = sum(1 for s in data["watchlist"] if s.get("alert"))
    print(f"\n📡 Market Signal: {data['marketSignal']}")
    print(f"🎯 Stocks near EMA: {data['alertCount']}")

    # Write JSON
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_data.json")
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\n✅ Saved: {out_path}\n")

if __name__ == "__main__":
    main()
