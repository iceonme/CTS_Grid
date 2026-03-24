"""
OKX 妯℃嫙鐩?+ Dashboard 鐙珛鍚姩
锛圖ashboard 鍦ㄤ富绾跨▼锛屽紩鎿庡湪鍚庡彴锛?

浣跨敤鏂规硶:
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
    """鍦ㄥ悗鍙扮嚎绋嬭繍琛屽紩鎿?""
    try:
        engine.run()
    except Exception as e:
        print(f"寮曟搸閿欒: {e}")


def main():
    parser = argparse.ArgumentParser(description='OKX 妯℃嫙鐩?+ Dashboard (甯﹀弬鏁版敮鎸佺増鏈?')
    parser.add_argument('--strategy', default='4.0', choices=['4.0', '5.2'], help='绛栫暐鐗堟湰')
    args = parser.parse_args()

    print("\n" + "="*60)
    print(f"CTS1 - OKX 妯℃嫙鐩?(Dashboard 妯″紡) | 绛栫暐鐗堟湰: {args.strategy}")
    print("="*60)
    print(f"浜ゆ槗瀵? {DEFAULT_SYMBOL}")
    print(f"K绾垮懆鏈? {DEFAULT_TIMEFRAME}")
    print("="*60 + "\n")
    
    # 鍒涘缓缁勪欢
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
    
    # 鍏堟樉寮忔墽琛岀儹韬互渚挎嬁鍒扮绾挎寚鏍?
    print("棰勭儹绛栫暐...")
    engine.warmup()
    
    # Dashboard 鏇存柊鍥炶皟
    dashboard = create_dashboard(port=5000)
    
    # 缁戝畾鏈€鏂扮増鐨勮矾鐢变綋绯?
    if args.strategy == '5.2':
        dashboard.register_strategy('default', 'Grid RSI V5.2 (妯℃嫙鐩?', route='/v5')
    else:
        dashboard.register_strategy('default', 'Grid RSI V4.0 (妯℃嫙鐩?', route='/')
        
    def on_status_update(status):
        dashboard.update(status)
    
    engine.register_status_callback(on_status_update)
    
    # 鍥炴斁鍘嗗彶浠ラ濉墠绔浘琛?
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
        
    # 鍦ㄥ悗鍙板惎鍔ㄥ紩鎿?
    engine_thread = threading.Thread(target=run_engine, args=(engine,))
    engine_thread.daemon = True
    engine_thread.start()
    
    # 涓荤嚎绋嬭繍琛?Dashboard
    print("Dashboard: http://localhost:5000")
    print("鎸?Ctrl+C 鍋滄\n")
    
    try:
        dashboard.start()
    except KeyboardInterrupt:
        print("\n姝ｅ湪鍋滄...")
        engine.stop()
        print("宸插仠姝?)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
