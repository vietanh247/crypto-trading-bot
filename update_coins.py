import requests
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def get_top_coins():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        'vs_currency': 'usd',
        'order': 'market_cap_desc',
        'per_page': 30,
        'page': 1,
        'sparkline': False
    }
    response = requests.get(url, params=params)
    coins = response.json()
    return [coin['symbol'].upper() for coin in coins]

def update_database(coins):
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    supabase = create_client(supabase_url, supabase_key)
    
    data = {"id": 1, "coins": coins}
    supabase.table("top_coins").upsert(data).execute()

if __name__ == "__main__":
    top_coins = get_top_coins()
    update_database(top_coins)
    print(f"Updated top coins: {top_coins}")