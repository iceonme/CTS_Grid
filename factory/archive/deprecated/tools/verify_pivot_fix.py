
import sys
import os
from pathlib import Path
from datetime import datetime

# 纭繚椤圭洰鏍圭洰褰曞湪 path 涓?
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cartridges.strategies.grid_rsi_5_2 import GridRSIStrategyV5_2
from console.core import MarketData

def test_pivot_timestamps():
    print("Testing pivot timestamps in GridRSIStrategyV5_2...")
    
    # 鍒濆鍖栫瓥鐣?
    strat = GridRSIStrategyV5_2(symbol="BTC-USDT")
    strat.initialize()
    
    # 妯℃嫙鏁版嵁
    # 鎴戜滑闇€瑕佹ā鎷熻冻澶熺殑 K 绾挎潵瀹屾垚棰勭儹骞惰Е鍙?pivot 璁＄畻
    # GridEngine.find_pivots 闇€瑕佽嚦灏?pivot_window + 1 鏍?K 绾?
    # IncrementalIndicators 闇€瑕?warmup_done
    
    warmup_period = max(strat.params['rsi_period'], strat.params['macd_slow'] + strat.params['macd_signal']) + 10
    
    for i in range(warmup_period):
        ts = datetime(2023, 1, 1, 0, i)
        # 鍒堕€犱竴涓槑鏄剧殑娉㈡鐐?
        if i == 10:
            price = 20000.0  # High
        elif i == 20:
            price = 10000.0  # Low
        else:
            price = 15000.0
            
        data = MarketData(
            symbol="BTC-USDT",
            timestamp=ts,
            open=price,
            high=price + 10,
            low=price - 10,
            close=price,
            volume=100
        )
        class MockContext:
            def __init__(self):
                self.positions = {}
        
        strat.on_data(data, MockContext())
        
    status = strat.get_status()
    pivots = status.get('pivots', {})
    ph = pivots.get('pivots_high', [])
    pl = pivots.get('pivots_low', [])
    
    print(f"Pivots High: {ph}")
    print(f"Pivots Low: {pl}")
    
    # 妫€鏌?time 瀛楁
    success = True
    if not ph and not pl:
        print("Warning: No pivots found in test data.")
    
    for p in ph + pl:
        if 'time' not in p:
            print(f"Error: Pivot missing 'time' field: {p}")
            success = False
        else:
            print(f"OK: Pivot has time: {p['time']}")
            
    if success and (ph or pl):
        print("\nTest PASSED: Pivot timestamps are present.")
    elif not ph and not pl:
        print("\nTest inconclusive: No pivots generated.")
    else:
        print("\nTest FAILED.")

if __name__ == "__main__":
    test_pivot_timestamps()
