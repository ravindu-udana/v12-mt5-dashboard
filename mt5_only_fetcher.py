import time
import requests
import sqlite3
import pandas as pd
from datetime import datetime, timezone
import sys

DB_MT5 = "/home/ubuntu/mt5_gold.db"

def is_market_closed():
    now_utc = datetime.now(timezone.utc)
    if now_utc.weekday() == 5:
        return True
    if now_utc.weekday() == 4 and now_utc.hour >= 22:
        return True
    if now_utc.weekday() == 6 and now_utc.hour < 22:
        return True
    return False

def save_candles(df, db_path):
    if df is None or df.empty:
        return
        
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    inserted = 0
    for idx, row in df.iterrows():
        try:
            dt_str = str(row['datetime'])
            cur.execute("""
                INSERT OR REPLACE INTO candles (datetime, unix_time, open, high, low, close, tick_volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (dt_str, row.get('time', 0), row['open'], row['high'], row['low'], row['close'], row['volume']))
            inserted += 1
        except sqlite3.IntegrityError:
            pass
            
    conn.commit()
    conn.close()
    if inserted > 0:
        print(f"[{datetime.now()}] {db_path}: Inserted {inserted} new candles.")

def fetch_mt5():
    try:
        r = requests.get("http://127.0.0.1:5000/history?symbol=XAUUSD&count=5000", timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data:
                df = pd.DataFrame(data)
                # MT5 bridge returns broker time (GMT+3) as unix timestamps.
                # We subtract 3 hours (10800s) to convert it to True UTC time.
                df['time'] = df['time'] - 10800
                df['datetime'] = pd.to_datetime(df['time'], unit='s')
                df = df.rename(columns={'tick_volume': 'volume'})
                save_candles(df, DB_MT5)
    except Exception as e:
        print(f"[{datetime.now()}] MT5 Fetch Error: {e}")

def main():
    print("Starting MT5 Data Fetcher...")
    while True:
        if is_market_closed():
            print(f"[{datetime.now()}] Market closed. Sleeping...")
            time.sleep(300)
            continue
            
        fetch_mt5()
        time.sleep(5)

if __name__ == "__main__":
    main()
