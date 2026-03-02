"""
TradingView 图表本地测试脚本
生成模拟 K 线数据，不依赖 OKX 网络
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

# 模拟 K 线数据生成器
def generate_mock_candles(count=200):
    """生成模拟 BTC K 线数据"""
    candles = []
    base_price = 65000
    current_time = datetime.now()
    
    for i in range(count):
        # 生成随机波动
        volatility = random.uniform(-0.002, 0.002)
        if i > count // 2:
            # 后半段添加趋势
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
    print('[TEST] 客户端已连接')
    
    # 发送历史 K 线数据
    mock_candles = generate_mock_candles(150)
    print(f'[TEST] 发送 {len(mock_candles)} 根模拟 K 线')
    emit('history_update', {'candles': mock_candles})
    
    # 发送初始状态
    emit('update', {
        'prices': {'BTC-USDT': mock_candles[-1]['c']},
        'total_value': 10500.50,
        'cash': 5000.0,
        'pnl_pct': 5.05,
        'rsi': 45.5,
        'positions': {'BTC-USDT': 0.085}
    })

def mock_data_stream():
    """模拟实时数据流"""
    price = 65000
    while True:
        time.sleep(3)  # 每3秒更新一次
        
        # 生成新的 K 线
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
        rsi = 30 + random.random() * 40  # 30-70 之间随机
        
        socketio.emit('update', {
            'prices': {'BTC-USDT': round(new_price, 2)},
            'total_value': 10500 + random.uniform(-100, 100),
            'pnl_pct': 5.05 + random.uniform(-0.5, 0.5),
            'rsi': round(rsi, 1),
            'candle': candle
        })
        
        print(f'[TEST] 推送新数据: Price={new_price:.2f}, RSI={rsi:.1f}')

if __name__ == '__main__':
    print('='*60)
    print('TradingView 图表本地测试')
    print('='*60)
    print('功能: 生成模拟 K 线数据，测试 TradingView 图表是否正常')
    print('访问: http://localhost:5000')
    print('注意: 每3秒自动推送新 K 线数据')
    print('='*60)
    
    # 启动模拟数据推送
    socketio.start_background_task(mock_data_stream)
    
    # 启动服务器
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
