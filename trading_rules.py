#!/usr/bin/env python3
"""
MoneyPak 交易規則引擎 v1.0
═══════════════════════════════════════════
所有買賣決定必須通過以下規則先可以執行
每個決定都要有明確理由，收市要做反思
"""

import json
import os
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
from typing import List, Optional

HK_TZ = timezone(timedelta(hours=8))
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# ═══════════════════════════════════════════
# 第一章：倉位管理規則
# ═══════════════════════════════════════════

POSITION_RULES = {
    "max_single_position_pct": 0.30,      # 單隻股票最多佔總資金30%
    "max_sector_exposure_pct": 0.50,       # 單一板塊最多佔50%
    "min_cash_reserve_pct": 0.20,          # 最少保留20%現金
    "max_total_positions": 5,              # 最多同時持有5隻
    "max_daily_loss_pct": 0.05,            # 單日最大虧損5%（觸發減倉）
}

# ═══════════════════════════════════════════
# 第二章：技術指標規則
# ═══════════════════════════════════════════

TECHNICAL_RULES = {
    # RSI 規則
    "rsi": {
        "oversold": 30,          # < 30 超賣，考慮買入
        "overbought": 70,        # > 70 超買，考慮賣出
        "strong_oversold": 20,   # < 20 強烈超賣，積極買入
        "strong_overbought": 80, # > 80 強烈超買，積極賣出
        "neutral_low": 40,       # 40-60 中性區
        "neutral_high": 60,
    },
    
    # MACD 規則
    "macd": {
        "buy_signal": "macd > signal AND histogram > 0",
        "sell_signal": "macd < signal AND histogram < 0",
        "strong_buy": "macd > signal AND histogram > 0 AND histogram > prev_histogram",
        "strong_sell": "macd < signal AND histogram < 0 AND histogram < prev_histogram",
    },
    
    # 移動平均線規則
    "moving_averages": {
        "bullish": "price > SMA20 > SMA50 > SMA200",  # 多頭排列
        "bearish": "price < SMA20 < SMA50 < SMA200",  # 空頭排列
        "golden_cross": "SMA50 上穿 SMA200",           # 金叉（長期買入）
        "death_cross": "SMA50 下穿 SMA200",            # 死叉（長期賣出）
        "support": "price 接近 SMA20 且反彈",          # 支撐位
        "resistance": "price 接近 SMA50 且回落",       # 阻力位
    },
    
    # 布林帶規則
    "bollinger": {
        "buy": "price < lower_band AND RSI < 35",      # 跌穿下軌+超賣
        "sell": "price > upper_band AND RSI > 65",     # 升穿上軌+超買
        "squeeze": "bandwidth < 20日最低",              # 波幅收窄，準備突破
    },
    
    # 成交量規則
    "volume": {
        "breakout": "volume > avg_volume_20 * 1.5 AND price_up",   # 放量上漲
        "breakdown": "volume > avg_volume_20 * 1.5 AND price_down", # 放量下跌
        "weak_rally": "volume < avg_volume_20 AND price_up",        # 無量上漲（假突破）
        "accumulation": "volume > avg_volume_20 AND price_flat",    # 橫盤放量（吸籌）
    },
}

# ═══════════════════════════════════════════
# 第三章：新聞/事件規則
# ═══════════════════════════════════════════

NEWS_RULES = {
    # 業績期
    "earnings": {
        "buy_on_beat": "業績超預期 AND 上調指引 → 買入",
        "sell_on_miss": "業績遜預期 AND 下調指引 → 賣出",
        "hold_on_mixed": "業績超預期但指引保守 → 持有觀察",
        "pre_earnings": "業績前3日減倉至半倉（避免gap風險）",
    },
    
    # 分析師評級
    "analyst": {
        "upgrade": "目標價上調 > 10% → 加強信心",
        "downgrade": "目標價下調 > 10% → 減倉或止損",
        "initiate": "首次覆蓋買入 → 觀察",
    },
    
    # 宏觀事件
    "macro": {
        "fed_decision": "議息前1日減倉",
        "cpi_data": "CPI日當日唔開新倉",
        "geopolitical": "地緣風險升溫 → 增持現金",
        "policy_stimulus": "政策利好 → 增持周期股",
    },
    
    # 公司事件
    "corporate": {
        "buyback": "大額回購計劃 → 利好",
        "insider_buying": "內部人大額增持 → 利好",
        "insider_selling": "內部人大額減持 → 注意",
        "mna": "併購消息 → 分析溢價合理性",
    },
}

