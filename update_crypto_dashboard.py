#!/usr/bin/env python3
"""
更新 Crypto Dashboard 數據
被 cron 每5分鐘調用，拉最新報價 → 寫入 JSON → 準備 push GitHub
"""

import json
import os
import urllib.request
from datetime import datetime, timezone, timedelta

HK_TZ = timezone(timedelta(hours=8))
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(TOOLS_DIR, "data")

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

CRYPTO_SYMBOLS = {
    "BTC": {"yahoo": "BTC-USD", "name": "Bitcoin", "color": "#f7931a"},
    "ETH": {"yahoo": "ETH-USD", "name": "Ethereum", "color": "#627eea"},
    "SOL": {"yahoo": "SOL-USD", "name": "Solana", "color": "#00ffa3"},
}

HISTORY_FILE = os.path.join(DATA_DIR, "crypto_history.json")
PORTFOLIO_FILE = os.path.join(DATA_DIR, "crypto_portfolio.json")
TRADES_FILE = os.path.join(DATA_DIR, "crypto_trades.json")
DASHBOARD_JSON = os.path.join(TOOLS_DIR, "crypto_data.json")


def fetch_price(yahoo_symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval=1d&range=1d"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            result = data.get("chart", {}).get("result", [])
            if result:
                meta = result[0].get("meta", {})
                return {
                    "price": meta.get("regularMarketPrice"),
                    "change": meta.get("regularMarketPrice", 0) - (meta.get("chartPreviousClose") or meta.get("regularMarketPreviousClose", 0)),
                    "prevClose": meta.get("chartPreviousClose") or meta.get("regularMarketPreviousClose"),
                }
    except Exception as e:
        print(f"Error fetching {yahoo_symbol}: {e}")
    return None


def load_json(path, default=None):
    if default is None: default = {}
    if os.path.exists(path):
        with open(path) as f: return json.load(f)
    return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    now = datetime.now(HK_TZ)
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    time_str = now.strftime("%H:%M")
    
    print(f"🪙 更新 Crypto Dashboard — {now_str}")
    
    # Fetch prices
    coins = []
    for symbol, info in CRYPTO_SYMBOLS.items():
        data = fetch_price(info["yahoo"])
        if data and data["price"]:
            price = data["price"]
            change = data["change"]
            prev = data["prevClose"] or price
            change_pct = (change / prev * 100) if prev else 0
            
            coins.append({
                "symbol": symbol,
                "name": info["name"],
                "color": info["color"],
                "price": round(price, 2),
                "change": round(change, 2),
                "changePct": round(change_pct, 2),
            })
            print(f"  {symbol}: ${price:,.2f} ({change_pct:+.2f}%)")
        else:
            print(f"  {symbol}: ❌ 無數據")
    
    # Load portfolio
    portfolio = load_json(PORTFOLIO_FILE, {"cash_usd": 3870, "positions": {}})
    trades = load_json(TRADES_FILE, [])
    history = load_json(HISTORY_FILE, [])
    
    # Calculate portfolio value
    positions = []
    total_value = portfolio.get("cash_usd", 3870)
    
    for sym, pos in portfolio.get("positions", {}).items():
        coin_data = next((c for c in coins if c["symbol"] == sym), None)
        current_price = coin_data["price"] if coin_data else pos["avg_price"]
        market_val = current_price * pos["qty"]
        pnl = (current_price - pos["avg_price"]) * pos["qty"]
        pnl_pct = (current_price / pos["avg_price"] - 1) * 100
        
        positions.append({
            "symbol": sym,
            "qty": pos["qty"],
            "avgPrice": pos["avg_price"],
            "currentPrice": current_price,
            "marketValue": round(market_val, 2),
            "pnl": round(pnl, 2),
            "pnlPct": round(pnl_pct, 2),
        })
        total_value += market_val
    
    # Update history
    pnl_total = total_value - 3870
    history.append({
        "time": time_str,
        "value": round(total_value, 2),
        "pnl": round(pnl_total, 2),
    })
    save_json(HISTORY_FILE, history)
    
    # Format trades for dashboard
    dash_trades = []
    for t in trades[-20:]:
        dash_trades.append({
            "time": t.get("time", "").split(" ")[-1] if " " in t.get("time", "") else t.get("time", ""),
            "action": t.get("action", ""),
            "symbol": t.get("symbol", ""),
            "price": t.get("price", 0),
            "qty": t.get("qty", 0),
            "amount": t.get("amount", 0),
            "pnl": t.get("pnl"),
        })
    
    # Build dashboard data
    dashboard = {
        "lastUpdate": now_str,
        "cash": portfolio.get("cash_usd", 3870),
        "coins": coins,
        "positions": positions,
        "trades": dash_trades,
        "history": history,
    }
    
    # Save dashboard JSON
    save_json(DASHBOARD_JSON, dashboard)
    print(f"✅ Dashboard JSON updated: {DASHBOARD_JSON}")
    print(f"   Coins: {len(coins)}")
    print(f"   Positions: {len(positions)}")
    print(f"   Total: ${total_value:,.2f} (PnL: ${pnl_total:+,.2f})")
    
    # Update HTML dashboard with embedded data
    html_path = os.path.join(TOOLS_DIR, "crypto_dashboard.html")
    if os.path.exists(html_path):
        with open(html_path) as f:
            html = f.read()
        
        import re
        data_json = json.dumps(dashboard, indent=2, ensure_ascii=False)
        pattern = r'const DATA = \{.*?\};'
        new_html = re.sub(pattern, f'const DATA = {data_json};', html, flags=re.DOTALL)
        
        with open(html_path, "w") as f:
            f.write(new_html)
        print(f"✅ HTML dashboard updated")


if __name__ == "__main__":
    main()
