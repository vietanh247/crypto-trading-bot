import patch_pandas_ta
import os
import time
import requests
import pandas as pd
import pandas_ta as ta
import numpy as np
import sys
import pandas_ta
print(f"pandas_ta version: {pandas_ta.__version__}")
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
if 'NaN' not in sys.modules:
    sys.modules['NaN'] = np.nan

# Hàm lấy dữ liệu từ Binance
def fetch_crypto_data(symbol, interval='1h', limit=500):
    url = "https://api.binance.com/api/v3/klines"
    params = {
        'symbol': symbol,
        'interval': interval,
        'limit': limit
    }
    response = requests.get(url, params=params)
    data = response.json()
    
    df = pd.DataFrame(data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 
        'taker_buy_base', 'taker_buy_quote', 'ignore'
    ])
    
    numeric_cols = ['open', 'high', 'low', 'close', 'volume']
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, axis=1)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    return df

# Hàm gửi cảnh báo Telegram
def send_telegram_alert(message):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown'
    }
    
    response = requests.post(url, json=payload)
    return response.json()
def test_telegram_connection():
    """Kiểm tra kết nối đến Telegram"""
    test_msg = "🔔 Bot connection test successful! Time: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        response = send_telegram_alert(test_msg)
        logging.info(f"Telegram test response: {response.status_code}")
        return True
    except Exception as e:
        logging.error(f"Telegram connection failed: {str(e)}")
        return False
# Hàm phân tích chính
def analyze_market():
    supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    top_coins_data = supabase.table("top_coins").select("*").eq("id", 1).execute()
    top_coins = top_coins_data.data[0]['coins']
    
    for coin in top_coins:
        symbol = f"{coin}USDT"
        
        try:
            df_4h = fetch_crypto_data(symbol, '4h')
            if df_4h is None or len(df_4h) < 100:
                logging.warning(f"Skipping {symbol}: insufficient data ({len(df_4h) if df_4h else 0} records)")
            continue
            
                logging.info(f"Data range: {df_4h['timestamp'].iloc[0]} to {df_4h['timestamp'].iloc[-1]}")
                logging.info(f"Latest close: {df_4h['close'].iloc[-1]}")
            # Kiểm tra dữ liệu đủ
            if len(df_4h) < 100:
                continue
                
            # Gửi dữ liệu đến Cloudflare Worker cho Ichimoku
            ichimoku_data = {
                "high": df_4h['high'].tolist(),
                "low": df_4h['low'].tolist(),
                "close": df_4h['close'].tolist()
            }
            
            worker_url = os.getenv("CLOUDFLARE_WORKER_URL")
            response = requests.post(worker_url, json=ichimoku_data)
            ichimoku_result = response.json()
            
            # Tính toán các chỉ báo khác
            df_4h.ta.rsi(length=14, append=True)
            df_4h.ta.macd(fast=12, slow=26, signal=9, append=True)
            df_4h.ta.ema(length=21, append=True)
            df_4h.ta.ema(length=50, append=True)
            df_4h.ta.ema(length=200, append=True)
            df_4h.ta.adx(length=14, append=True)

            # Xác định tín hiệu
            signals = []
            
            # RSI
            current_rsi = df_4h['RSI_14'].iloc[-1]
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
            if ichimoku_result['signal'] in ['STRONG_BULLISH', 'BULLISH']:
                signals.append("Ichimoku tăng")
                
            # Kiểm tra điều kiện giao dịch
            logging.info(f"Signals detected: {signals}")
            if len(signals) >= 4 and df_4h['ADX_14'].iloc[-1] > 20:
                logging.info("✅ Conditions met! Generating signal...")
                current_price = df_4h['close'].iloc[-1]
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
                send_telegram_alert(message)
                print(f"Signal sent for {symbol}")
                signal_count += 1
            else:
                # ===== THÊM LOGGING LÝ DO KHÔNG TẠO TÍN HIỆU =====
                logging.info(f"❌ Conditions not met. Signals: {len(signals)}, ADX: {df_4h['adx'].iloc[-1]}")
                
        except Exception as e:
            error_msg = f"⚠️ Error processing {symbol}: {str(e)}"
            logging.error(error_msg, exc_info=True)
            send_telegram_alert(error_msg)
    
        time.sleep(5)  # Chờ giữa các coin
if __name__ == "__main__":
    analyze_market()