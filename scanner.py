def manage_active_trades():
    db = load_db()
    if not db: return
    
    for symbol, data in list(db.items()):
        price, prev, rsi, ma5, ma10 = get_market_data(symbol)
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
