import os
import sys
import time
from datetime import datetime

# 确保模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engines.live import LiveEngine
from executors.paper import PaperExecutor
from datafeeds.csv_feed import CSVDataFeed
from strategies.grid_v85 import GridStrategyV85
from dashboard import create_dashboard

def run_v85_replay():
    # 1. 路径设置
    data_path = "data/btc_1m_2025_03_week.csv"
    if not os.path.exists(data_path):
        print(f"Error: {data_path} not found. Please run scripts/extract_mar_week.py first.")
        return
        
    # 2. 启动 Dashboard
    port = 5005
    dashboard = create_dashboard(port=port)
    dashboard.register_strategy('v85_replay', 'Strategy 8.5 (Jeff Huang) - Mar 2025 Replay', route='/v5')
    dashboard.start_background()
    print(f"\n[Dashboard] Started at http://localhost:{port}/v5?strategy_id=v85_replay")
    print("[Dashboard] 请在 3 秒内打开浏览器并进入上述页面...")
    time.sleep(3) # 给用户一点时间打开页面
    
    # 3. 初始化组件
    strategy = GridStrategyV85(
        name="V85_Mar_Replay",
        symbol="BTC-USDT",
        initial_capital=10000.0,
        max_position_pct=0.8,
        rsi_period=14,      # 可在此修改试验
        observe_hours=2.0    # 可在此修改试验
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
    
    print(f"\n[DEBUG] 初始资金确认: {executor.get_cash():.2f}")

    # 4. 注册状态回调
    def on_status_update(status):
        dashboard.update(status, strategy_id='v85_replay')
    
    engine.register_status_callback(on_status_update)
    
    print(f"\n{'='*60}")
    print(f"策略 8.5 (Jeff Huang) 高速回测重演启动")
    print(f"时间范围: 2025-03-10 至 2025-03-16")
    print(f"重演速度: 5ms/bar")
    print(f"{'='*60}\n")
    
    engine.is_running = True
    
    count = 0
    try:
        for data in engine.data_feed.stream():
            if not engine.is_running: break
            
            engine._current_time = data.timestamp
            engine._current_prices[data.symbol] = data.close
            
            # 更新执行器
            engine.executor.update_market_data(data.timestamp, data.close)
            
            # 策略决策
            context = engine._get_context()
            signals = engine.strategy.on_data(data, context)
            
            # 执行
            if signals:
                engine._execute_signals(signals)
            
            # 推送状态
            status = engine._build_status(data)
            
            # 注入网格线和状态元数据
            st_raw = engine.strategy.get_status(context)
            status['grid_lines'] = st_raw.get('grid_lines', [])
            status['strategy_state'] = st_raw.get('state', 'Warmup')
            status['rsi'] = st_raw.get('rsi', 50)
            
            if count < 5:
                print(f"[DEBUG Step {count}] Time: {data.timestamp} | Price: {data.close:.2f} | TotalValue: {status['total_value']:.2f} | Cash: {status['cash']:.2f}")

            on_status_update(status)
            count += 1
            time.sleep(0.005)
            
    except KeyboardInterrupt:
        print("\nReplay Interrupted by User")
        engine.stop()
        
    print(f"\n[Done] Replay Finished.")

if __name__ == "__main__":
    run_v85_replay()
