import requests

TOKEN = "9171870506:AAFvZn7HBBtnhIkJ2fFfvr1cB6JRWwPepic"
CHAT_ID = "8902758637" 

STABLECOINS = ['USDC', 'USDT', 'DAI', 'FDUSD', 'TUSD', 'USDD', 'USDE']

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def get_bybit_coins():
    bybit_coins = set()
    try:
        for page in range(1, 4):
            url = f"https://api.coingecko.com/api/v3/exchanges/bybit/tickers?page={page}"
            res = requests.get(url, timeout=10).json()
            for ticker in res.get("tickers", []):
                base = ticker.get("base")
                if base:
                    bybit_coins.add(base.upper())
    except Exception as e:
        print(f"Error fetching Bybit list: {e}")
    
    stocks = ['XNVDA', 'XTSLA', 'XAAPL', 'XMSFT', 'XAMZN', 'XGOOG', 'XMETA', 'XBRK', 'XLLY', 'XJPM', 'XSPCX', 'XCOIN']
    return bybit_coins, stocks

def get_market_data(symbol):
    url = "https://www.okx.com/api/v5/market/candles"
    params = {"instId": symbol, "bar": "15m", "limit": 20} 
    try:
        data = requests.get(url, params=params).json()["data"]
        closes = [float(k[4]) for k in data[1:]] 
        closes.reverse() 
        
        current_price = closes[-1]
        prev_close = closes[-2]
        
        gains = [max(0, closes[i] - closes[i-1]) for i in range(1, len(closes))]
        losses = [max(0, closes[i-1] - closes[i]) for i in range(1, len(closes))]
        avg_gain = sum(gains[-14:])/14
        avg_loss = sum(losses[-14:])/14
        rsi = 100.0 if avg_loss == 0 else round(100 - (100 / (1 + (avg_gain / avg_loss))), 2)
            
        ma5 = round(sum(closes[-5:]) / 5, 6)
        ma10 = round(sum(closes[-10:]) / 10, 6)
        recent_low = min(closes[-5:])
        
        return current_price, prev_close, rsi, ma5, ma10, recent_low
    except Exception:
        return None, None, None, None, None, None

def is_safe_trade(entry, sl, tp):
    risk = entry - sl
    reward = tp - entry
    if risk <= 0 or reward <= 0: return False
    return (reward / risk) >= 1.8

