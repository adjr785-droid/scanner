import requests
import json
import os

TOKEN = "9171870506:AAFvZn7HBBtnhIkJ2fFfvr1cB6JRWwPepic"
CHAT_ID = "8902758637" 
DB_FILE = "positions.json"

STABLECOINS = ['USDC', 'USDT', 'DAI', 'FDUSD', 'TUSD', 'USDD', 'USDE']

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
        
        gains = [max(0, closes[i] - closes[i-1]) for i in range(1, len(closes))]
        losses = [max(0, closes[i-1] - closes[i]) for i in range(1, len(closes))]
        avg_gain = sum(gains[-14:])/14
        avg_loss = sum(losses[-14:])/14
        rsi = 100.0 if avg_loss == 0 else round(100 - (100 / (1 + (avg_gain / avg_loss))), 2)
            
        ma5 = round(sum(closes[-5:]) / 5, 6)
        ma10 = round(sum(closes[-10:]) / 10, 6)
        return current_price, prev_close, rsi, ma5, ma10
    except Exception:
        return None, None, None, None, None

def is_safe_trade(entry, sl, tp):
    risk = entry - sl
    reward = tp - entry
    if risk <= 0 or reward <= 0: return False
    return (reward / risk) >= 1.8

def manage_active_trades():
    db = load_db()
    if not db: return
    
    for symbol, data in list(db.items()):
        price, prev, rsi, ma5, ma10 = get_market_data(symbol)
        if not price: continue
        
        entry = data["entry_price"]
        safe_zone = data["safe_zone"]
        sl = data["stop_loss"] # NEW: Track the stop loss
        increase = ((price - entry) / entry) * 100
        
        # --- STOP LOSS RULE (The "Alternative") ---
        if price <= sl:
            send_telegram(f"🩸 *STOP LOSS HIT*\n🪙 *{symbol}* has dropped to {price}.\n\nExit the trade on Bybit. Removing from memory to search for new alternatives.")
            del db[symbol] # Remove from memory so the bot can find a better alternative
            continue

        # --- TAKE PROFIT RULES ---
        if rsi >= 75:
            send_telegram(f"🚨 *SELL 100% NOW*\n🪙 *{symbol}* has hit RSI {rsi}!\n💰 Current Price: {price}")
            del db[symbol] 
            continue
            
        elif rsi >= 70 and not data.get("took_profit_50"):
            send_telegram(f"🎯 *SELL 50% NOW*\n🪙 *{symbol}* has hit RSI {rsi}!\n💰 Current Price: {price}")
            db[symbol]["took_profit_50"] = True
            
        elif increase >= 10.0 and not data.get("took_profit_10"):
            send_telegram(f"💰 *SELL 25% NOW*\n🪙 *{symbol}* is up +{increase:.1f}%!\n💰 Current Price: {price}")
            db[symbol]["took_profit_10"] = True

        # --- RE-INVEST RULE ---
        if (db[symbol].get("took_profit_10") or db[symbol].get("took_profit_50")) and price <= safe_zone:
            send_telegram(f"🔄 *RE-INVEST ALERT*\n🪙 *{symbol}* has dropped back to the Safe Zone ({safe_zone}).\n💰 Current Price: {price}")
            db[symbol]["took_profit_10"] = False
            db[symbol]["took_profit_50"] = False
            
    save_db(db)

def scan_for_new_trades():
    db = load_db()
    
    # If we already have 3 active trades, don't take more risk
    if len(db) >= 3:
        print("Max active trades reached. Managing existing positions only.")
        return

    url = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"
    tickers = requests.get(url).json()["data"]
    
    valid = []
    for t in tickers:
        if t['instId'].endswith('-USDT'):
            base = t['instId'].split('-')[0]
            if base in STABLECOINS or (base.startswith('X') and len(base) <= 6): continue
            vol = float(t['volCcy24h'])
            if vol >= 1000000: 
                change = ((float(t['last']) - float(t['open24h'])) / float(t['open24h'])) * 100
                valid.append({'symbol': t['instId'], 'vol': vol, 'change': change})
                
    valid.sort(key=lambda x: x['vol'], reverse=True)
    to_check = valid[15:50] # SKIP TOP 15 MEGA-CAPS
    
    for t in to_check:
        if t['symbol'] in db: continue 
        
        price, prev, rsi, ma5, ma10 = get_market_data(t['symbol'])
        if not price: continue
        
        # STATE 3: Early Breakout
        if t['change'] > 3.0 and 50 <= rsi <= 58 and price > ma5 and ma5 > ma10:
            safe_entry = ma5
            sl = round(ma5 * 0.98, 6) 
            tp = round(safe_entry * 1.10, 6) 
            
            if is_safe_trade(safe_entry, sl, tp):
                msg = f"🚀 *NEW EARLY BREAKOUT*\n🪙 *{t['symbol']}*\n🎯 Entry: {safe_entry}\n🛑 SL: {sl}\n💰 TP: {tp}\n📊 RSI: {rsi}"
                send_telegram(msg)
                
                db[t['symbol']] = {
                    "entry_price": safe_entry,
                    "safe_zone": safe_entry,
                    "stop_loss": sl, # Saving the SL to memory
                    "took_profit_10": False,
                    "took_profit_50": False
                }
                save_db(db)

if __name__ == "__main__":
    manage_active_trades()
    scan_for_new_trades()
