"""
OKX 模拟盘 + Dashboard 独立启动
（Dashboard 在主线程，引擎在后台）

使用方法:
    python run_okx_demo_with_dashboard.py
"""

import sys
import os
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategies import GridRSIStrategy
from executors import OKXExecutor
from datafeeds import OKXDataFeed
from engines import LiveEngine
import argparse
from config.api_config import OKX_DEMO_CONFIG, DEFAULT_SYMBOL, DEFAULT_TIMEFRAME
from dashboard import create_dashboard


def run_engine(engine):
    """在后台线程运行引擎"""
    try:
        engine.run()
    except Exception as e:
        print(f"引擎错误: {e}")


def main():
    parser = argparse.ArgumentParser(description='OKX 模拟盘 + Dashboard (带参数支持版本)')
    parser.add_argument('--strategy', default='4.0', choices=['4.0', '5.1'], help='策略版本')
    args = parser.parse_args()

    print("\n" + "="*60)
    print(f"CTS1 - OKX 模拟盘 (Dashboard 模式) | 策略版本: {args.strategy}")
    print("="*60)
    print(f"交易对: {DEFAULT_SYMBOL}")
    print(f"K线周期: {DEFAULT_TIMEFRAME}")
    print("="*60 + "\n")
    
    # 创建组件
    if args.strategy == '5.1':
        from strategies import GridRSIStrategyV5_1
        strategy = GridRSIStrategyV5_1(
            symbol=DEFAULT_SYMBOL,
            grid_levels=10,
            use_kelly_sizing=True,
            trailing_stop=True
        )
    else:
        from strategies import GridRSIStrategy
        strategy = GridRSIStrategy(
            symbol=DEFAULT_SYMBOL,
            grid_levels=10,
            use_kelly_sizing=True,
            trailing_stop=True
        )
    
    executor = OKXExecutor(
        api_key=OKX_DEMO_CONFIG['api_key'],
        api_secret=OKX_DEMO_CONFIG['api_secret'],
        passphrase=OKX_DEMO_CONFIG['passphrase'],
        is_demo=True
    )
    
    data_feed = OKXDataFeed(
        symbol=DEFAULT_SYMBOL,
        timeframe=DEFAULT_TIMEFRAME,
        api_key=OKX_DEMO_CONFIG['api_key'],
        api_secret=OKX_DEMO_CONFIG['api_secret'],
        passphrase=OKX_DEMO_CONFIG['passphrase'],
        is_demo=True,
        poll_interval=2.0
    )
    
    engine = LiveEngine(
        strategy=strategy,
        executor=executor,
        data_feed=data_feed,
        warmup_bars=100
    )
    
    # 先显式执行热身以便拿到离线指标
    print("预热策略...")
    engine.warmup()
    
    # Dashboard 更新回调
    dashboard = create_dashboard(port=5000)
    
    # 绑定最新版的路由体系
    if args.strategy == '5.1':
        dashboard.register_strategy('default', 'Grid RSI V5.1 (模拟盘)', route='/5.1')
    else:
        dashboard.register_strategy('default', 'Grid RSI V4.0 (模拟盘)', route='/')
        
    def on_status_update(status):
        dashboard.update(status)
    
    engine.register_status_callback(on_status_update)
    
    # 回放历史以预填前端图表
    hist_data = {}
    if hasattr(strategy, '_data_buffer') and strategy._data_buffer:
        history_candles = []
        for d in strategy._data_buffer:
            import pandas as pd
            ts_ms = int(pd.Timestamp(d.timestamp).timestamp() * 1000)
            history_candles.append({
                't': ts_ms, 'o': float(d.open), 'h': float(d.high), 'l': float(d.low), 'c': float(d.close)
            })
        hist_data = {
            'history_candles': history_candles,
            'history_rsi': [{'time': c['t'], 'value': None} for c in history_candles],
            'history_equity': [{'time': c['t'], 'value': None} for c in history_candles]
        }
        if hasattr(engine, '_history_rsi'): hist_data['history_rsi'] = engine._history_rsi
        if hasattr(engine, '_history_macd'): hist_data['history_macd'] = engine._history_macd
        dashboard.update(hist_data)
        
    # 在后台启动引擎
    engine_thread = threading.Thread(target=run_engine, args=(engine,))
    engine_thread.daemon = True
    engine_thread.start()
    
    # 主线程运行 Dashboard
    print("Dashboard: http://localhost:5000")
    print("按 Ctrl+C 停止\n")
    
    try:
        dashboard.start()
    except KeyboardInterrupt:
        print("\n正在停止...")
        engine.stop()
        print("已停止")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
