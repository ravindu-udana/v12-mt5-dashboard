import MetaTrader5 as mt5
from flask import Flask, request, jsonify

app = Flask(__name__)

# Initialize connection to the MT5 terminal on import
if not mt5.initialize():
    print("initialize() failed, error code =", mt5.last_error())
else:
    print("MT5 initialized successfully")

@app.route("/history", methods=["GET"])
def get_history():
    symbol = request.args.get("symbol", "XAUUSD")
    count = int(request.args.get("count", 600))
    timeframe = request.args.get("timeframe", "M1")
    
    # Map timeframe string to MT5 constant
    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "H1": mt5.TIMEFRAME_H1,
        "D1": mt5.TIMEFRAME_D1
    }
    
    tf = tf_map.get(timeframe.upper())
    if tf is None:
        return jsonify({"error": "Invalid timeframe"}), 400
        
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None:
        return jsonify({"error": f"No data found for {symbol}"}), 404
        
    result = []
    for r in rates:
        result.append({
            'time': int(r[0]),
            'open': float(r[1]),
            'high': float(r[2]),
            'low': float(r[3]),
            'close': float(r[4]),
            'tick_volume': int(r[5])
        })
        
    return jsonify(result)

@app.route("/positions", methods=["GET"])
def get_positions():
    positions = mt5.positions_get()
    if positions is None:
        return jsonify({"error": "Failed to get positions", "code": mt5.last_error()}), 500
    
    result = []
    for p in positions:
        result.append({
            'ticket': p.ticket,
            'symbol': p.symbol,
            'type': p.type, # 0 = buy, 1 = sell
            'volume': p.volume,
            'price_open': p.price_open,
            'sl': p.sl,
            'tp': p.tp,
            'price_current': p.price_current,
            'profit': p.profit,
            'time': p.time,
            'comment': p.comment
        })
    return jsonify(result)

from datetime import datetime, timedelta

@app.route("/deals", methods=["GET"])
def get_deals():
    days = int(request.args.get("days", 7))
    date_from = datetime.now() - timedelta(days=days)
    date_to = datetime.now() + timedelta(days=1)
    
    deals = mt5.history_deals_get(date_from, date_to)
    if deals is None:
        return jsonify({"error": "Failed to get deals", "code": mt5.last_error()}), 500
    
    result = []
    for d in deals:
        if d.entry == mt5.DEAL_ENTRY_OUT:
            result.append({
                'ticket': d.ticket,
                'position_id': d.position_id,
                'symbol': d.symbol,
                'type': d.type, # 0=buy, 1=sell
                'volume': d.volume,
                'price': d.price,
                'profit': d.profit,
                'time': d.time,
                'comment': d.comment
            })
            
    result.sort(key=lambda x: x['time'], reverse=True)
    return jsonify(result)

@app.route("/order", methods=["POST"])
def place_order():
    data = request.json
    action = data.get('action') # 'buy' or 'sell'
    symbol = data.get('symbol', 'XAUUSD')
    volume = float(data.get('volume', 0.01))
    sl = float(data.get('sl', 0.0))
    tp = float(data.get('tp', 0.0))
    
    order_type = mt5.ORDER_TYPE_BUY if action.lower() == 'buy' else mt5.ORDER_TYPE_SELL
    
    # get symbol info
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return jsonify({"error": "Symbol not found"}), 400
        
    price = mt5.symbol_info_tick(symbol).ask if action.lower() == 'buy' else mt5.symbol_info_tick(symbol).bid
    
    request_data = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": 123456,
        "comment": "v12 dashboard",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request_data)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return jsonify({"error": "Order send failed", "retcode": result.retcode, "comment": result.comment}), 500
        
    return jsonify({
        "order": result.order,
        "volume": result.volume,
        "price": result.price,
        "comment": result.comment
    })

@app.route("/close", methods=["POST"])
def close_order():
    data = request.json
    ticket = int(data.get('ticket'))
    
    position = mt5.positions_get(ticket=ticket)
    if position is None or len(position) == 0:
        return jsonify({"error": "Position not found"}), 404
        
    pos = position[0]
    order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = mt5.symbol_info_tick(pos.symbol).bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(pos.symbol).ask
    
    request_data = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": order_type,
        "position": ticket,
        "price": price,
        "deviation": 20,
        "magic": 123456,
        "comment": "v12 close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request_data)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return jsonify({"error": "Close failed", "retcode": result.retcode, "comment": result.comment}), 500
        
    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
