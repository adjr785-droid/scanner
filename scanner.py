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
        closes.reverse() # Oldest to newest
        
        current_price = closes[-1]
        prev_close = closes[-2]
        
        # Calculate RSI
        gains = [max(0, closes[i] - closes[i-1]) for i in range(1, len(closes))]
        losses = [max(0, closes[i-1] - closes[i]) for i in range(1, len(closes))]
        avg_gain = sum(gains[-14:])/14
        avg_loss = sum(losses[-14:])/14
        rsi = 100.0 if avg_loss == 0 else round(100 - (100 / (1 + (avg_gain / avg_loss))), 2)
            
        # Calculate MAs
        ma5 = round(sum(closes[-5:]) / 5, 6)
        ma10 = round(sum(closes[-10:]) / 10, 6)
        recent_low = min(closes[-5:]) # Lowest price in the last 5 candles
        
        return current_price, prev_close, rsi, ma5, ma10, recent_low
    except Exception:
        return None, None, None, None, None, None

def run():
    print("Scanning Market (State Machine V4.0)...")
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
                
                valid.append({
                    'symbol': t['instId'], 
                    'vol': vol, 
                    'change': change_24h
                })
    
    # Sort by highest volume and check the top 50 coins
    valid.sort(key=lambda x: x['vol'], reverse=True)
    to_check = valid[:50] 
    
    alert_text = ""
    found = 0
    
    for t in to_check:
        price, prev_close, rsi, ma5, ma10, recent_low = get_market_data(t['symbol'])
        if not price: continue
        
        # ==========================================
        # STATE 1: Bullish Pullback (Safe Trend Continuation)
        # ==========================================
        if t['change'] > 1.0 and 42 <= rsi <= 46 and price > ma5 and ma5 > ma10:
            found += 1
            sl = round(ma10 * 0.995, 6) # SL just below MA10
            tp = round(price * 1.025, 6) # 2.5% Target
            alert_text += f"🟢 *TREND PULLBACK*\n🪙 *{t['symbol']}*\n"
            alert_text += f"💰 Entry: {price}\n🛑 Stop Loss: {sl}\n🎯 Take Profit: {tp}\n"
            alert_text += f"📊 RSI: {rsi} | Vol: ${t['vol']/1000000:.1f}M\n\n"

        # ==========================================
        # STATE 2: Oversold Reversal (Knife Catch)
        # ==========================================
        elif t['change'] < -8.0 and rsi < 30 and price > prev_close:
            found += 1
            sl = round(recent_low * 0.99, 6) # SL just below recent low
            tp = round(ma10, 6) # Target is the MA10 resistance
            alert_text += f"🩸 *OVERSOLD BOUNCE*\n🪙 *{t['symbol']}*\n"
            alert_text += f"💰 Entry: {price}\n🛑 Stop Loss: {sl}\n🎯 Take Profit: {tp}\n"
            alert_text += f"📊 RSI: {rsi} | 24H: {t['change']:.1f}%\n\n"

        # ==========================================
        # STATE 3: Momentum Breakout (Ride the Wave)
        # ==========================================
        elif t['change'] > 5.0 and 55 <= rsi <= 72 and price > ma5 and ma5 > ma10:
            found += 1
            sl = round(ma5 * 0.995, 6) # SL just below MA5
            tp = round(price * 1.04, 6) # 4% Target
            alert_text += f"🚀 *MOMENTUM BREAKOUT*\n🪙 *{t['symbol']}*\n"
            alert_text += f"💰 Entry: {price}\n🛑 Stop Loss: {sl}\n🎯 Take Profit: {tp}\n"
            alert_text += f"📊 RSI: {rsi} | 24H: +{t['change']:.1f}%\n\n"
            
        # OTHERWISE: No state triggered. Do nothing.

    if found == 0:
        alert_text = "🛑 No market states triggered on 15m. Waiting for setups."
    else:
        alert_text = "🎯 *V4.0 MARKET ALERTS*\n\n" + alert_text
            
    print(alert_text)
    send_telegram(alert_text)

run()