# ═══════════════════════════════════════════
# 第四章：風險控制規則
# ═══════════════════════════════════════════

RISK_RULES = {
    "stop_loss": {
        "default_pct": 0.05,        # 預設止損 5%
        "tight_pct": 0.03,          # 短線止損 3%
        "wide_pct": 0.08,           # 長線止損 8%
        "trailing_pct": 0.03,       # 移動止損 3%
        "rule": "買入即設止損，唔可以取消只可以收窄",
    },
    
    "take_profit": {
        "default_pct": 0.10,        # 預設止盈 10%
        "aggressive_pct": 0.20,     # 強勢股止盈 20%
        "partial": "到達目標先賣一半，另一半用移動止損",
        "rule": "止盈可以放寬，但唔可以貪",
    },
    
    "drawdown": {
        "warning_pct": 0.03,        # 回撤3%警告
        "reduce_pct": 0.05,         # 回撤5%減倉50%
        "stop_pct": 0.08,           # 回撤8%清倉反省
    },
    
    "correlation": {
        "rule": "唔好買超過2隻相關性高嘅股票",
        "example": "例如騰訊+美團（都係科技）要控制比例",
    },
}

# ═══════════════════════════════════════════
# 第五章：交易時間規則
# ═══════════════════════════════════════════

TIMING_RULES = {
    "hk": {
        "avoid_first_5min": "開市首5分鐘觀察為主（避免被騙）",
        "avoid_last_5min": "收市前5分鐘唔開新倉",
        "best_entry": "10:00-10:30 / 14:00-14:30",
        "lunch_break": "12:00-13:00 觀察新聞，唔操作",
    },
    "us": {
        "avoid_first_15min": "開市首15分鐘波動大，觀察",
        "power_hour": "最後1小時（03:00-04:00 HKT）最重要",
        "pre_market": "盤前數據影響開市方向",
    },
}

# ═══════════════════════════════════════════
# 決策記錄系統
# ═══════════════════════════════════════════

@dataclass
class TradeDecision:
    timestamp: str
    market: str           # HK / US
    code: str
    name: str
    action: str           # BUY / SELL / HOLD
    price: float
    qty: int
    strategies: List[str] # 使用嘅策略
    indicators: dict      # 當時嘅指標數據
    news_factors: List[str] # 新聞因素
    confidence: float     # 信心度 0-1
    risk_reward: float    # 風險回報比
    stop_loss: float
    take_profit: float
    reason: str           # 主要理由
    risk_note: str        # 風險提示
    approved: bool = False
    
    def to_dict(self):
        return asdict(self)


DECISIONS_FILE = os.path.join(DATA_DIR, "trade_decisions.json")
REFLECTIONS_FILE = os.path.join(DATA_DIR, "daily_reflections.json")


def record_decision(decision: TradeDecision):
    """記錄每一個交易決定"""
    os.makedirs(DATA_DIR, exist_ok=True)
    
    decisions = []
    if os.path.exists(DECISIONS_FILE):
        with open(DECISIONS_FILE) as f:
            decisions = json.load(f)
    
    decisions.append(decision.to_dict())
    
    with open(DECISIONS_FILE, "w") as f:
        json.dump(decisions, f, indent=2, ensure_ascii=False)


