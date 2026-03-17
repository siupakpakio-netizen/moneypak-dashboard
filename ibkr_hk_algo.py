#!/usr/bin/env python3
"""
MoneyPak IBKR Algo Trade — 港股版
═══════════════════════════════════════════
接收 TradingView Webhook → 透過 IBKR 自動落港股單

用法：
1. 啟動 TWS (Trader Workstation) 或 IB Gateway
2. 開啟 API 連接 (設定 → API → 啟用 ActiveX)
3. python3 ibkr_hk_algo.py
4. TradingView Alert Webhook → http://你的IP:5001/webhook

Requirements:
pip install ib_insync flask
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
from threading import Lock

# ═══════════════════════════════════════════
# 設定
# ═══════════════════════════════════════════

CONFIG = {
    # IBKR 連接設定
    "ib_host": "127.0.0.1",
    "ib_port": 7497,        # TWS 預設 7497，Gateway 4001
    "ib_client_id": 1,
    
    # 交易設定
    "market": "HK",
    "currency": "HKD",
    "exchange": "SEHK",     # 香港交易所
    "default_quantity": 100, # 預設股數（港股每手股數因股票而異）
    
    # 風險控制
    "max_position_value": 9000,     # 單股最大持倉 HKD 9,000 (30%)
    "max_daily_trades": 10,         # 每日最多10筆交易
    "max_daily_loss": 1500,         # 每日最大虧損 HKD 1,500 (5%)
    "stop_loss_pct": 0.05,          # 止損 5%
    "take_profit_pct": 0.10,        # 止盈 10%
    
    # Paper Trading 模式（建議先用 Paper 測試）
    "paper_trading": True,  # True = 模擬盤，False = 真實盤
}

# ═══════════════════════════════════════════
# 初始化
# ═══════════════════════════════════════════

HK_TZ = timezone(timedelta(hours=8))
LOG_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(LOG_DIR, exist_ok=True)

app = Flask(__name__)
trade_lock = Lock()
trade_count = 0
daily_pnl = 0

# IBKR 連接（延遲加載）
ib = None

def connect_ibkr():
    """連接 IBKR"""
    global ib
    try:
        from ib_insync import IB, Stock, MarketOrder, LimitOrder, StopOrder
        
        ib = IB()
        port = CONFIG["ib_port"] if not CONFIG["paper_trading"] else 7497
        ib.connect(CONFIG["ib_host"], port, clientId=CONFIG["ib_client_id"])
        
        mode = "Paper 📝" if CONFIG["paper_trading"] else "🔴 REAL"
        print(f"✅ IBKR 已連接 ({mode}) - {CONFIG['ib_host']}:{port}")
        return True
    except Exception as e:
        print(f"❌ IBKR 連接失敗: {e}")
        print("請確認 TWS/Gateway 已啟動，API 已開啟")
        return False


# ═══════════════════════════════════════════
# 交易邏輯
# ═══════════════════════════════════════════

def get_hk_symbol(ticker):
    """轉換港股代碼格式
    TradingView: 0700.HK → IBKR: 0700 SEHK HKD
    """
    code = ticker.replace(".HK", "").replace(".hk", "")
    # 補齊4位
    code = code.zfill(4)
    return code


def calculate_quantity(price):
    """計算可買股數（考慮倉位限制）"""
    max_value = CONFIG["max_position_value"]
    qty = int(max_value / price)
    # 港股通常有每手股數，但這裡簡化處理
    return max(qty, 1)


def place_order(action, ticker, price, score):
    """落單"""
    global trade_count, daily_pnl
    
    with trade_lock:
        # 檢查風險限制
        if trade_count >= CONFIG["max_daily_trades"]:
            log_trade("REJECTED", ticker, 0, price, "達到每日交易上限")
            return {"status": "rejected", "reason": "daily_limit"}
        
        if daily_pnl <= -CONFIG["max_daily_loss"]:
            log_trade("REJECTED", ticker, 0, price, "達到每日虧損上限")
            return {"status": "rejected", "reason": "daily_loss_limit"}
        
        try:
            from ib_insync import Stock, MarketOrder, LimitOrder
            
            code = get_hk_symbol(ticker)
            contract = Stock(code, CONFIG["exchange"], CONFIG["currency"])
            
            # 確認合約
            ib.qualifyContracts(contract)
            
            qty = calculate_quantity(price)
            
            if action == "BUY":
                # 市價單買入
                order = MarketOrder("BUY", qty)
                order.tif = "DAY"
                
                trade = ib.placeOrder(contract, order)
                print(f"🟢 BUY {code} x{qty} @ ~{price:.2f} HKD")
                
                # 設置止損單
                stop_price = round(price * (1 - CONFIG["stop_loss_pct"]), 2)
                stop_order = LimitOrder("SELL", qty, stop_price)
                stop_order.tif = "GTC"  # Good Till Cancelled
                # ib.placeOrder(contract, stop_order)  # 取消註釋以啟用自動止損
                
                trade_count += 1
                log_trade("BUY", ticker, qty, price, f"Score:{score}")
                
            elif action == "SELL":
                order = MarketOrder("SELL", qty)
                order.tif = "DAY"
                
                trade = ib.placeOrder(contract, order)
                print(f"🔴 SELL {code} x{qty} @ ~{price:.2f} HKD")
                
                trade_count += 1
                log_trade("SELL", ticker, qty, price, f"Score:{score}")
            
            return {"status": "ok", "action": action, "ticker": ticker, "qty": qty}
            
        except Exception as e:
            print(f"❌ 落單失敗: {e}")
            log_trade("ERROR", ticker, 0, price, str(e))
            return {"status": "error", "reason": str(e)}


def log_trade(action, ticker, qty, price, note):
    """記錄交易"""
    now = datetime.now(HK_TZ).strftime("%Y-%m-%d %H:%M:%S")
    log_file = os.path.join(LOG_DIR, "ibkr_hk_trades.jsonl")
    
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
    
    print(f"📝 {now} | {action} | {ticker} | {note}")


# ═══════════════════════════════════════════
# Flask Webhook 端點
# ═══════════════════════════════════════════

@app.route("/webhook", methods=["POST"])
def webhook():
    """接收 TradingView Webhook"""
    try:
        data = request.get_json(force=True)
        
        action = data.get("action", "").upper()
        ticker = data.get("ticker", "")
        price = float(data.get("price", 0))
        score = float(data.get("score", 0))
        market = data.get("market", "HK")
        
        # 只處理港股
        if market != "HK":
            return jsonify({"status": "skip", "reason": "not HK market"})
        
        # 驗證
        if action not in ["BUY", "SELL"]:
            return jsonify({"status": "error", "reason": "invalid action"})
        
        if not ticker or price <= 0:
            return jsonify({"status": "error", "reason": "invalid data"})
        
        # 檢查評分門檻
        if action == "BUY" and score < 3:
            return jsonify({"status": "skip", "reason": f"score too low: {score}"})
        
        print(f"\n{'='*40}")
        print(f"📨 Webhook: {action} {ticker} @ {price} (Score: {score})")
        
        # 落單
        result = place_order(action, ticker, price, score)
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return jsonify({"status": "error", "reason": str(e)}), 500


@app.route("/status", methods=["GET"])
def status():
    """查詢狀態"""
    return jsonify({
        "market": "HK",
        "mode": "Paper" if CONFIG["paper_trading"] else "REAL",
        "connected": ib.isConnected() if ib else False,
        "trade_count": trade_count,
        "daily_pnl": daily_pnl,
        "config": {
            "max_position": CONFIG["max_position_value"],
            "stop_loss": f"{CONFIG['stop_loss_pct']*100}%",
            "take_profit": f"{CONFIG['take_profit_pct']*100}%",
        }
    })


@app.route("/", methods=["GET"])
def home():
    return """
    <h1>🇭🇰 MoneyPak IBKR 港股 Algo Trade</h1>
    <p>Webhook endpoint: <code>/webhook</code></p>
    <p>Status: <a href="/status">/status</a></p>
    <hr>
    <pre>
    POST /webhook
    {
        "action": "BUY",
        "ticker": "0700.HK",
        "price": 560,
        "score": 5.5,
        "market": "HK"
    }
    </pre>
    """


# ═══════════════════════════════════════════
# 主程式
# ═══════════════════════════════════════════

if __name__ == "__main__":
    mode = "📝 Paper Trading" if CONFIG["paper_trading"] else "🔴 REAL TRADING"
    print(f"═══════════════════════════════════════")
    print(f"🇭🇰 MoneyPak IBKR 港股 Algo Trade")
    print(f"═══════════════════════════════════════")
    print(f"模式: {mode}")
    print(f"Webhook: http://0.0.0.0:5001/webhook")
    print(f"═══════════════════════════════════════")
    
    # 嘗試連接 IBKR
    connect_ibkr()
    
    # 啟動 Flask
    app.run(host="0.0.0.0", port=5001, debug=False)
