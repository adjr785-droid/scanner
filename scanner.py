import requests
import json
import os
import time

TOKEN = "9171870506:AAFvZn7HBBtnhIkJ2fFfvr1cB6JRWwPepic"
CHAT_ID = "8902758637" 
DB_FILE = "positions.json"
STATE_FILE = "tg_state.json"

STABLECOINS = ['USDC', 'USDT', 'DAI', 'FDUSD', 'TUSD', 'USDD', 'USDE', 'ONE', 'CT']

# --- COINGECKO ATH / ATL HELPER ---
def get_ath_atl(coin_symbol):
    """Fetches ATH and ATL from CoinGecko using the coin symbol."""
    try:
        # Search for the coin ID by symbol
        search_url = f"https://api.coingecko.com/api/v3/search?query={coin_symbol}"
        search_res = requests.get(search_url, timeout=10).json()
        
        if not search_res.get('coins'):
            return None, None
        
        # Take the first matching coin ID
        coin_id = search_res['coins'][0]['id']
        
        # Fetch full market data for that coin
        market_url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={coin_id}"
        market_res = requests.get(market_url, timeout=10).json()
        
        if market_res:
            return market_res[0].get('ath'), market_res[0].get('atl')
        return None, None
    except Exception:
        return None, None

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def load_json(file):
    if not os.path.exists(file): return {}
    with open(file, "r") as f: return json.load(f)

def save_json(file, data):
    with open(file, "w") as f: json.dump(data, f, indent=4)

def get_market_data(symbol):
    url = "https://www.okx.com/api/v5/market/candles"
    params = {"instId": symbol, "bar": "1H", "limit": 50} 
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
        return current_price, prev_close, rsi, ma5, ma10, min(closes[-5:])
    except Exception:
        return None, None, None, None, None, None

# --- TELEGRAM COMMANDS (Unchanged from previous Bybit version) ---
def check_telegram_commands():
    # ... (Your existing Telegram command logic: /rsi, /scan, /status, /clear, /help) ...
    # No changes needed here for the scanner.
    pass

# --- TRADE MANAGEMENT (Unchanged) ---
def manage_active_trades():
    # ... (Your existing profit-taking logic) ...
    pass

# --- SCANNER ---
def scan_for_new_trades():
    db = load_json(DB_FILE)
    if len(db) >= 1: return 

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
    to_check = valid[15:50] 
    
    candidates = []
    
    for t in to_check:
        price, prev, rsi, ma5, ma10, recent_low = get_market_data(t['symbol'])
        if not price: continue
        
        # Strategy 1: Trend Pullback
        if t['change'] > 1.0 and 42 <= rsi <= 48 and price > ma5 and ma5 > ma10:
            safe_entry = ma5
            sl = round(ma5 * 0.95, 6) 
            tp1 = round(safe_entry * 1.10, 6) 
            tp2 = round(safe_entry * 1.20, 6) # NEW: TP2 at +20%
            rr = (tp1 - safe_entry) / (safe_entry - sl) if (safe_entry - sl) > 0 else 0
            if rr >= 1.8:
                candidates.append({
                    "symbol": t['symbol'], "type": "TREND PULLBACK",
                    "entry": safe_entry, "sl": sl, "tp1": tp1, "tp2": tp2,
                    "rsi": rsi, "vol": t['vol'], "rr": rr
                })

        # Strategy 2: Oversold Bounce
        elif t['change'] < -8.0 and rsi < 30 and price > prev:
            safe_entry = round(recent_low * 1.005, 6)
            sl = round(recent_low * 0.98, 6)          
            tp1 = round(safe_entry * 1.10, 6)          
            tp2 = round(safe_entry * 1.20, 6) # NEW: TP2 at +20%
            rr = (tp1 - safe_entry) / (safe_entry - sl) if (safe_entry - sl) > 0 else 0
            if rr >= 1.8:
                candidates.append({
                    "symbol": t['symbol'], "type": "OVERSOLD BOUNCE",
                    "entry": safe_entry, "sl": sl, "tp1": tp1, "tp2": tp2,
                    "rsi": rsi, "vol": t['vol'], "rr": rr
                })
                
    candidates.sort(key=lambda x: (x['vol'], x['rr']), reverse=True)
    
    if candidates:
        best = candidates[0] 
        coin_symbol = best['symbol'].split('-')[0] # Extract "LINK" from "LINK-USDT"
        
        # Fetch ATH/ATL from CoinGecko
        ath, atl = get_ath_atl(coin_symbol)
        ath_str = f"${ath:.4f}" if ath else "N/A"
        atl_str = f"${atl:.4f}" if atl else "N/A"
        
        icon = "🏆" if best['type'] == "TREND PULLBACK" else "🩸"
        msg = (
            f"{icon} *{best['type']}*\n"
            f"🪙 *{best['symbol']}*\n\n"
            f"🎯 *Entry:* {best['entry']}\n"
            f"🛑 *Stop Loss:* {best['sl']} (5%)\n"
            f"💰 *TP1:* {best['tp1']} (10%)\n"
            f"💰 *TP2:* {best['tp2']} (20%)\n\n"
            f"📊 *RSI:* {best['rsi']} | *R:R:* 1:{best['rr']:.1f}\n"
            f"📈 *ATH:* {ath_str}\n"
            f"📉 *ATL:* {atl_str}"
        )
        send_telegram(msg)
        
        # Save to memory (TP2 and ATH/ATL are not stored for trade management)
        db[best['symbol']] = {
            "entry_price": best['entry'], "safe_zone": best['entry'], "stop_loss": best['sl'],
            "took_profit_10": False, "took_profit_50": False, "last_investment_time": int(time.time())
        }
        save_json(DB_FILE, db)

if __name__ == "__main__":
    check_telegram_commands() 
    manage_active_trades()    
    scan_for_new_trades()