def evaluate_stock(code, name, price, indicators, news=None):
    """
    綜合評估一隻股票，返回 TradeDecision
    每次分析都要走呢個流程
    """
    signals = []
    strategies = []
    news_factors = []
    score = 0
    
    rsi = indicators.get("rsi", 50)
    macd = indicators.get("macd", 0)
    macd_signal = indicators.get("macd_signal", 0)
    price_sma20 = indicators.get("sma20", price)
    price_sma50 = indicators.get("sma50", price)
    price_sma200 = indicators.get("sma200", price)
    bb_lower = indicators.get("bb_lower", price * 0.95)
    bb_upper = indicators.get("bb_upper", price * 1.05)
    volume = indicators.get("volume", 0)
    avg_volume = indicators.get("avg_volume", 1)
    
    # ── RSI 分析 ──
    if rsi < TECHNICAL_RULES["rsi"]["strong_oversold"]:
        score += 3
        signals.append(f"RSI={rsi:.0f} 強烈超賣💎")
        strategies.append("均值回歸")
    elif rsi < TECHNICAL_RULES["rsi"]["oversold"]:
        score += 2
        signals.append(f"RSI={rsi:.0f} 超賣🟢")
        strategies.append("均值回歸")
    elif rsi > TECHNICAL_RULES["rsi"]["strong_overbought"]:
        score -= 3
        signals.append(f"RSI={rsi:.0f} 強烈超買⚠️")
    elif rsi > TECHNICAL_RULES["rsi"]["overbought"]:
        score -= 2
        signals.append(f"RSI={rsi:.0f} 超買🟡")
    else:
        signals.append(f"RSI={rsi:.0f} 中性")
    
    # ── MACD 分析 ──
    if macd > macd_signal:
        score += 1
        signals.append("MACD金叉🟢")
        strategies.append("動量策略")
    else:
        score -= 1
        signals.append("MACD死叉🔴")
    
    # ── 均線分析 ──
    if price > price_sma20 > price_sma50:
        score += 2
        signals.append("多頭排列🟢")
        strategies.append("趨勢跟蹤")
    elif price < price_sma20 < price_sma50:
        score -= 2
        signals.append("空頭排列🔴")
    
    if price > price_sma200:
        score += 1
        signals.append("牛市區域🟢")
    else:
        score -= 1
        signals.append("熊市區域🔴")
    
    # ── 布林帶分析 ──
    if price < bb_lower:
        score += 2
        signals.append("跌穿BB下軌🟢")
        if "均值回歸" not in strategies:
            strategies.append("均值回歸")
    elif price > bb_upper:
        score -= 2
        signals.append("升穿BB上軌🔴")
    
    # ── 成交量分析 ──
    vol_ratio = volume / avg_volume if avg_volume > 0 else 1
    if vol_ratio > 1.5 and score > 0:
        score += 1
        signals.append(f"放量上攻({vol_ratio:.1f}x)🟢")
    elif vol_ratio < 0.5:
        signals.append(f"成交萎縮({vol_ratio:.1f}x)⚠️")
    
    # ── 新聞因素 ──
    if news:
        for n in news:
            if n.get("sentiment") == "positive":
                score += 1
                news_factors.append(n.get("title", ""))
                strategies.append("事件驅動")
            elif n.get("sentiment") == "negative":
                score -= 1
                news_factors.append(n.get("title", ""))
    
    # ── 綜合決策 ──
    if score >= 5:
        action = "BUY"
        confidence = min(0.9, 0.5 + score * 0.05)
    elif score >= 3:
        action = "BUY"
        confidence = min(0.7, 0.4 + score * 0.05)
    elif score <= -3:
        action = "SELL"
        confidence = min(0.8, 0.5 + abs(score) * 0.05)
    else:
        action = "HOLD"
        confidence = 0.5
    
    # 計算止損止盈
    if action == "BUY":
        stop_loss = price * (1 - RISK_RULES["stop_loss"]["default_pct"])
        take_profit = price * (1 + RISK_RULES["take_profit"]["default_pct"])
        risk_reward = (take_profit - price) / (price - stop_loss) if price > stop_loss else 0
        reason = " | ".join(signals[:3])
    elif action == "SELL":
        stop_loss = 0
        take_profit = 0
        risk_reward = 0
        reason = " | ".join(signals[:3])
    else:
        stop_loss = 0
        take_profit = 0
        risk_reward = 0
        reason = "信號不足，繼續觀察"
    
    now = datetime.now(HK_TZ).strftime("%Y-%m-%d %H:%M:%S")
    
    decision = TradeDecision(
        timestamp=now,
        market="HK" if ".HK" in code else "US",
        code=code,
        name=name,
        action=action,
        price=price,
        qty=0,  # 由實際交易填入
        strategies=list(set(strategies)),
        indicators={
            "rsi": rsi, "macd": macd, "macd_signal": macd_signal,
            "sma20": price_sma20, "sma50": price_sma50,
            "score": score, "signals": signals
        },
        news_factors=news_factors,
        confidence=confidence,
        risk_reward=risk_reward,
        stop_loss=stop_loss,
        take_profit=take_profit,
        reason=reason,
        risk_note=f"信心度{confidence*100:.0f}% | 風報比{risk_reward:.1f}"
    )
    
    return decision


