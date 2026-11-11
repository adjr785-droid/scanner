import requests

TOKEN = "9171870506:AAFvZn7HBBtnhIkJ2fFfvr1cB6JRWwPepic"
CHAT_ID = "8902758637" 

STABLECOINS = ['USDC', 'USDT', 'DAI', 'FDUSD', 'TUSD', 'USDD', 'USDE']

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def get_market_data(symbol):
    url = "https://www.okx.com/api/v5/market/candles"
    params = {"instId": symbol, "bar": "15m", "limit": 20} 
    try:
        data = requests.get(url, params=params).json()["data"]
        closes = [float(k[4]) for k in data[1:]] 
        closes.reverse() 
        
        current_price = closes[-1]
        prev_close = closes[-2]
        
        # RSI Calculation
        gains = [max(0, closes[i] - closes[i-1]) for i in range(1, len(closes))]
        losses = [max(0, closes[i-1] - closes[i]) for i in range(1, len(closes))]
        avg_gain = sum(gains[-14:])/14
        avg_loss = sum(losses[-14:])/14
        rsi = 100.0 if avg_loss == 0 else round(100 - (100 / (1 + (avg_gain / avg_loss))), 2)
            
        # MAs & Recent Low
        ma5 = round(sum(closes[-5:]) / 5, 6)
        ma10 = round(sum(closes[-10:]) / 10, 6)
        recent_low = min(closes[-5:])
        
        return current_price, prev_close, rsi, ma5, ma10, recent_low
    except Exception:
        return None, None, None, None, None, None

def is_safe_trade(entry, sl, tp):
    """Calculates Risk/Reward. ONLY returns True if R:R is 1:1.8 or better."""
    risk = entry - sl
    reward = tp - entry
    if risk <= 0 or reward <= 0: return False
    rr_ratio = reward / risk
    return rr_ratio >= 1.8

def run():
    print("Scanning Market (V4.5 Early Entries)...")
    url = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"
    tickers = requests.get(url).json()["data"]
    
    valid = []
    for t in tickers:
        if t['instId'].endswith('-USDT'):
            base_coin = t['instId'].split('-')[0]
            if base_coin in STABLECOINS: continue
            
            vol = float(t['volCcy24h'])
            if vol >= 5000000: 
                last_price = float(t['last'])
                open_price = float(t['open24h'])
                change_24h = ((last_price - open_price) / open_price) * 100
                valid.append({'symbol': t['instId'], 'vol': vol, 'change': change_24h})
    
    valid.sort(key=lambda x: x['vol'], reverse=True)
    to_check = valid[:50] 
    
    alert_text = ""
    found = 0
    
    for t in to_check:
        price, prev_close, rsi, ma5, ma10, recent_low = get_market_data(t['symbol'])
        if not price: continue
        
        # STATE 1: Bullish Pullback
        if t['change'] > 1.0 and 42 <= rsi <= 46 and price > ma5 and ma5 > ma10:
            safe_entry = ma5
            sl = round(ma10 * 0.99, 6) 
            tp = round(safe_entry * 1.05, 6) 
            
            if is_safe_trade(safe_entry, sl, tp):
                found += 1
                alert_text += f"🟢 *TREND PULLBACK*\n🪙 *{t['symbol']}*\n"
                alert_text += f"🎯 Entry (Limit): {safe_entry}\n🛑 SL: {sl}\n💰 TP: {tp}\n"
                alert_text += f"📊 RSI: {rsi}\n\n"

        # STATE 2: Oversold Reversal
        elif t['change'] < -10.0 and rsi < 28 and price > prev_close:
            safe_entry = round(recent_low * 1.005, 6)
            sl = round(recent_low * 0.985, 6) 
            tp = round(safe_entry * 1.06, 6) 
            
            if is_safe_trade(safe_entry, sl, tp):
                found += 1
                alert_text += f"🩸 *OVERSOLD BOUNCE*\n🪙 *{t['symbol']}*\n"
                alert_text += f"🎯 Entry (Limit): {safe_entry}\n🛑 SL: {sl}\n💰 TP: {tp}\n"
                alert_text += f"📊 RSI: {rsi} | 24H: {t['change']:.1f}%\n\n"

        # STATE 3: Early Breakout
        elif t['change'] > 3.0 and 50 <= rsi <= 58 and price > ma5 and ma5 > ma10:
            safe_entry = ma5
            sl = round(ma5 * 0.98, 6) 
            tp = round(safe_entry * 1.06, 6) 
            
            if is_safe_trade(safe_entry, sl, tp):
                found += 1
                alert_text += f"🚀 *EARLY BREAKOUT*\n🪙 *{t['symbol']}*\n"
                alert_text += f"🎯 Entry (Limit): {safe_entry}\n🛑 SL: {sl}\n💰 TP: {tp}\n"
                alert_text += f"📊 RSI: {rsi} | 24H: +{t['change']:.1f}%\n\n"

    if found == 0:
        alert_text = "🛑 No safe setups found (R:R must be > 1:1.8)."
    else:
        alert_text = "🛡️ *V4.5 SAFEST EARLY ALERTS*\n\n" + alert_text
            
    print(alert_text)
    send_telegram(alert_text)

run()
