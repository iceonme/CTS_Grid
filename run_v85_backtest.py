import os
import sys
import json
from datetime import datetime

# 确保模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engines import BacktestEngine
from strategies import GridStrategyV85
from datafeeds import CSVDataFeed

def run_v85_backtest():
    # 1. 路径设置 (使用 3 月 16-22 日的第二周数据)
    data_path = "data/btc_1m_2025_03_week2.csv"
    if not os.path.exists(data_path):
        data_path = "data/btc_1m_2025.csv"
        print(f"[警告] 未找到周数据，降级使用全量数据: {data_path}")
    
    # 2. 初始化策略
    strategy = GridStrategyV85(
        name="Grid_V85_Jeff_Mar2025",
        symbol="BTC-USDT",
        initial_capital=10000.0,
        max_position_pct=0.8
    )
    
    # 3. 初始化数据源
    data_feed = CSVDataFeed(
        filepath=data_path,
        symbol="BTC-USDT",
        timestamp_col="timestamp"
    )
    
    # 4. 初始化引擎
    engine = BacktestEngine(strategy, initial_capital=10000.0)
    
    # 5. 运行回测
    print(f"\n{'='*60}")
    print(f"策略 8.5 (Jeff Huang) 2025年3月回测启动")
    print(f"数据源: {data_path}")
    print(f"{'='*60}\n")
    
    report = engine.run(data_feed)
    
    # 6. 打印结果
    engine.print_report(report)
    
    # 7. 保存详细交易记录便于分析
    output_file = "trading_trades_grid_v85_mar2025.json"
    trades_dict = []
    for t in report.get('trades', []):
        trade_data = t.__dict__.copy()
        if isinstance(trade_data['timestamp'], datetime):
            trade_data['timestamp'] = trade_data['timestamp'].isoformat()
        if hasattr(trade_data['side'], 'name'):
            trade_data['side'] = trade_data['side'].name
        trades_dict.append(trade_data)
        
    with open(output_file, "w") as f:
        json.dump(trades_dict, f, indent=2)
    
    print(f"\n[完成] 策略 8.5 回测结束。")
    print(f"详细交易记录已保存至: {output_file}")

if __name__ == "__main__":
    run_v85_backtest()
