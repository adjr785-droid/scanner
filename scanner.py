import requests
import json
import os
import time

TOKEN = "9171870506:AAFvZn7HBBtnhIkJ2fFfvr1cB6JRWwPepic"
CHAT_ID = "8902758637" 
DB_FILE = "positions.json"
STATE_FILE = "tg_state.json"

STABLECOINS = ['USDC', 'USDT', 'DAI', 'FDUSD', 'TUSD', 'USDD', 'USDE', 'ONE', 'CT']

def get_ath_atl(coin_symbol):
    try:
        search_url = f"https://api.coingecko.com/api/v3/search?query={coin_symbol}"
        search_res = requests.get(search_url, timeout=10).json()
        if not search_res.get('coins'): return None, None
        coin_id = search_res['coins'][0]['id']
        market_url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={coin_id}"
        market_res = requests.get(market_url, timeout=10).json()
        if market_res: return market_res[0].get('ath'), market_res[0].get('atl')
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

def check_telegram_commands():
    state = load_json(STATE_FILE)
    last_id = state.get("last_update_id", 0)
    
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_id + 1}"
    try:
        res = requests.get(url, timeout=10).json()
        if res.get("ok") and len(res.get("result", [])) > 0:
            for update in res["result"]:
                last_id = update["update_id"]
                if "message" in update and "text" in update["message"]:
                    text = update["message"]["text"].lower()
                    
                    if text.startswith("/rsi"):
                        parts = text.split()
                        if len(parts) > 1:
                            coin = parts[1].upper().replace("USDT", "").replace("-", "")
                            symbol = f"{coin}-USDT"
                            
                            price, _, rsi, ma5, ma10, _ = get_market_data(symbol)
                            if rsi:
                                trend = "🟢 BULLISH" if price > ma5 > ma10 else ("🔴 BEARISH" if price < ma5 < ma10 else "🟡 CHOPPY")
                                send_telegram(f"📊 *{coin}* (1H Chart)\n💰 Price: `{price}`\n📈 RSI: `{rsi}`\n\n📉 MA5: `{ma5}`\n📉 MA10: `{ma10}`\n⚖️ Trend: {trend}")
                            else:
                                send_telegram(f"❌ Could not fetch data for `{coin}`.")
                        else:
                            send_telegram("❌ Please specify a coin. Example: `/rsi BTC`")

                    elif text.startswith("/scan"):
                        parts = text.split()
                        if len(parts) == 3:
                            try:
                                min_rsi = float(parts[1])
                                max_rsi = float(parts[2])
                                send_telegram(f"🔍 Scanning Top 30 coins for RSI between {min_rsi} and {max_rsi}... (Wait 15s)")
                                
                                url = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"
                                tickers = requests.get(url).json()["data"]
                                
                                valid = [t for t in tickers if t['instId'].endswith('-USDT') and float(t['volCcy24h']) >= 5000000]
                                valid.sort(key=lambda x: float(x['volCcy24h']), reverse=True)
                                to_check = valid[:30] 
                                
                                results = []
                                for t in to_check:
                                    coin_name = t['instId'].split('-')[0]
                                    if coin_name in STABLECOINS: continue
                                    
                                    price, _, rsi, ma5, ma10, _ = get_market_data(t['instId'])
                                    if rsi and min_rsi <= rsi <= max_rsi:
                                        results.append(f"🪙 *{coin_name}*: RSI {rsi} (Price: {price})")
                                
                                if results:
                                    response = f"📊 *RSI RESULTS ({min_rsi} - {max_rsi})*\n\n" + "\n".join(results[:10])
                                    if len(results) > 10:
                                        response += f"\n\n*...and {len(results) - 10} more.*"
                                    send_telegram(response)
                                else:
                                    send_telegram(f"🛑 No top-30 coins found with RSI between {min_rsi} and {max_rsi}.")
                                    
                            except ValueError:
                                send_telegram("❌ Invalid format. Use: `/scan 30 40`")
                        else:
                            send_telegram("❌ Use format: `/scan [min] [max]`.")

                    elif "/status" in text:
                        db = load_json(DB_FILE)
                        if not db:
                            send_telegram("🛑 *STATUS:* Memory is empty. The bot is hunting.")
                        else:
                            for sym, data in db.items():
                                price, _, rsi, _, _, _ = get_market_data(sym)
                                if price:
                                    inc = ((price - data['entry_price']) / data['entry_price']) * 100
                                    send_telegram(f"🟢 *ACTIVE:* {sym}\n💰 Entry: {data['entry_price']}\n📊 Current: {price} ({inc:+.1f}%)\n🎯 RSI: {rsi}")
                                    
                    elif "/clear" in text:
                        save_json(DB_FILE, {})
                        send_telegram("🧹 *MEMORY CLEARED!* The bot will start scanning for a new setup.")
                        
                    elif "/help" in text:
                        send_telegram("🤖 *COMMANDS:*\n/status - Check trades\n/rsi BTC - Get live RSI\n/scan 30 40 - Find coins in an RSI range\n/clear - Wipe memory\n/help - Menu")
            
            state["last_update_id"] = last_id
            save_json(STATE_FILE, state)
            
    except Exception as e:
        print(f"⚠️ TELEGRAM ERROR: {e}") 

