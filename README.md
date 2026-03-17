# 📊 MoneyPak Algo Trading System

## 架構
```
TradingView (Pine Script Indicator)
     ↓ Webhook Alert
IBKR Algo (Python Flask)
     ↓ TWS API
Interactive Brokers (自動落單)
```

## 文件結構

### TradingView 指標
| 文件 | 說明 |
|------|------|
| `MoneyPak_HK.pine` | 港股版指標（RSI/MACD/BB/均線綜合評分） |
| `MoneyPak_US.pine` | 美股版指標（加ATR動態止損） |

### IBKR 自動交易
| 文件 | 說明 | Port |
|------|------|------|
| `ibkr_hk_algo.py` | 港股自動落單 | 5001 |
| `ibkr_us_algo.py` | 美股自動落單 | 5002 |

### 交易規則
| 文件 | 說明 |
|------|------|
| `trading_rules.py` | 完整交易規則引擎 |
| `TRADING_RULES.md` | 規則文檔 |

### Dashboard
| 文件 | 說明 |
|------|------|
| `index.html` | 港股 Dashboard |
| `us_dashboard.html` | 美股 Dashboard |

## 使用方法

### 1. TradingView
1. 打開 TradingView
2. Pine Editor → 貼上 `.pine` 文件
3. Add to chart
4. 設定 Alert → Webhook URL

### 2. IBKR 自動交易
```bash
# 安裝
pip install ib_insync flask

# 啟動 TWS → 開啟 API

# 港股
python3 ibkr_hk_algo.py  # Port 5001

# 美股  
python3 ibkr_us_algo.py  # Port 5002
```

### 3. TradingView Alert → IBKR
Alert message 格式：
```json
{"action":"BUY","ticker":"{{ticker}}","price":{{close}},"score":5.5,"market":"HK"}
```

Webhook URL：
- 港股: `http://你的IP:5001/webhook`
- 美股: `http://你的IP:5002/webhook`

## 風險控制
- Paper Trading 模式預設開啟
- 單股上限：總資金 30%
- 每日虧損上限：5%
- 止損：5% / ATR 1.5倍
- 止盈：10% / ATR 3倍

## ⚠️ 免責聲明
模擬交易僅供參考，不構成投資建議。
自動交易有風險，請先 Paper Trading 測試。
