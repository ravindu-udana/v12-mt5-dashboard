import sqlite3
import pandas as pd
import json

DB_FILE = "wizard_v7.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Candles table (time is primary key to prevent duplicates)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS candles (
            time INTEGER PRIMARY KEY,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL
        )
    ''')
    
    # Signals table (time is primary key to prevent duplicates)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS signals (
            time INTEGER PRIMARY KEY,
            direction TEXT,
            confidence REAL,
            status TEXT DEFAULT 'PENDING'
        )
    ''')
    
    # In case we upgraded from v6, add the status column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE signals ADD COLUMN status TEXT DEFAULT 'PENDING'")
    except sqlite3.OperationalError:
        pass
        
    # Manual Engulfings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS manual_engulfings (
            c_time INTEGER PRIMARY KEY,
            c_open REAL, c_high REAL, c_low REAL, c_close REAL, c_volume REAL,
            b_time INTEGER, b_open REAL, b_high REAL, b_low REAL, b_close REAL, b_volume REAL,
            a_time INTEGER, a_open REAL, a_high REAL, a_low REAL, a_close REAL, a_volume REAL
        )
    ''')
    
    conn.commit()
    conn.close()

def save_candles(df):
    """Upserts candles from a pandas dataframe into the database."""
    conn = sqlite3.connect(DB_FILE)
    # Convert dataframe to list of tuples for fast insert
    # df must contain: time, open, high, low, close, tick_volume
    records = []
    for _, row in df.iterrows():
        # Handle time
        timestamp = int(row['datetime'].timestamp())
        records.append((
            timestamp,
            float(row['open']),
            float(row['high']),
            float(row['low']),
            float(row['close']),
            float(row['tick_volume'])
        ))
        
    cursor = conn.cursor()
    # INSERT OR REPLACE handles upsert natively in sqlite based on primary key
    cursor.executemany('''
        INSERT OR REPLACE INTO candles (time, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', records)
    
    conn.commit()
    conn.close()

def save_signal(time_val, direction, confidence):
    """Upserts a single AI signal into the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO signals (time, direction, confidence, status)
        VALUES (?, ?, ?, COALESCE((SELECT status FROM signals WHERE time = ?), 'PENDING'))
    ''', (int(time_val), direction, float(confidence), int(time_val)))
    conn.commit()
    conn.close()

def update_signal_status(time_val, status):
    """Updates the status of an existing signal to WON or LOST."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE signals SET status = ? WHERE time = ?
    ''', (status, int(time_val)))
    conn.commit()
    conn.close()

def get_all_candles():
    """Returns all historical candles from the database as a list of dicts."""
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM candles ORDER BY time ASC", conn)
    conn.close()
    
    return df.to_dict(orient='records')

def get_all_signals():
    """Returns all historical AI signals from the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT time, direction, confidence, status FROM signals ORDER BY time ASC")
    rows = cursor.fetchall()
    conn.close()
    
    signals = []
    for row in rows:
        signals.append({
            'time': row[0],
            'direction': row[1],
            'confidence': row[2],
            'status': row[3]
        })
    return signals

def toggle_manual_engulfing(a, b, c):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT c_time FROM manual_engulfings WHERE c_time = ?", (c['time'],))
    row = cursor.fetchone()
    
    if row:
        cursor.execute("DELETE FROM manual_engulfings WHERE c_time = ?", (c['time'],))
        action = "deleted"
    else:
        cursor.execute('''
            INSERT INTO manual_engulfings (
                c_time, c_open, c_high, c_low, c_close, c_volume,
                b_time, b_open, b_high, b_low, b_close, b_volume,
                a_time, a_open, a_high, a_low, a_close, a_volume
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            c['time'], c['open'], c['high'], c['low'], c['close'], c.get('value', c.get('volume', 0)),
            b['time'], b['open'], b['high'], b['low'], b['close'], b.get('value', b.get('volume', 0)),
            a['time'], a['open'], a['high'], a['low'], a['close'], a.get('value', a.get('volume', 0))
        ))
        action = "inserted"
        
    conn.commit()
    conn.close()
    return action

def get_manual_engulfings():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM manual_engulfings", conn)
    conn.close()
    return df.to_dict(orient='records')