def run():
    print("Fetching Bybit listing data...")
    valid_bybit_coins, fallback_stocks = get_bybit_coins()
    
    print("Scanning Market (V5.1)...")
    url = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"
    tickers = requests.get(url).json()["data"]
    
    valid = []
    for t in tickers:
        if t['instId'].endswith('-USDT'):
            base_coin = t['instId'].split('-')[0]
            
            if base_coin.startswith('X') and 4 <= len(base_coin) <= 6: continue
            if base_coin in STABLECOINS: continue
            if base_coin in fallback_stocks: continue
            if len(valid_bybit_coins) > 0 and base_coin not in valid_bybit_coins: continue 
            
            vol = float(t['volCcy24h'])
            if vol >= 1000000: 
                last_price = float(t['last'])
                open_price = float(t['open24h'])
                change_24h = ((last_price - open_price) / open_price) * 100
                valid.append({'symbol': t['instId'], 'vol': vol, 'change': change_24h})
    
    valid.sort(key=lambda x: x['vol'], reverse=True)
    to_check = valid[15:50] 
    
    alert_text = ""
    found = 0
    
    for t in to_check:
        price, prev_close, rsi, ma5, ma10, recent_low = get_market_data(t['symbol'])
        if not price: continue
        
        # STATE 1: Bullish Pullback
        if t['change'] > 1.0 and 42 <= rsi <= 46 and price > ma5 and ma5 > ma10:
            safe_entry = ma5
            sl = round(ma10 * 0.99, 6) 
            tp_final = round(safe_entry * 1.06, 6) 
            
            if is_safe_trade(safe_entry, sl, tp_final):
                found += 1
                tp_10_percent = round(safe_entry * 1.10, 6)
                alert_text += f"🟢 *TREND PULLBACK*\n🪙 *{t['symbol']}*\n\n"
                alert_text += f"🎯 *Buy Zone (Limit):* {safe_entry}\n"
                alert_text += f"🔄 *Re-invest Zone:* {safe_entry}\n"
                alert_text += f"🛑 *Stop Loss:* {sl}\n\n"
                alert_text += f"📉 *PROFIT TAKING PLAN:*\n"
                alert_text += f"1️⃣ Price hits {tp_10_percent} (+10%): Sell 25%\n"
                alert_text += f"2️⃣ RSI hits 70: Sell 50%\n"
                alert_text += f"3️⃣ RSI hits 75-85: Sell 100%\n\n"
                alert_text += f"📊 *Current Price:* {price}\n"
                alert_text += f"📊 *RSI:* {rsi} | *MA5:* {ma5} | *MA10:* {ma10}\n\n"

        # STATE 2: Oversold Reversal
        elif t['change'] < -10.0 and rsi < 28 and price > prev_close:
            safe_entry = round(recent_low * 1.005, 6)
            sl = round(recent_low * 0.985, 6) 
            tp_final = round(safe_entry * 1.06, 6) 
            
            if is_safe_trade(safe_entry, sl, tp_final):
                found += 1
                tp_10_percent = round(safe_entry * 1.10, 6)
                alert_text += f"🩸 *OVERSOLD BOUNCE*\n🪙 *{t['symbol']}*\n\n"
                alert_text += f"🎯 *Buy Zone (Limit):* {safe_entry}\n"
                alert_text += f"🔄 *Re-invest Zone:* {safe_entry}\n"
                alert_text += f"🛑 *Stop Loss:* {sl}\n\n"
                alert_text += f"📉 *PROFIT TAKING PLAN:*\n"
                alert_text += f"1️⃣ Price hits {tp_10_percent} (+10%): Sell 25%\n"
                alert_text += f"2️⃣ RSI hits 70: Sell 50%\n"
                alert_text += f"3️⃣ RSI hits 75-85: Sell 100%\n\n"
                alert_text += f"📊 *Current Price:* {price}\n"
                alert_text += f"📊 *RSI:* {rsi} | *MA5:* {ma5} | *MA10:* {ma10}\n\n"

        # STATE 3: Early Breakout
        elif t['change'] > 3.0 and 50 <= rsi <= 58 and price > ma5 and ma5 > ma10:
            safe_entry = ma5
            sl = round(ma5 * 0.98, 6) 
            tp_final = round(safe_entry * 1.06, 6) 
            
            if is_safe_trade(safe_entry, sl, tp_final):
                found += 1
                tp_10_percent = round(safe_entry * 1.10, 6)
                alert_text += f"🚀 *EARLY BREAKOUT*\n🪙 *{t['symbol']}*\n\n"
                alert_text += f"🎯 *Buy Zone (Limit):* {safe_entry}\n"
                alert_text += f"🔄 *Re-invest Zone:* {safe_entry}\n"
                alert_text += f"🛑 *Stop Loss:* {sl}\n\n"
                alert_text += f"📉 *PROFIT TAKING PLAN:*\n"
                alert_text += f"1️⃣ Price hits {tp_10_percent} (+10%): Sell 25%\n"
                alert_text += f"2️⃣ RSI hits 70: Sell 50%\n"
                alert_text += f"3️⃣ RSI hits 75-85: Sell 100%\n\n"
                alert_text += f"📊 *Current Price:* {price}\n"
                alert_text += f"📊 *RSI:* {rsi} | *MA5:* {ma5} | *MA10:* {ma10}\n\n"

    if found == 0:
        alert_text = "🛑 No safe Bybit setups found (R:R > 1:1.8)."
    else:
        alert_text = "🛡️ *V5.1 TRADE MANAGER ALERTS*\n\n" + alert_text
            
    print(alert_text)
    send_telegram(alert_text)

run()