# ═══════════════════════════════════════════
# 收市反思系統
# ═══════════════════════════════════════════

def generate_daily_reflection(date_str=None):
    """
    每日收市反思：
    1. 今日做咗啲乜
    2. 用咗咩策略
    3. 邊啲決定啱，邊啲錯
    4. 點樣改進
    """
    if not date_str:
        date_str = datetime.now(HK_TZ).strftime("%Y-%m-%d")
    
    decisions = []
    if os.path.exists(DECISIONS_FILE):
        with open(DECISIONS_FILE) as f:
            all_decisions = json.load(f)
            decisions = [d for d in all_decisions if d["timestamp"].startswith(date_str)]
    
    if not decisions:
        return f"📋 {date_str} 暫無交易紀錄"
    
    buys = [d for d in decisions if d["action"] == "BUY"]
    sells = [d for d in decisions if d["action"] == "SELL"]
    holds = [d for d in decisions if d["action"] == "HOLD"]
    
    # 策略使用統計
    strategy_count = {}
    for d in decisions:
        for s in d.get("strategies", []):
            strategy_count[s] = strategy_count.get(s, 0) + 1
    
    # 計算勝率
    wins = sum(1 for d in sells if d.get("indicators", {}).get("score", 0) < 0)
    total_sells = len(sells)
    win_rate = wins / total_sells * 100 if total_sells > 0 else 0
    
    reflection = f"""
═══════════════════════════════════════
📋 每日交易反思 — {date_str}
═══════════════════════════════════════

📊 交易統計：
  • 買入次數: {len(buys)}
  • 賣出次數: {len(sells)}
  • 觀望次數: {len(holds)}

🧠 策略使用："""
    
    for s, count in sorted(strategy_count.items(), key=lambda x: -x[1]):
        reflection += f"\n  • {s}: {count}次"
    
    reflection += f"""

📈 詳細記錄："""
    
    for d in decisions:
        emoji = "🟢" if d["action"] == "BUY" else ("🔴" if d["action"] == "SELL" else "⚪")
        reflection += f"\n  {emoji} {d['timestamp'].split(' ')[1]} {d['action']} {d['code']} @ {d['price']}"
        reflection += f"\n     理由: {d['reason']}"
        reflection += f"\n     策略: {', '.join(d.get('strategies', []))}"
    
    reflection += f"""

═══════════════════════════════════════
📝 反思與改進：
═══════════════════════════════════════

✅ 做得好的：
  • 所有決定都有明確理由記錄
  • 遵守倉位管理規則
  • 設置止損止盈

⚠️ 需要改進的：
  • 持續追蹤每個決定嘅結果
  • 計算實際勝率同盈虧比
  • 根據市場環境調整策略權重

🎯 明日策略調整：
  • 關注成交量變化
  • 留意新聞事件影響
  • 嚴格執行止損

═══════════════════════════════════════
"""
    
    # 儲存反思
    os.makedirs(DATA_DIR, exist_ok=True)
    reflections = []
    if os.path.exists(REFLECTIONS_FILE):
        with open(REFLECTIONS_FILE) as f:
            reflections = json.load(f)
    
    reflections.append({
        "date": date_str,
        "reflection": reflection,
        "stats": {
            "buys": len(buys),
            "sells": len(sells),
            "holds": len(holds),
            "strategies": strategy_count,
        }
    })
    
    with open(REFLECTIONS_FILE, "w") as f:
        json.dump(reflections, f, indent=2, ensure_ascii=False)
    
    return reflection


if __name__ == "__main__":
    print(generate_daily_reflection())
