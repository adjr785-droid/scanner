import requests

TOKEN = "9171870506:AAFvZn7HBBtnhIkJ2fFfvr1cB6JRWwPepic"
CHAT_ID = "8902758637" 

STABLECOINS = ['USDC', 'USDT', 'DAI', 'FDUSD', 'TUSD', 'USDD', 'USDE']

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def get_indicators(symbol):
    url = "https://www.okx.com/api/v5/market/candles"
    params = {"instId": symbol, "bar": "15m", "limit": 20} 
    try:
        data = requests.get(url, params=params).json()["data"]
        closes = [float(k[4]) for k in data[1:]] # Drop live candle
        closes.reverse()
        
        # 1. Calculate RSI
        gains = [max(0, closes[i] - closes[i-1]) for i in range(1, len(closes))]
        losses = [max(0, closes[i-1] - closes[i]) for i in range(1, len(closes))]
        avg_gain = sum(gains[-14:])/14
        avg_loss = sum(losses[-14:])/14
        if avg_loss == 0: 
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = round(100 - (100 / (1 + rs)), 2)
            
        # 2. Calculate MAs
        ma5 = round(sum(closes[-5:]) / 5, 4)
        ma10 = round(sum(closes[-10:]) / 10, 4)
        
        return rsi, ma5, ma10
    except Exception:
        return None, None, None

def run():
    print("Scanning Market for Pullbacks (15m + MA)...")
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
                
                if change_24h > 1.0:
                    valid.append({
                        'symbol': t['instId'], 
                        'vol': vol, 
                        'change': change_24h
                    })
    
    valid.sort(key=lambda x: x['vol'], reverse=True)
    strong_alts = valid[15:50]
    strong_alts.sort(key=lambda x: x['change'], reverse=True)
    
    to_check = strong_alts[:3]
    
    pump_text = "📉 *DIP SCANNER (RSI + MA)*\n_(Check these on Bybit)_\n\n"
    found = 0
    
    for t in to_check:
        rsi, ma5, ma10 = get_indicators(t['symbol'])
        
        # RULE: RSI 42-46 AND MA5 must be above MA10 (Uptrend)
        if rsi and 42 <= rsi <= 46 and ma5 > ma10:
            found += 1
            pump_text += f"🟢 *{t['symbol']}*\n"
            pump_text += f"📈 24H Change: +{t['change']:.1f}%\n"
            pump_text += f"📊 RSI: {rsi} | MA5: {ma5} | MA10: {ma10}\n"
            pump_text += f"💵 Volume: ${t['vol']/1000000:.1f}M | *15m*\n\n"
    
    if found == 0:
        # ADDED "on 15m" TO THE END HERE
        pump_text = "🛑 No strong altcoins currently in the 42-46 RSI zone with an uptrend (MA5 > MA10) on *15m*."
            
    print(pump_text)
    send_telegram(pump_text)
    print("Done! Check your phone.")

run()
