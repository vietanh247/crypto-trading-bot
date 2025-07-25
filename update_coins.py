import os
import requests
from supabase import create_client
from dotenv import load_dotenv
import logging
import sys
from datetime import datetime

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.basicConfig(
    level=logging.INFO,  # Đổi thành logging.DEBUG để xem chi tiết
    format=log_format,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot_debug.log')
    ]
)
logger = logging.getLogger('trading_bot')
logger.info("====== STARTING TRADING BOT ======")

def get_top_coins():
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            'vs_currency': 'usd',
            'order': 'market_cap_desc',
            'per_page': 30,
            'page': 1,
            'sparkline': False
        }
        response = requests.get(url, params=params)
        response.raise_for_status()  # Kiểm tra lỗi HTTP
        coins = response.json()
        return [coin['symbol'].upper() for coin in coins]
    except Exception as e:
        logging.error(f"Lỗi khi lấy top coins: {str(e)}")
        return []

def update_database(coins):
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        
        # Kiểm tra biến môi trường
        if not supabase_url or not supabase_key:
            logging.error("Thiếu biến môi trường SUPABASE_URL hoặc SUPABASE_KEY")
            return False
        
        supabase = create_client(supabase_url, supabase_key)
        
        # Kiểm tra kết nối Supabase
        response = supabase.table("top_coins").select("*").limit(1).execute()
        if hasattr(response, 'error') and response.error:
            logging.error(f"Lỗi kết nối Supabase: {response.error}")
            return False
        
        # Cập nhật dữ liệu
        data = {"id": 1, "coins": coins}
        result = supabase.table("top_coins").upsert(data).execute()
        
        if hasattr(result, 'error') and result.error:
            logging.error(f"Lỗi khi cập nhật database: {result.error}")
            return False
            
        return True
    except Exception as e:
        logging.error(f"Lỗi không xác định: {str(e)}")
        return False

if __name__ == "__main__":
    load_dotenv()  # Tải biến môi trường từ file .env
    
    logging.info("Bắt đầu cập nhật top coins...")
    top_coins = get_top_coins()
    
    if top_coins:
        logging.info(f"Top coins: {', '.join(top_coins)}")
        success = update_database(top_coins)
        if success:
            logging.info("Cập nhật database thành công!")
        else:
            logging.error("Cập nhật database thất bại")
    else:
        logging.error("Không lấy được danh sách coin")