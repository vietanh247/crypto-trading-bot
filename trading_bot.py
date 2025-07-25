import os
import time
import requests
import pandas as pd
import pandas_ta as ta
import numpy as np
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client

# ======= CẤU HÌNH LOGGING CHI TIẾT ========
log_format = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot_debug.log')
    ]
)

# Tạo logger riêng cho ứng dụng
logger = logging.getLogger('trading_bot')
logger.info("====== STARTING TRADING BOT ======")

# Fix lỗi pandas_ta
if 'NaN' not in sys.modules:
    sys.modules['NaN'] = np.nan
    logger.info("Patched NaN module")

# Load biến môi trường
load_dotenv()

# ======= HÀM GỬI TELEGRAM ALERT ========
def send_telegram_alert(message):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        logger.error("Missing Telegram credentials in environment variables")
        return None
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown'
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"Telegram message sent successfully")
        return response.json()
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {str(e)}")
        return None

# ======= KIỂM TRA KẾT NỐI TELEGRAM ========
def test_telegram_connection():
    """Kiểm tra kết nối đến Telegram"""
    test_msg = f"🔔 Bot connection test successful!\nTime: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    try:
        response = send_telegram_alert(test_msg)
        if response:
            logger.info("Telegram connection test: PASSED")
            return True
        logger.error("Telegram test failed: No response")
        return False
    except Exception as e:
        logger.error(f"Telegram connection failed: {str(e)}")
        return False

# ======= HÀM LẤY DỮ LIỆU TỪ BINANCE ========
def fetch_crypto_data(symbol, interval='1h', limit=100):
    # Chuyển sang sử dụng Bybit API
    url = "https://api.bybit.com/v5/market/kline"
    
    # Bybit sử dụng quy ước ký hiệu khác: BTCUSDT → BTCUSDT
    params = {
        'category': 'linear',
        'symbol': symbol,
        'interval': interval,
        'limit': limit
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        data = response.json()
        
        if data['retCode'] != 0:
            logger.error(f"Bybit API error: {data['retMsg']}")
            return None
            
        klines = data['result']['list']
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'turnover'
        ])
        logger.info(f"Fetched {len(df)} records for {symbol} ({interval})")
        return df
    except Exception as e:
        logger.error(f"Failed to fetch data for {symbol}: {str(e)}")
        return None
        
# ======= HÀM LẤY TÍN HIỆU ICHIMOKU TỪ CLOUDFLARE WORKER ========
def get_ichimoku_signal(high, low, close):
    worker_url = os.getenv("CLOUDFLARE_WORKER_URL")
    if ichimoku_signal is None:
    logger.warning("Using fallback Ichimoku analysis")
    
    if not worker_url:
        logger.error("Cloudflare Worker URL not configured")
        return None
    
    data = {
        "high": high[-100:],  # Chỉ gửi 100 nến gần nhất
        "low": low[-100:],
        "close": close[-100:]
    }
    
    try:
        response = requests.post(
            worker_url, 
            json=data,
            timeout=10  # Timeout sau 10 giây
        )
        response.raise_for_status()
        return response.json().get("signal")
    except Exception as e:
        logger.error(f"Failed to get Ichimoku signal: {str(e)}")
        return None

