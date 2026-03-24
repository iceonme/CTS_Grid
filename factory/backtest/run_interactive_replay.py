import os
import sys
import time
from datetime import datetime

# 自动处理路径 - 向上寻找项目根目褰?
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

print(f"[REPLAY] Starting script at {datetime.now()}")

try:
    from console.engines.live import LiveEngine
    from cartridges.bridge.executors.paper import PaperExecutor
    from cartridges.bridge.datafeeds.csv_feed import CSVDataFeed
    from cartridges.strategies.grid_v85 import GridStrategyV85
    from console.dashboard import create_dashboard
    print("[REPLAY] Imports successful.")
except Exception as e:
    print(f"[REPLAY] Import error: {e}")
    sys.exit(1)

def run_v85_replay():
    # 1. 路径设置
    data_path = "data/btc_1m_2025_03_16.csv"
    if not os.path.exists(data_path):
        print(f"Error: {data_path} not found. Please run scripts/extract_mar_week_16_22.py first.")
        return
        
    # 2. 启动 Dashboard
    print("[REPLAY] Initializing Dashboard...")
    port = 5005
    dashboard = create_dashboard(port=port)
    dashboard.register_strategy('v85_replay', 'Strategy 8.5 (Jeff Huang) - Mar 16-22 Replay', route='/v5')
    dashboard.start_background()
    print(f"[REPLAY] Dashboard started in background at http://localhost:{port}/v5?strategy_id=v85_replay")
    
    # 3. 初始化组浠?
    print("[REPLAY] Initializing Strategy and Engine...")
    strategy = GridStrategyV85(
        name="V85_Mar_16_22_Replay",
        symbol="BTC-USDT",
        initial_capital=10000.0,
        max_position_pct=0.8,
        rsi_period=14,
        observe_hours=2.0
    )
    
    data_feed = CSVDataFeed(
        filepath=data_path,
        symbol="BTC-USDT",
        timestamp_col="timestamp"
    )
    
    executor = PaperExecutor(initial_capital=10000.0, fee_rate=0.001)
    
    engine = LiveEngine(
        strategy=strategy,
        executor=executor,
        data_feed=data_feed
    )
    
    print(f"[REPLAY] Initial Cash: {executor.get_cash():.2f}")

    # 4. 注册鐘舵€佸洖璋?
    def on_status_update(status):
        dashboard.update(status, strategy_id='v85_replay')
    
    engine.register_status_callback(on_status_update)
    
    # 5. 预加杞?240 根历鍙?K 绾?(满足 4 小时计算闇€姹?
    print("[REPLAY] Pre-loading 240 bars (4 hours) for indicator warmup...")
    warmup_count = 0
    # 为保证数据连缁€э紝我们临时使用提取出来的完整日线数鎹?
    for data in engine.data_feed.stream():
        engine.strategy._data_1m.append(data)
        engine._sync_history_candles(data)
        warmup_count += 1
        if warmup_count >= 240:
            break
    print(f"[REPLAY] Pre-loaded {warmup_count} bars.")
    
    print("\n" + "="*60)
    print("STARTING REplay LOOP (5ms per bar)")
    print("="*60 + "\n")
    
    engine.is_running = True
    count = 0
    try:
        # **重要**: 不要重新执行 for data in stream，接鐫€上面的生成器继续跑！
        # 但目鍓?CSV 迭代器没鏈?reset 鎴?stateful 支持，我们需重开流并快进过去
        stream = engine.data_feed.stream()
        for _ in range(240):
            next(stream)
            
        for data in stream:
            if not engine.is_running: break
            
            engine._current_time = data.timestamp
            engine._current_prices[data.symbol] = data.close
            
            # 更新执行器并同步 K 绾?
            engine.executor.update_market_data(data.timestamp, data.close)
            engine._sync_history_candles(data)
            
            # 策略决策
            context = engine._get_context()
            signals = engine.strategy.on_data(data, context)
            
            # 执行
            if signals:
                engine._execute_signals(signals)
            
            # 鎺ㄩ€佺姸鎬?
            status = engine._build_status(data)
            
            # 注入网格信息
            st_raw = engine.strategy.get_status(context)
            status['grid_lines'] = st_raw.get('grid_lines', [])
            status['strategy_state'] = st_raw.get('state', 'Unknown')
            
            on_status_update(status)
            
            count += 1
            if count % 20 == 0:
                print(f"[REPLAY PROGRESS] {data.timestamp} | {count} bars | Price: {data.close:.2f} | PnL: {status['pnl_pct']:.2f}% | History: {len(status['history_candles'])}")
            
            time.sleep(0.005)
            
    except KeyboardInterrupt:
        print("\nReplay Interrupted by User")
    except Exception as e:
        print(f"\n[REPLAY ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        engine.stop()
        
    print(f"\n[Done] Replay Finished at {datetime.now()}. Processed {count} bars.")

if __name__ == "__main__":
    run_v85_replay()
