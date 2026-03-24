"""
TradingView 鍥捐〃鏈湴娴嬭瘯鑴氭湰
鐢熸垚妯℃嫙 K 绾挎暟鎹紝涓嶄緷璧?OKX 缃戠粶
"""

from flask import Flask, render_template, make_response
from flask_socketio import SocketIO, emit
import threading
import time
import random
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'test-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# 妯℃嫙 K 绾挎暟鎹敓鎴愬櫒
def generate_mock_candles(count=200):
    """鐢熸垚妯℃嫙 BTC K 绾挎暟鎹?""
    candles = []
    base_price = 65000
    current_time = datetime.now()
    
    for i in range(count):
        # 鐢熸垚闅忔満娉㈠姩
        volatility = random.uniform(-0.002, 0.002)
        if i > count // 2:
            # 鍚庡崐娈垫坊鍔犺秼鍔?
            volatility += 0.0005
        
        open_price = base_price * (1 + volatility)
        high_price = open_price * (1 + random.uniform(0, 0.003))
        low_price = open_price * (1 - random.uniform(0, 0.003))
        close_price = (high_price + low_price) / 2 + random.uniform(-50, 50)
        
        candle_time = current_time - timedelta(minutes=count-i)
        
        candles.append({
            't': candle_time.isoformat(),
            'o': round(open_price, 2),
            'h': round(high_price, 2),
            'l': round(low_price, 2),
            'c': round(close_price, 2)
        })
        
        base_price = close_price
    
    return candles

@app.route('/')
def index():
    res = make_response(render_template('dashboard.html'))
    res.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return res

@socketio.on('connect')
def handle_connect():
    print('[TEST] 瀹㈡埛绔凡杩炴帴')
    
    # 鍙戦€佸巻鍙?K 绾挎暟鎹?
    mock_candles = generate_mock_candles(150)
    print(f'[TEST] 鍙戦€?{len(mock_candles)} 鏍规ā鎷?K 绾?)
    emit('history_update', {'candles': mock_candles})
    
    # 鍙戦€佸垵濮嬬姸鎬?
    emit('update', {
        'prices': {'BTC-USDT': mock_candles[-1]['c']},
        'total_value': 10500.50,
        'cash': 5000.0,
        'pnl_pct': 5.05,
        'rsi': 45.5,
        'positions': {'BTC-USDT': 0.085}
    })

def mock_data_stream():
    """妯℃嫙瀹炴椂鏁版嵁娴?""
    price = 65000
    while True:
        time.sleep(3)  # 姣?绉掓洿鏂颁竴娆?
        
        # 鐢熸垚鏂扮殑 K 绾?
        now = datetime.now()
        volatility = random.uniform(-100, 100)
        new_price = price + volatility
        
        candle = {
            't': now.isoformat(),
            'o': price,
            'h': max(price, new_price) + random.uniform(0, 50),
            'l': min(price, new_price) - random.uniform(0, 50),
            'c': new_price
        }
        
        price = new_price
        rsi = 30 + random.random() * 40  # 30-70 涔嬮棿闅忔満
        
        socketio.emit('update', {
            'prices': {'BTC-USDT': round(new_price, 2)},
            'total_value': 10500 + random.uniform(-100, 100),
            'pnl_pct': 5.05 + random.uniform(-0.5, 0.5),
            'rsi': round(rsi, 1),
            'candle': candle
        })
        
        print(f'[TEST] 鎺ㄩ€佹柊鏁版嵁: Price={new_price:.2f}, RSI={rsi:.1f}')

if __name__ == '__main__':
    print('='*60)
    print('TradingView 鍥捐〃鏈湴娴嬭瘯')
    print('='*60)
    print('鍔熻兘: 鐢熸垚妯℃嫙 K 绾挎暟鎹紝娴嬭瘯 TradingView 鍥捐〃鏄惁姝ｅ父')
    print('璁块棶: http://localhost:5000')
    print('娉ㄦ剰: 姣?绉掕嚜鍔ㄦ帹閫佹柊 K 绾挎暟鎹?)
    print('='*60)
    
    # 鍚姩妯℃嫙鏁版嵁鎺ㄩ€?
    socketio.start_background_task(mock_data_stream)
    
    # 鍚姩鏈嶅姟鍣?
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
