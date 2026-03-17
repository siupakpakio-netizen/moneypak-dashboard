#!/usr/bin/env python3
"""
MoneyPak IBKR Algo Trade — 美股版
═══════════════════════════════════════════
接收 TradingView Webhook → 透過 IBKR 自動落美股單

用法：
1. 啟動 TWS 或 IB Gateway
2. python3 ibkr_us_algo.py
3. TradingView Alert Webhook → http://你的IP:5002/webhook

pip install ib_insync flask
"""

import json
import os
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
from threading import Lock

# ═══════════════════════════════════════════
# 設定
# ═══════════════════════════════════════════

CONFIG = {
    "ib_host": "127.0.0.1",
    "ib_port": 7497,
    "ib_client_id": 2,      # 唔同client ID避免衝突
    
    "market": "US",
    "currency": "USD",
    "exchange": "SMART",     # IBKR SMART routing
    
    # 風險控制（USD）
    "max_position_value": 1160,     # ~USD 1,160 (30% of 3,870)
    "max_daily_trades": 8,
    "max_daily_loss": 194,          # 5% of 3,870
    "stop_loss_pct": 0.05,
    "take_profit_pct": 0.10,
    
    # 美股特有
    "avoid_first_15min": True,      # 避開開市首15分鐘
    "power_hour_only": False,       # 只喺最後1小時交易
    "use_atr_stop": True,           # 用ATR動態止損
    
    "paper_trading": True,
}

# ═══════════════════════════════════════════

HK_TZ = timezone(timedelta(hours=8))
ET_TZ = timezone(timedelta(hours=-4))  # EDT
LOG_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(LOG_DIR, exist_ok=True)

app = Flask(__name__)
trade_lock = Lock()
trade_count = 0
daily_pnl = 0
ib = None


def connect_ibkr():
    global ib
    try:
        from ib_insync import IB
        ib = IB()
        port = CONFIG["ib_port"]
        ib.connect(CONFIG["ib_host"], port, clientId=CONFIG["ib_client_id"])
        mode = "Paper 📝" if CONFIG["paper_trading"] else "🔴 REAL"
        print(f"✅ IBKR US 已連接 ({mode})")
        return True
    except Exception as e:
        print(f"❌ 連接失敗: {e}")
        return False


def is_market_hours():
    """檢查美股交易時間（美東 9:30-16:00）"""
    now_et = datetime.now(ET_TZ)
    hour = now_et.hour
    minute = now_et.minute
    weekday = now_et.weekday()
    
    if weekday >= 5:  # 週末
        return False
    
    current_minutes = hour * 60 + minute
    market_open = 9 * 60 + 30   # 9:30
    market_close = 16 * 60      # 16:00
    
    return market_open <= current_minutes <= market_close


def calculate_qty(price):
    """計算股數"""
    max_val = CONFIG["max_position_value"]
    return max(int(max_val / price), 1)


def place_order(action, ticker, price, score, atr=None):
    global trade_count, daily_pnl
    
    with trade_lock:
        if trade_count >= CONFIG["max_daily_trades"]:
            return {"status": "rejected", "reason": "daily_limit"}
        
        if daily_pnl <= -CONFIG["max_daily_loss"]:
            return {"status": "rejected", "reason": "daily_loss_limit"}
        
        try:
            from ib_insync import Stock, MarketOrder
            
            contract = Stock(ticker, CONFIG["exchange"], CONFIG["currency"])
            ib.qualifyContracts(contract)
            
            qty = calculate_qty(price)
            
            if action == "BUY":
                order = MarketOrder("BUY", qty)
                trade = ib.placeOrder(contract, order)
                
                # ATR動態止損
                if atr and CONFIG["use_atr_stop"]:
                    stop_price = round(price - atr * 1.5, 2)
                else:
                    stop_price = round(price * (1 - CONFIG["stop_loss_pct"]), 2)
                
                print(f"🟢 US BUY {ticker} x{qty} @ ~${price:.2f}")
                print(f"   止損: ${stop_price:.2f}")
                
                trade_count += 1
                log_trade("BUY", ticker, qty, price, f"Score:{score} SL:{stop_price}")
                
            elif action == "SELL":
                order = MarketOrder("SELL", qty)
                trade = ib.placeOrder(contract, order)
                print(f"🔴 US SELL {ticker} x{qty} @ ~${price:.2f}")
                trade_count += 1
                log_trade("SELL", ticker, qty, price, f"Score:{score}")
            
            return {"status": "ok", "action": action, "ticker": ticker, "qty": qty}
            
        except Exception as e:
            print(f"❌ 落單失敗: {e}")
            log_trade("ERROR", ticker, 0, price, str(e))
            return {"status": "error", "reason": str(e)}


def log_trade(action, ticker, qty, price, note):
    now = datetime.now(HK_TZ).strftime("%Y-%m-%d %H:%M:%S")
    log_file = os.path.join(LOG_DIR, "ibkr_us_trades.jsonl")
    
    entry = {
        "time": now,
        "action": action,
        "ticker": ticker,
        "qty": qty,
        "price": price,
        "note": note,
        "paper": CONFIG["paper_trading"],
    }
    
    with open(log_file, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ═══════════════════════════════════════════
# Webhook
# ═══════════════════════════════════════════

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        
        action = data.get("action", "").upper()
        ticker = data.get("ticker", "")
        price = float(data.get("price", 0))
        score = float(data.get("score", 0))
        market = data.get("market", "US")
        atr = data.get("atr")
        
        if market != "US":
            return jsonify({"status": "skip", "reason": "not US market"})
        
        if action not in ["BUY", "SELL"]:
            return jsonify({"status": "error", "reason": "invalid action"})
        
        if not ticker or price <= 0:
            return jsonify({"status": "error", "reason": "invalid data"})
        
        if action == "BUY" and score < 3:
            return jsonify({"status": "skip", "reason": f"score too low: {score}"})
        
        print(f"\n{'='*40}")
        print(f"📨 US Webhook: {action} {ticker} @ ${price} (Score: {score})")
        
        result = place_order(action, ticker, price, score, atr)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"status": "error", "reason": str(e)}), 500


@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "market": "US",
        "mode": "Paper" if CONFIG["paper_trading"] else "REAL",
        "connected": ib.isConnected() if ib else False,
        "market_open": is_market_hours(),
        "trade_count": trade_count,
        "daily_pnl": daily_pnl,
        "config": {
            "max_position": CONFIG["max_position_value"],
            "max_daily_loss": CONFIG["max_daily_loss"],
            "stop_loss": f"{CONFIG['stop_loss_pct']*100}%",
            "take_profit": f"{CONFIG['take_profit_pct']*100}%",
        }
    })


@app.route("/", methods=["GET"])
def home():
    return """
    <h1>🇺🇸 MoneyPak IBKR 美股 Algo Trade</h1>
    <p>Webhook: <code>/webhook</code></p>
    <p>Status: <a href="/status">/status</a></p>
    <pre>
    POST /webhook
    {"action":"BUY","ticker":"AAPL","price":252,"score":5.5,"market":"US","atr":5.2}
    </pre>
    """


if __name__ == "__main__":
    mode = "📝 Paper" if CONFIG["paper_trading"] else "🔴 REAL"
    print(f"═══════════════════════════════════════")
    print(f"🇺🇸 MoneyPak IBKR 美股 Algo Trade")
    print(f"模式: {mode}")
    print(f"Webhook: http://0.0.0.0:5002/webhook")
    print(f"═══════════════════════════════════════")
    
    connect_ibkr()
    app.run(host="0.0.0.0", port=5002, debug=False)
