import requests
import json
import os
import time

TOKEN = "9171870506:AAFvZn7HBBtnhIkJ2fFfvr1cB6JRWwPepic"
CHAT_ID = "8902758637" 
DB_FILE = "positions.json"

# 'ONE' is blacklisted to prevent errors
STABLECOINS = ['USDC', 'USDT', 'DAI', 'FDUSD', 'TUSD', 'USDD', 'USDE', 'ONE']

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def load_db():
    if not os.path.exists(DB_FILE): return {}
    with open(DB_FILE, "r") as f: return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)

def get_market_data(symbol):
    url = "https://www.okx.com/api/v5/market/candles"
    params = {"instId": symbol, "bar": "15m", "limit": 20} 
    try:
        data = requests.get(url, params=params).json()["data"]
        closes = [float(k[4]) for k in data[1:]] 
        closes.reverse() 
        
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
        
        # Calculate Recent Low (for oversold stop loss)
        recent_low = min(closes[-5:])
        
        return current_price, prev_close, rsi, ma5, ma10, recent_low
    except Exception:
        return None, None, None, None, None, None

def manage_active_trades():
    db = load_db()
    if not db: return
    
    for symbol, data in list(db.items()):
        price, prev, rsi, ma5, ma10, recent_low = get_market_data(symbol)
        if not price: continue
        
        entry = data["entry_price"]
        safe_zone = data["safe_zone"]
        sl = data["stop_loss"]
        increase = ((price - entry) / entry) * 100
        
        # --- VARIABLE MONTHLY DCA REMINDER (30 Days) ---
        current_time = int(time.time())
        last_invested = data.get("last_investment_time", current_time)
        days_since = (current_time - last_invested) / (60 * 60 * 24)
        
        if days_since >= 30:
            send_telegram(f"📅 *MONTHLY DCA REMINDER*\n🪙 *{symbol}* is still active.\n\nIt has been 30 days. Time to add funds for your monthly DCA (Variable Amount).\n*(Check your portfolio and decide your investment size).*")
            db[symbol]["last_investment_time"] = current_time
            
        # --- STOP LOSS HIT ---
        if price <= sl:
            send_telegram(f"🩸 *STOP LOSS HIT*\n🪙 *{symbol}* dropped to {price}.\n\nExit the trade. Removing from memory to hunt for the next best setup.")
            del db[symbol] 
            continue

        # --- TAKE PROFIT RULES ---
        if rsi >= 75:
            send_telegram(f"🚨 *SELL 100% NOW*\n🪙 *{symbol}* hit RSI {rsi}!\n💰 Price: {price}\n\nRemoving from memory to find the next winner.")
            del db[symbol] 
            continue
        elif rsi >= 70 and not data.get("took_profit_50"):
            send_telegram(f"🎯 *SELL 50% NOW*\n🪙 *{symbol}* hit RSI {rsi}!\n💰 Price: {price}")
            db[symbol]["took_profit_50"] = True
        elif increase >= 10.0 and not data.get("took_profit_10"):
            send_telegram(f"💰 *SELL 25% NOW*\n🪙 *{symbol}* is up +{increase:.1f}%!\n💰 Price: {price}")
            db[symbol]["took_profit_10"] = True

        # --- RE-INVEST RULE ---
        if (db[symbol].get("took_profit_10") or db[symbol].get("took_profit_50")) and price <= safe_zone:
            send_telegram(f"🔄 *RE-INVEST ALERT*\n🪙 *{symbol}* dropped back to Safe Zone ({safe_zone}).\n💰 Price: {price}")
            db[symbol]["took_profit_10"] = False
            db[symbol]["took_profit_50"] = False
            
    save_db(db)

def scan_for_new_trades():
    db = load_db()
    
    # ONLY ALLOW 1 ACTIVE TRADE AT A TIME
    if len(db) >= 1: 
        return 

    url = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"
    tickers = requests.get(url).json()["data"]
    
    valid = []
    for t in tickers:
        if t['instId'].endswith('-USDT'):
            base = t['instId'].split('-')[0]
            # Filter X-stocks and blacklisted coins
            if base in STABLECOINS or (base.startswith('X') and len(base) <= 6): continue
            
            vol = float(t['volCcy24h'])
            if vol >= 1000000: 
                change = ((float(t['last']) - float(t['open24h'])) / float(t['open24h'])) * 100
                valid.append({'symbol': t['instId'], 'vol': vol, 'change': change})
                
    valid.sort(key=lambda x: x['vol'], reverse=True)
    
    # Skip Top 15 Mega-Caps
    to_check = valid[15:50]
    
    candidates = []
    
    for t in to_check:
        price, prev, rsi, ma5, ma10, recent_low = get_market_data(t['symbol'])
        if not price: continue
        
        # --- STRATEGY 1: BULLISH PULLBACK (RSI 42-48) ---
        if t['change'] > 1.0 and 42 <= rsi <= 48 and price > ma5 and ma5 > ma10:
            safe_entry = ma5
            sl = round(ma5 * 0.96, 6) 
            tp = round(safe_entry * 1.10, 6) 
            
            risk = safe_entry - sl
            reward = tp - safe_entry
            rr_ratio = reward / risk if risk > 0 else 0
            
            if rr_ratio >= 1.8:
                candidates.append({
                    "symbol": t['symbol'], "type": "TREND PULLBACK",
                    "entry": safe_entry, "sl": sl, "tp": tp,
                    "rsi": rsi, "vol": t['vol'], "rr": rr_ratio
                })

        # --- STRATEGY 2: OVERSOLD BOUNCE (RSI < 30 + Green Candle) ---
        elif t['change'] < -8.0 and rsi < 30 and price > prev:
            safe_entry = round(recent_low * 1.005, 6) # Buy slightly above the low
            sl = round(recent_low * 0.98, 6)          # Stop loss 2% below the low
            tp = round(safe_entry * 1.10, 6)          # 10% Target
            
            risk = safe_entry - sl
            reward = tp - safe_entry
            rr_ratio = reward / risk if risk > 0 else 0
            
            if rr_ratio >= 1.8:
                candidates.append({
                    "symbol": t['symbol'], "type": "OVERSOLD BOUNCE",
                    "entry": safe_entry, "sl": sl, "tp": tp,
                    "rsi": rsi, "vol": t['vol'], "rr": rr_ratio
                })
                
    # Rank by Volume (safest) and R:R (most profitable)
    candidates.sort(key=lambda x: (x['vol'], x['rr']), reverse=True)
    
    # ONLY SEND THE ABSOLUTE BEST TOKEN
    if candidates:
        best = candidates[0] 
        
        icon = "🏆" if best['type'] == "TREND PULLBACK" else "🩸"
        
        msg = f"{icon} *{best['type']}*\n🪙 *{best['symbol']}*\n🎯 Entry: {best['entry']}\n🛑 SL: {best['sl']}\n💰 TP: {best['tp']}\n📊 RSI: {best['rsi']} | R:R: 1:{best['rr']:.1f}"
        send_telegram(msg)
        
        db[best['symbol']] = {
            "entry_price": best['entry'],
            "safe_zone": best['entry'],
            "stop_loss": best['sl'],
            "took_profit_10": False,
            "took_profit_50": False,
            "last_investment_time": int(time.time())
        }
        save_db(db)

if __name__ == "__main__":
    manage_active_trades()
    scan_for_new_trades()
