"""
OKX 模拟鐩?+ Dashboard 独立启动
（Dashboard 在主线程，引擎在后台锛?

使用方法:
    python run_okx_demo_with_dashboard.py
"""

import sys
import os
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cartridges.strategies import GridRSIStrategy
from cartridges.bridge.executors import OKXExecutor
from cartridges.bridge.datafeeds import OKXDataFeed
from console.engines import LiveEngine
import argparse
from infra.config.api_config import OKX_DEMO_CONFIG, DEFAULT_SYMBOL, DEFAULT_TIMEFRAME
from console.dashboard import create_dashboard


def run_engine(engine):
    """在后台线程运行引鎿?""
    try:
        engine.run()
    except Exception as e:
        print(f"引擎错误: {e}")


def main():
    parser = argparse.ArgumentParser(description='OKX 模拟鐩?+ Dashboard (带参数支持版鏈?')
    parser.add_argument('--strategy', default='4.0', choices=['4.0', '5.2'], help='策略版本')
    args = parser.parse_args()

    print("\n" + "="*60)
    print(f"CTS1 - OKX 模拟鐩?(Dashboard 模式) | 策略版本: {args.strategy}")
    print("="*60)
    print(f"交易瀵? {DEFAULT_SYMBOL}")
    print(f"K线周鏈? {DEFAULT_TIMEFRAME}")
    print("="*60 + "\n")
    
    # 创建组件
    if args.strategy == '5.2':
        from cartridges.strategies import GridRSIStrategyV5_2
        strategy = GridRSIStrategyV5_2(
            symbol=DEFAULT_SYMBOL,
            grid_levels=10,
            use_kelly_sizing=True,
            trailing_stop=True
        )
    else:
        from cartridges.strategies import GridRSIStrategy
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
    
    # 先显式执行热身以便拿到离线指鏍?
    print("预热策略...")
    engine.warmup()
    
    # Dashboard 更新回调
    dashboard = create_dashboard(port=5000)
    
    # 绑定鏈€新版的路由体绯?
    if args.strategy == '5.2':
        dashboard.register_strategy('default', 'Grid RSI V5.2 (模拟鐩?', route='/v5')
    else:
        dashboard.register_strategy('default', 'Grid RSI V4.0 (模拟鐩?', route='/')
        
    def on_status_update(status):
        dashboard.update(status)
    
    engine.register_status_callback(on_status_update)
    
    # 回放历ʷ以预填前端图琛?
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
        
    # 在后台启动引鎿?
    engine_thread = threading.Thread(target=run_engine, args=(engine,))
    engine_thread.daemon = True
    engine_thread.start()
    
    # 主线程运琛?Dashboard
    print("Dashboard: http://localhost:5000")
    print("鎸?Ctrl+C 停止\n")
    
    try:
        dashboard.start()
    except KeyboardInterrupt:
        print("\n正在停止...")
        engine.stop()
        print("已停姝?)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