# ======= HÀM PHÂN TÍCH CHÍNH ========
def analyze_market():
    # ======= TEST MODE - GỬI TÍN HIỆU THỬ ========
    TEST_MODE = os.getenv("TEST_MODE", "False").lower() == "true"
    
    if TEST_MODE:
        test_message = """
🚀 **TEST SIGNAL** 🚀
🪙 **Coin:** BTC/USDT
📈 **Lệnh:** LONG
 leverage **Đòn bẩy đề xuất:** 5x
🔍 **Phân tích:** This is a test signal
"""
        send_telegram_alert(test_message)
        logger.info("Sent test signal to Telegram")
        # return  # Bỏ comment nếu chỉ muốn test không chạy tiếp
    
    # Kết nối Supabase để lấy danh sách coin
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        if not supabase_url or not supabase_key:
            logger.error("Missing Supabase credentials")
            return
            
        supabase = create_client(supabase_url, supabase_key)
        top_coins_data = supabase.table("top_coins").select("*").eq("id", 1).execute()
        
        if not top_coins_data.data:
            logger.error("No top coins data found in Supabase")
            return
            
        top_coins = top_coins_data.data[0]['coins']
        logger.info(f"Loaded {len(top_coins)} coins from Supabase")
    except Exception as e:
        logger.error(f"Supabase connection failed: {str(e)}")
        return
        
    signal_count = 0
    
    for coin in top_coins:
        symbol = f"{coin}USDT"
        logger.info(f"======= ANALYZING {symbol} =======")
        
        try:
            df_4h = fetch_crypto_data(symbol, '4h')
            
            # Kiểm tra dữ liệu đủ
            if df_4h is None or len(df_4h) < 100:
                logger.warning(f"Skipping {symbol}: insufficient data")
                continue
                
            logger.info(f"Data range: {df_4h['timestamp'].iloc[0]} to {df_4h['timestamp'].iloc[-1]}")
            logger.info(f"Latest close: {df_4h['close'].iloc[-1]}")
            
            # ======= TÍNH TOÁN CHỈ BÁO ========
            # RSI
            df_4h.ta.rsi(length=14, append=True)
            current_rsi = df_4h['RSI_14'].iloc[-1]
            
            # MACD
            df_4h.ta.macd(fast=12, slow=26, signal=9, append=True)
            
            # EMA
            df_4h.ta.ema(length=21, append=True)
            df_4h.ta.ema(length=50, append=True)
            df_4h.ta.ema(length=200, append=True)
            
            # ADX
            df_4h.ta.adx(length=14, append=True)
            
            # Ichimoku Cloud
            ichimoku_signal = get_ichimoku_signal(
                df_4h['high'].tolist(),
                df_4h['low'].tolist(),
                df_4h['close'].tolist()
            )
            
            # ======= LOG CHỈ BÁO ========
            logger.debug(f"RSI: {current_rsi:.2f}")
            logger.debug(f"MACD: {df_4h['MACD_12_26_9'].iloc[-1]:.4f}, Signal: {df_4h['MACDs_12_26_9'].iloc[-1]:.4f}")
            logger.debug(f"EMA 21: {df_4h['EMA_21'].iloc[-1]:.2f}, EMA 50: {df_4h['EMA_50'].iloc[-1]:.2f}, EMA 200: {df_4h['EMA_200'].iloc[-1]:.2f}")
            logger.debug(f"ADX: {df_4h['ADX_14'].iloc[-1]:.2f}")
            logger.debug(f"Ichimoku signal: {ichimoku_signal}")
            
            # ======= XÁC ĐỊNH TÍN HIỆU ========
            signals = []
            
            # RSI
            if current_rsi < 35:
                signals.append("RSI quá bán")
            elif current_rsi > 65:
                signals.append("RSI quá mua")
                
            # MACD
            if df_4h['MACD_12_26_9'].iloc[-1] > df_4h['MACDs_12_26_9'].iloc[-1] and \
               df_4h['MACD_12_26_9'].iloc[-2] < df_4h['MACDs_12_26_9'].iloc[-2]:
                signals.append("MACD cắt lên")
                
            # EMA
            if df_4h['EMA_21'].iloc[-1] > df_4h['EMA_50'].iloc[-1] > df_4h['EMA_200'].iloc[-1]:
                signals.append("EMA tăng (21>50>200)")
                
            # ADX
            if df_4h['ADX_14'].iloc[-1] > 25:
                signals.append("Xu hướng mạnh (ADX>25)")
                
            # Ichimoku
            if ichimoku_signal in ['STRONG_BULLISH', 'BULLISH']:
                signals.append("Ichimoku tăng")
            
            # ======= KIỂM TRA ĐIỀU KIỆN GIAO DỊCH ========
            logger.info(f"Signals detected: {signals} ({len(signals)} signals)")
            
            # Yêu cầu 4 chỉ báo đồng thuận và ADX > 20
            if len(signals) >= 4 and df_4h['ADX_14'].iloc[-1] > 20:
                logger.info("✅ Conditions met! Generating signal...")
                current_price = df_4h['close'].iloc[-1]
                
                # Tính ATR cho quản lý rủi ro
                atr = ta.atr(df_4h['high'], df_4h['low'], df_4h['close'], length=14).iloc[-1]
                
                # Tính điểm vào lệnh
                entry1 = current_price * 0.995
                entry2 = current_price * 0.99
                
                # Tính điểm chốt lời
                tp1 = current_price + atr * 1
                tp2 = current_price + atr * 2
                tp3 = current_price + atr * 3
                
                # Điểm dừng lỗ
                stop_loss = current_price - atr * 1.5
                
                # Tạo thông báo
                message = f"""
🚀 **TÍN HIỆU GIAO DỊCH MỚI** 🚀

🪙 **Coin:** {symbol}
📈 **Lệnh:** LONG
 leverage **Đòn bẩy đề xuất:** 5x

🎯 **VÙNG VÀO LỆNH:**
* {entry1:.4f}
* {entry2:.4f}

✅ **CÁC MỤC TIÊU CHỐT LỜI:**
* TP1: {tp1:.4f}
* TP2: {tp2:.4f}
* TP3: {tp3:.4f}

🚫 **ĐIỂM DỪNG LỖ:** {stop_loss:.4f}

🔍 **Phân tích:**
{", ".join(signals)}
"""
                if send_telegram_alert(message):
                    signal_count += 1
                    logger.info(f"Signal sent for {symbol}")
                else:
                    logger.error(f"Failed to send signal for {symbol}")
            else:
                reason = f"Signals: {len(signals)}/{4}, ADX: {df_4h['ADX_14'].iloc[-1]:.2f}/20"
                logger.info(f"❌ Conditions not met ({reason})")
                
        except Exception as e:
            error_msg = f"⚠️ Error processing {symbol}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            send_telegram_alert(error_msg)
        
        time.sleep(1)  # Chờ ngắn giữa các coin
    
    # ======= BÁO CÁO TỔNG KẾT ========
    report = f"""
📊 **Analysis Report** 
⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
🪙 Coins analyzed: {len(top_coins)}
🚀 Signals generated: {signal_count}
📈 Market conditions: {'Bullish' if signal_count > 0 else 'Neutral/Bearish'}
"""
    send_telegram_alert(report)
    logger.info(report)

# ======= MAIN EXECUTION ========
if __name__ == "__main__":
    logger.info("====== BOT STARTED ======")
    
    # Kiểm tra kết nối Telegram
    if not test_telegram_connection():
        logger.error("Critical: Telegram connection failed. Exiting.")
        exit(1)
    
    # Chạy phân tích thị trường
    try:
        analyze_market()
    except Exception as e:
        logger.error(f"Unhandled exception in main: {str(e)}", exc_info=True)
        send_telegram_alert(f"⚠️ CRITICAL ERROR: {str(e)}")
    
    logger.info("====== BOT FINISHED ======")