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
from dashboard import create_dashboard
from config.api_config import OKX_DEMO_CONFIG, DEFAULT_SYMBOL, DEFAULT_TIMEFRAME


def run_engine(engine):
    """在后台线程运行引擎"""
    try:
        engine.run()
    except Exception as e:
        print(f"引擎错误: {e}")


def main():
    print("\n" + "="*60)
    print("CTS1 - OKX 模拟盘 (Dashboard 模式)")
    print("="*60)
    print(f"交易对: {DEFAULT_SYMBOL}")
    print(f"K线周期: {DEFAULT_TIMEFRAME}")
    print("="*60 + "\n")
    
    # 创建组件
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
    
    # Dashboard 更新回调
    dashboard = create_dashboard(port=5000)
    
    def on_status_update(status):
        dashboard.update(status)
    
    engine.register_status_callback(on_status_update)
    
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
