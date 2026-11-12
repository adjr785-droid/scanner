import os
from pybit.unified_trading import HTTP

print("Connecting to Bybit...")

# Initialize the session using the GitHub Secrets
session = HTTP(
    testnet=True, # We are testing on Testnet first!
    api_key=os.environ.get("BYBIT_API_KEY"),
    api_secret=os.environ.get("BYBIT_API_SECRET")
)

try:
    # Ask Bybit for the wallet balance
    response = session.get_wallet_balance(accountType="UNIFIED")
    
    if response["retCode"] == 0:
        print("✅ SUCCESS! Connection established.")
        print("Here is your Testnet Wallet Balance:")
        
        # Print the USDT balance
        coins = response["result"]["list"][0]["coin"]
        for coin in coins:
            if coin["coin"] == "USDT":
                print(f"💰 USDT Balance: {coin['walletBalance']}")
    else:
        print(f"❌ FAILED: {response['retMsg']}")
except Exception as e:
    print(f"❌ ERROR: {e}")
