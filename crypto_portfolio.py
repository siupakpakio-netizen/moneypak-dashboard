#!/usr/bin/env python3
"""
Crypto 模擬投資組合管理器
BTC / ETH / SOL
本金：HKD 30,000 ≈ USD 3,870
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

HK_TZ = timezone(timedelta(hours=8))
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PORTFOLIO_FILE = os.path.join(DATA_DIR, "crypto_portfolio.json")
TRADES_FILE = os.path.join(DATA_DIR, "crypto_trades.json")

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

# Yahoo Finance crypto symbols
CRYPTO_SYMBOLS = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
}

def fetch_price(symbol):
    ticker = CRYPTO_SYMBOLS.get(symbol, f"{symbol}-USD")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            result = data.get("chart", {}).get("result", [])
            if result:
                return result[0].get("meta", {}).get("regularMarketPrice")
    except:
        pass
    return None

def fetch_all_prices():
    prices = {}
    for sym in CRYPTO_SYMBOLS:
        prices[sym] = fetch_price(sym)
    return prices

def load_json(path, default=None):
    if default is None: default = {}
    if os.path.exists(path):
        with open(path) as f: return json.load(f)
    return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def now_str():
    return datetime.now(HK_TZ).strftime("%Y-%m-%d %H:%M:%S")

def cmd_init(cash_usd):
    p = {"cash_usd": float(cash_usd), "positions": {}, "created": now_str()}
    save_json(PORTFOLIO_FILE, p)
    save_json(TRADES_FILE, [])
    print(f"✅ Crypto 組合初始化！資金: USD {float(cash_usd):,.0f} (≈HKD {float(cash_usd)*7.75:,.0f})")

def cmd_buy(symbol, price, qty):
    p = load_json(PORTFOLIO_FILE, {"cash_usd": 0, "positions": {}})
    trades = load_json(TRADES_FILE, [])
    price, qty = float(price), float(qty)
    cost = price * qty
    
    if p["cash_usd"] < cost:
        print(f"❌ 資金不足！需要 ${cost:,.2f}，可用 ${p['cash_usd']:,.2f}")
        return
    
    p["cash_usd"] -= cost
    sym = symbol.upper()
    
    if sym in p["positions"]:
        pos = p["positions"][sym]
        total_cost = pos["avg_price"] * pos["qty"] + cost
        total_qty = pos["qty"] + qty
        pos["avg_price"] = total_cost / total_qty
        pos["qty"] = total_qty
    else:
        p["positions"][sym] = {"avg_price": price, "qty": qty}
    
    trades.append({"time": now_str(), "action": "BUY", "symbol": sym, "price": price, "qty": qty, "amount": cost})
    save_json(PORTFOLIO_FILE, p)
    save_json(TRADES_FILE, trades)
    print(f"✅ 買入 {sym} {qty:.6f} @ ${price:,.2f} = ${cost:,.2f}")
    print(f"   餘額: ${p['cash_usd']:,.2f}")

def cmd_sell(symbol, price, qty):
    p = load_json(PORTFOLIO_FILE, {"cash_usd": 0, "positions": {}})
    trades = load_json(TRADES_FILE, [])
    price, qty = float(price), float(qty)
    sym = symbol.upper()
    
    if sym not in p["positions"] or p["positions"][sym]["qty"] < qty:
        have = p["positions"].get(sym, {}).get("qty", 0)
        print(f"❌ 持倉不足！持有 {have:.6f}，賣出 {qty:.6f}")
        return
    
    pos = p["positions"][sym]
    revenue = price * qty
    pnl = (price - pos["avg_price"]) * qty
    
    pos["qty"] -= qty
    if pos["qty"] <= 0.0000001:
        del p["positions"][sym]
    
    p["cash_usd"] += revenue
    
    trades.append({"time": now_str(), "action": "SELL", "symbol": sym, "price": price, "qty": qty, "amount": revenue, "pnl": pnl})
    save_json(PORTFOLIO_FILE, p)
    save_json(TRADES_FILE, trades)
    emoji = "🟢" if pnl >= 0 else "🔴"
    print(f"✅ 賣出 {sym} {qty:.6f} @ ${price:,.2f} = ${revenue:,.2f}")
    print(f"   {emoji} 盈虧: ${pnl:>+,.2f}")

def cmd_status():
    p = load_json(PORTFOLIO_FILE, {"cash_usd": 0, "positions": {}})
    prices = fetch_all_prices()
    
    print(f"\n🪙 Crypto 投資組合 — {now_str()}")
    print("═" * 55)
    
    total_value = p.get("cash_usd", 0)
    
    if not p.get("positions"):
        print(f"  💰 現金: ${p['cash_usd']:,.2f} USD")
        print(f"  📭 持倉: 無")
        # Show current prices
        print(f"\n  📊 即時報價：")
        for sym, price in prices.items():
            if price:
                print(f"     {sym}: ${price:,.2f}")
        print("═" * 55)
        return
    
    print(f"{'Coin':<6} {'持倉':>12} {'成本':>10} {'現價':>10} {'市值':>10} {'盈虧':>10}")
    print("─" * 55)
    
    for sym, pos in sorted(p["positions"].items()):
        current = prices.get(sym) or pos["avg_price"]
        market_val = current * pos["qty"]
        cost = pos["avg_price"] * pos["qty"]
        pnl = market_val - cost
        pnl_pct = (current / pos["avg_price"] - 1) * 100
        emoji = "🟢" if pnl >= 0 else "🔴"
        total_value += market_val
        print(f"  {sym:<6} {pos['qty']:>12.6f} ${pos['avg_price']:>9,.2f} ${current:>9,.2f} ${market_val:>9,.2f} {emoji}${pnl:>+9,.2f} ({pnl_pct:>+.1f}%)")
    
    print("─" * 55)
    print(f"  💰 現金: ${p['cash_usd']:,.2f} USD")
    print(f"  💼 總值: ${total_value:,.2f} USD (≈HKD {total_value*7.75:,.0f})")
    print("═" * 55)

def cmd_prices():
    """顯示即時報價"""
    prices = fetch_all_prices()
    print(f"\n🪙 Crypto 即時報價 — {now_str()}")
    print("─" * 40)
    for sym, price in prices.items():
        if price:
            print(f"  {sym}: ${price:,.2f}")
    print("─" * 40)

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    cmd = sys.argv[1].lower()
    if cmd == "init" and len(sys.argv) >= 3:
        cmd_init(sys.argv[2])
    elif cmd == "buy" and len(sys.argv) >= 5:
        cmd_buy(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "sell" and len(sys.argv) >= 5:
        cmd_sell(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "status":
        cmd_status()
    elif cmd == "prices":
        cmd_prices()
    else:
        print(__doc__)

if __name__ == "__main__":
    main()
