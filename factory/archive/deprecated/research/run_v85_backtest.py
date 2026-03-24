import os
import sys
import json
from datetime import datetime

# 纭繚妯″潡璺緞
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from console.engines import BacktestEngine
from cartridges.strategies import GridStrategyV85
from cartridges.bridge.datafeeds import CSVDataFeed

def run_v85_backtest():
    # 1. 璺緞璁剧疆 (浣跨敤 3 鏈?16-22 鏃ョ殑绗簩鍛ㄦ暟鎹?
    data_path = "data/btc_1m_2025_03_week2.csv"
    if not os.path.exists(data_path):
        data_path = "data/btc_1m_2025.csv"
        print(f"[璀﹀憡] 鏈壘鍒板懆鏁版嵁锛岄檷绾т娇鐢ㄥ叏閲忔暟鎹? {data_path}")
    
    # 2. 鍒濆鍖栫瓥鐣?
    strategy = GridStrategyV85(
        name="Grid_V85_Jeff_Mar2025",
        symbol="BTC-USDT",
        initial_capital=10000.0,
        max_position_pct=0.8
    )
    
    # 3. 鍒濆鍖栨暟鎹簮
    data_feed = CSVDataFeed(
        filepath=data_path,
        symbol="BTC-USDT",
        timestamp_col="timestamp"
    )
    
    # 4. 鍒濆鍖栧紩鎿?
    engine = BacktestEngine(strategy, initial_capital=10000.0)
    
    # 5. 杩愯鍥炴祴
    print(f"\n{'='*60}")
    print(f"绛栫暐 8.5 (Jeff Huang) 2025骞?鏈堝洖娴嬪惎鍔?)
    print(f"鏁版嵁婧? {data_path}")
    print(f"{'='*60}\n")
    
    report = engine.run(data_feed)
    
    # 6. 鎵撳嵃缁撴灉
    engine.print_report(report)
    
    # 7. 淇濆瓨璇︾粏浜ゆ槗璁板綍渚夸簬鍒嗘瀽
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
    
    print(f"\n[瀹屾垚] 绛栫暐 8.5 鍥炴祴缁撴潫銆?)
    print(f"璇︾粏浜ゆ槗璁板綍宸蹭繚瀛樿嚦: {output_file}")

if __name__ == "__main__":
    run_v85_backtest()
