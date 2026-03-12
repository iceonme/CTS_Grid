import os
import sys
import json
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any
from multiprocessing import Pool, cpu_count

# 确保模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engines import BacktestEngine
from strategies import GridStrategyV85
from datafeeds import CSVDataFeed

def run_single_backtest(params: Dict[str, Any]) -> Dict[str, Any]:
    """单次回测运行函数，供进程池调用"""
    mode = params['unlock_mode']
    lookback = params['lookback_hours']
    observe = params['observe_hours']
    data_path = params['data_path']
    start_date = params['start_date']
    end_date = params['end_date']
    range_mult = params.get('range_multiplier', 1.0)
    
    # 重新初始化数据源（每个进程独立）
    data_feed = CSVDataFeed(
        filepath=data_path,
        symbol="BTC-USDT",
        timestamp_col="timestamp"
    )
    
    # 初始化策略
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
    
    # 初始化引擎
    engine = BacktestEngine(strategy, initial_capital=10000.0)
    
    # 运行回测
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
    # 1. 配置
    data_path = "data/btc_1m_2025.csv"
    start_date = datetime(2025, 3, 15)
    end_date = datetime(2025, 3, 31, 23, 59, 59)
    
    # 2. 参数空间
    unlock_modes = ['fifo'] # 重点测试 FIFO
    lookback_options = [4.0, 6.0] # 重点测试长周期
    observe_options = [1.5, 2.0]  # 重点测试长观察期
    range_multipliers = [1.0, 1.2, 1.5] # 新增：测试网格扩容
    
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
    print(f"并行回测启动: 2025-03-15 至 2025-03-31")
    print(f"使用 CPU 核心数: {cpu_count()}")
    print(f"参数组合总数: {total_runs}")
    print(f"{'-'*90}")
    print(f"{'Mode':<5} | {'Look':<4} | {'Obs':<4} | {'Mult':<4} | {'Return':>8} | {'MDD':>8} | {'Trades':>6}")
    print(f"{'-'*90}")
    
    # 3. 使用进程池并行运行
    with Pool(processes=cpu_count()) as pool:
        results_raw = pool.map(run_single_backtest, tasks)
    
    # 4. 过滤结果
    results = [r for r in results_raw if r is not None]
    
    # 5. 打印结果
    for res in results:
        print(f"{res['unlock_mode']:<5} | {res['lookback_hours']:<4.1f} | {res['observe_hours']:<4.1f} | {res['range_multiplier']:<4.1f} | {res['total_return']*100:>7.2f}% | {res['max_drawdown']*100:>7.2f}% | {res['total_trades']:>6}")

    # 6. 保存结果
    output_file = "multi_param_backtest_v85_phase2_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
        
    # 7. 最佳结果汇总
    if results:
        best_return = max(results, key=lambda x: x['total_return'])
        best_mdd = min(results, key=lambda x: x['max_drawdown'])
        
        print(f"\n{'-'*80}")
        print(f"最佳收益组合: {best_return['unlock_mode']} / {best_return['lookback_hours']}h / {best_return['observe_hours']}h / x{best_return['range_multiplier']} -> {best_return['total_return']*100:.2f}%")
        print(f"最低回撤组合: {best_mdd['unlock_mode']} / {best_mdd['lookback_hours']}h / {best_mdd['observe_hours']}h / x{best_mdd['range_multiplier']} -> {best_mdd['max_drawdown']*100:.2f}%")
        print(f"{'-'*90}")

if __name__ == "__main__":
    run_multi_parameter_backtest()
