import asyncio
import json
import sqlite3
import pandas as pd
import pandas_ta_classic as ta
import numpy as np
import database
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from datetime import datetime
from contextlib import asynccontextmanager
import uvicorn

# Global State
connected_clients = []
last_processed_candle_time = None

def get_latest_mt5_data():
    """Fetches last 10000 candles from the MT5 database."""
    try:
        conn = sqlite3.connect('/home/ubuntu/mt5_gold.db')
        df = pd.read_sql_query("SELECT * FROM candles ORDER BY unix_time DESC LIMIT 10000", conn)
        conn.close()
        
        if df.empty:
            return None
            
        # Reverse to chronological order
        df = df.iloc[::-1].reset_index(drop=True)
        
        # Convert timestamp to datetime if not already
        df['datetime'] = pd.to_datetime(df['unix_time'], unit='s')
        
        # In mt5_gold.db columns are already open, high, low, close, tick_volume
        df = df.rename(columns={'tick_volume': 'tick_volume'})
        
        df['hour'] = df['datetime'].dt.hour
        df['dayofweek'] = df['datetime'].dt.dayofweek
        
        # Compute TA
        df.ta.ema(length=9, append=True)
        df.ta.ema(length=21, append=True)
        df.ta.ema(length=50, append=True)
        df.ta.ema(length=200, append=True)
        df.ta.sma(length=50, append=True)
        df.ta.sma(length=200, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        df.ta.rsi(length=14, append=True)
        df.ta.stoch(append=True)
        df.ta.bbands(length=20, std=2.0, append=True)
        df.ta.atr(length=14, append=True)
        
        df = df.dropna().reset_index(drop=True)
        return df
    except Exception as e:
        print(f"Error fetching OANDA data: {e}")
        return None

# Global State
connected_clients = []
last_processed_candle_time = None

async def broadcast(message: dict):
    for client in connected_clients:
        try:
            await client.send_text(json.dumps(message))
        except:
            pass

async def live_trading_loop():
    global last_processed_candle_time
    print("Starting Live Trading Polling Loop...")
    
    # 1. Boot-up sweep
    initial_df = get_latest_mt5_data()
    if initial_df is not None:
        database.save_candles(initial_df)
    
    while True:
        try:
            df = get_latest_mt5_data()
            if df is not None:
                # OPTIMIZATION: Only save the last 100 candles to DB to prevent 6-8s IO lag
                database.save_candles(df.tail(100))
                
                active_candle = df.iloc[-1]
                await broadcast({
                    'type': 'candle',
                    'data': {
                        'time': int(active_candle['datetime'].timestamp()),
                        'open': float(active_candle['open']),
                        'high': float(active_candle['high']),
                        'low': float(active_candle['low']),
                        'close': float(active_candle['close']),
                        'volume': float(active_candle['tick_volume'])
                    }
                })
                        
        except Exception as e:
            print(f"Loop Error: {e}")
            
        await asyncio.sleep(0.5) # Poll every 0.5 second


background_tasks = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(live_trading_loop())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    yield

app = FastAPI(lifespan=lifespan)

# Initialize database
database.init_db()

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    
    # Send historical data on connect
    try:
        print("Client Connected, fetching history from DB...")
        history = database.get_all_candles()
        await websocket.send_text(json.dumps({'type': 'history', 'data': history}))
        
        # Send historical signals
        history_signals = database.get_all_signals()
        await websocket.send_text(json.dumps({'type': 'history_signals', 'data': history_signals}))
        
        # Send manual engulfings
        manual = database.get_manual_engulfings()
        await websocket.send_text(json.dumps({'type': 'manual_update', 'data': manual}))
        
    except Exception as e:
        print(f"WS Error: {e}")
        
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                
                if msg.get('type') == 'toggle_manual':
                    database.toggle_manual_engulfing(
                        msg['data']['a'], msg['data']['b'], msg['data']['c']
                    )
                    # Broadcast to all clients
                    broadcast_msg = json.dumps({'type': 'manual_update', 'data': database.get_manual_engulfings()})
                    for client in connected_clients:
                        try:
                            await client.send_text(broadcast_msg)
                        except:
                            pass
            except Exception as e:
                print(f"Error processing message: {e}")
    except:
        connected_clients.remove(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8005, reload=False, ws="wsproto")