def manage_active_trades():
    db = load_json(DB_FILE)
    if not db: return
    
    for symbol, data in list(db.items()):
        price, prev, rsi, ma5, ma10, recent_low = get_market_data(symbol)
        if not price: continue
        
        entry = data["entry_price"]
        increase = ((price - entry) / entry) * 100
        
        # CATASTROPHE STOP LOSS (20% drop)
        if price <= data["stop_loss"]:
            send_telegram(f"🩸 *CATASTROPHE STOP LOSS HIT*\n🪙 *{symbol}* dropped 20% to {price}.\n\nExit the trade. Removing from memory.")
            del db[symbol] 
            continue

        if rsi >= 75:
            send_telegram(f"🚨 *SELL 100% NOW*\n🪙 *{symbol}* hit RSI {rsi}!\n💰 Price: {price}")
            del db[symbol] 
            continue
        elif rsi >= 70 and not data.get("took_profit_50"):
            send_telegram(f"🎯 *SELL 50% NOW*\n🪙 *{symbol}* hit RSI {rsi}!\n💰 Price: {price}")
            db[symbol]["took_profit_50"] = True
        elif increase >= 10.0 and not data.get("took_profit_10"):
            send_telegram(f"💰 *SELL 25% NOW*\n🪙 *{symbol}* is up +{increase:.1f}%!\n💰 Price: {price}")
            db[symbol]["took_profit_10"] = True

        if (db[symbol].get("took_profit_10") or db[symbol].get("took_profit_50")) and price <= data["safe_zone"]:
            send_telegram(f"🔄 *RE-INVEST ALERT*\n🪙 *{symbol}* dropped back to Safe Zone ({data['safe_zone']}).\n💰 Price: {price}")
            db[symbol]["took_profit_10"] = False
            db[symbol]["took_profit_50"] = False
            
    save_json(DB_FILE, db)

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
        
        # STATE 1: TREND PULLBACK
        if t['change'] > 1.0 and 42 <= rsi <= 48 and price > ma5 and ma5 > ma10:
            safe_entry = ma5
            # WIDER 20% STOP LOSS
            sl = round(ma5 * 0.80, 6) 
            tp1 = round(safe_entry * 1.10, 6)
            tp2 = round(safe_entry * 1.20, 6) 
            rr = (tp1 - safe_entry) / (safe_entry - sl) if (safe_entry - sl) > 0 else 0
            if rr >= 1.8:
                candidates.append({"symbol": t['symbol'], "type": "TREND PULLBACK", "entry": safe_entry, "sl": sl, "tp1": tp1, "tp2": tp2, "rsi": rsi, "vol": t['vol'], "rr": rr})

        # STATE 2: OVERSOLD BOUNCE
        elif t['change'] < -8.0 and rsi < 30 and price > prev:
            safe_entry = round(recent_low * 1.005, 6)
            # WIDER 20% STOP LOSS
            sl = round(recent_low * 0.80, 6)          
            tp1 = round(safe_entry * 1.10, 6)          
            tp2 = round(safe_entry * 1.20, 6)
            rr = (tp1 - safe_entry) / (safe_entry - sl) if (safe_entry - sl) > 0 else 0
            if rr >= 1.8:
                candidates.append({"symbol": t['symbol'], "type": "OVERSOLD BOUNCE", "entry": safe_entry, "sl": sl, "tp1": tp1, "tp2": tp2, "rsi": rsi, "vol": t['vol'], "rr": rr})
                
    candidates.sort(key=lambda x: (x['vol'], x['rr']), reverse=True)
    
    if candidates:
        best = candidates[0] 
        coin_symbol = best['symbol'].split('-')[0] 
        
        ath, atl = get_ath_atl(coin_symbol)
        ath_str = f"${ath:.4f}" if ath else "N/A"
        atl_str = f"${atl:.4f}" if atl else "N/A"
        
        icon = "🏆" if best['type'] == "TREND PULLBACK" else "🩸"
        
        msg = (
            f"{icon} *{best['type']}*\n"
            f"🪙 *{best['symbol']}*\n\n"
            f"🎯 *Entry:* {best['entry']}\n"
            f"🛑 *Catastrophe SL:* {best['sl']} (20%)\n"
            f"💰 *TP1:* {best['tp1']} (10%)\n"
            f"💰 *TP2:* {best['tp2']} (20%)\n\n"
            f"📊 *RSI:* {best['rsi']} | *R:R:* 1:{best['rr']:.1f}\n"
            f"📈 *ATH:* {ath_str}\n"
            f"📉 *ATL:* {atl_str}"
        )
        send_telegram(msg)
        
        db[best['symbol']] = {
            "entry_price": best['entry'], "safe_zone": best['entry'], 
            "stop_loss": best['sl'], # Now a 20% drop
            "took_profit_10": False, "took_profit_50": False
        }
        save_json(DB_FILE, db)

if __name__ == "__main__":
    check_telegram_commands() 
    manage_active_trades()    
    scan_for_new_trades()     
