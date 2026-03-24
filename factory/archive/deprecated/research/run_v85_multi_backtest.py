import os
import sys
import json
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any
from multiprocessing import Pool, cpu_count

# 纭繚妯″潡璺緞
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from console.engines import BacktestEngine
from cartridges.strategies import GridStrategyV85
from cartridges.bridge.datafeeds import CSVDataFeed

def run_single_backtest(params: Dict[str, Any]) -> Dict[str, Any]:
    """鍗曟鍥炴祴杩愯鍑芥暟锛屼緵杩涚▼姹犺皟鐢?""
    mode = params['unlock_mode']
    lookback = params['lookback_hours']
    observe = params['observe_hours']
    data_path = params['data_path']
    start_date = params['start_date']
    end_date = params['end_date']
    range_mult = params.get('range_multiplier', 1.0)
    
    # 閲嶆柊鍒濆鍖栨暟鎹簮锛堟瘡涓繘绋嬬嫭绔嬶級
    data_feed = CSVDataFeed(
        filepath=data_path,
        symbol="BTC-USDT",
        timestamp_col="timestamp"
    )
    
    # 鍒濆鍖栫瓥鐣?
    strategy = GridStrategyV85(
        name=f"V85_{mode}_{lookback}h_{observe}h",
        symbol="BTC-USDT",
        initial_capital=10000.0,
        max_position_pct=0.8,
        unlock_mode=mode,
        lookback_hours=lookback,
        observe_hours=observe,
        range_multiplier=range_mult
    )
    
    # 鍒濆鍖栧紩鎿?
    engine = BacktestEngine(strategy, initial_capital=10000.0)
    
    # 杩愯鍥炴祴
    report = engine.run(data_feed, start=start_date, end=end_date, fast_mode=True)
    
    if report:
        return {
            'unlock_mode': mode,
            'lookback_hours': lookback,
            'observe_hours': observe,
            'range_multiplier': range_mult,
            'total_return': report['total_return'],
            'max_drawdown': report['max_drawdown'],
            'win_rate': report['win_rate'],
            'total_trades': report['total_trades'],
            'profit_factor': report['profit_factor']
        }
    return None

def run_multi_parameter_backtest():
    # 1. 閰嶇疆
    data_path = "data/btc_1m_2025.csv"
    start_date = datetime(2025, 3, 15)
    end_date = datetime(2025, 3, 31, 23, 59, 59)
    
    # 2. 鍙傛暟绌洪棿
    unlock_modes = ['fifo'] # 閲嶇偣娴嬭瘯 FIFO
    lookback_options = [4.0, 6.0] # 閲嶇偣娴嬭瘯闀垮懆鏈?
    observe_options = [1.5, 2.0]  # 閲嶇偣娴嬭瘯闀胯瀵熸湡
    range_multipliers = [1.0, 1.2, 1.5] # 鏂板锛氭祴璇曠綉鏍兼墿瀹?
    
    tasks = []
    for mode in unlock_modes:
        for lookback in lookback_options:
            for observe in observe_options:
                for r_mult in range_multipliers:
                    tasks.append({
                        'unlock_mode': mode,
                        'lookback_hours': lookback,
                        'observe_hours': observe,
                        'range_multiplier': r_mult,
                        'data_path': data_path,
                        'start_date': start_date,
                        'end_date': end_date
                    })
    
    total_runs = len(tasks)
    print(f"骞惰鍥炴祴鍚姩: 2025-03-15 鑷?2025-03-31")
    print(f"浣跨敤 CPU 鏍稿績鏁? {cpu_count()}")
    print(f"鍙傛暟缁勫悎鎬绘暟: {total_runs}")
    print(f"{'-'*90}")
    print(f"{'Mode':<5} | {'Look':<4} | {'Obs':<4} | {'Mult':<4} | {'Return':>8} | {'MDD':>8} | {'Trades':>6}")
    print(f"{'-'*90}")
    
    # 3. 浣跨敤杩涚▼姹犲苟琛岃繍琛?
    with Pool(processes=cpu_count()) as pool:
        results_raw = pool.map(run_single_backtest, tasks)
    
    # 4. 杩囨护缁撴灉
    results = [r for r in results_raw if r is not None]
    
    # 5. 鎵撳嵃缁撴灉
    for res in results:
        print(f"{res['unlock_mode']:<5} | {res['lookback_hours']:<4.1f} | {res['observe_hours']:<4.1f} | {res['range_multiplier']:<4.1f} | {res['total_return']*100:>7.2f}% | {res['max_drawdown']*100:>7.2f}% | {res['total_trades']:>6}")

    # 6. 淇濆瓨缁撴灉
    output_file = "multi_param_backtest_v85_phase2_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
        
    # 7. 鏈€浣崇粨鏋滄眹鎬?
    if results:
        best_return = max(results, key=lambda x: x['total_return'])
        best_mdd = min(results, key=lambda x: x['max_drawdown'])
        
        print(f"\n{'-'*80}")
        print(f"鏈€浣虫敹鐩婄粍鍚? {best_return['unlock_mode']} / {best_return['lookback_hours']}h / {best_return['observe_hours']}h / x{best_return['range_multiplier']} -> {best_return['total_return']*100:.2f}%")
        print(f"鏈€浣庡洖鎾ょ粍鍚? {best_mdd['unlock_mode']} / {best_mdd['lookback_hours']}h / {best_mdd['observe_hours']}h / x{best_mdd['range_multiplier']} -> {best_mdd['max_drawdown']*100:.2f}%")
        print(f"{'-'*90}")

if __name__ == "__main__":
    run_multi_parameter_backtest()
