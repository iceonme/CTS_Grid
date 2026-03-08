import sys
import os
import time
import json
import random
import multiprocessing
import pandas as pd
import numpy as np

# 自动处理路径：添加项目根目录到 sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from engines.backtest import BacktestEngine
from datafeeds.csv_feed import CSVDataFeed
from executors.paper import PaperExecutor

# 策略映射
from strategies.grid_mtf_6_0 import GridMTFStrategyV6_0
from strategies.grid_mtf_6_1 import GridMTFStrategyV6_1
from strategies.grid_mtf_6_2 import GridMTFStrategyV6_2
from strategies.grid_mtf_6_3 import GridMTFStrategyV6_3
from strategies.grid_mtf_6_4 import GridMTFStrategyV6_4
from strategies.grid_mtf_6_5 import GridMTFStrategyV6_5
from strategies.grid_mtf_7_1_victory import GridMTFStrategyV7_1
from strategies.zen_7_1 import Zen71Strategy

STRATEGY_MAP = {
    "grid_mtf_6_0": GridMTFStrategyV6_0,
    "grid_mtf_6_1": GridMTFStrategyV6_1,
    "grid_mtf_6_2": GridMTFStrategyV6_2,
    "grid_mtf_6_3": GridMTFStrategyV6_3,
    "grid_mtf_6_4": GridMTFStrategyV6_4,
    "grid_mtf_6_5": GridMTFStrategyV6_5,
    "grid_mtf_7_1": GridMTFStrategyV7_1,
    "zen_7_1": Zen71Strategy
}

# 默认搜索空间
SEARCH_SPACE_MTF = {
    'rsi_buy_threshold': (20, 45),
    'rsi_sell_threshold': (60, 85),
    'macd_fast': (8, 16),
    'macd_slow': (22, 35),
    'macd_signal': (7, 12),
    'atr_blackswan_mult': (2.5, 6.0),
    'grid_layers': (3, 8),
    'grid_buffer': (0.01, 0.05),
    'grid_readjust': (0.02, 0.10),
    'atr_sl_mult': (3.0, 10.0),
    'grid_buy_cooldown': (1.0, 6.0)
}

SEARCH_SPACE_ZEN = {
    "resample_min": [30, 45, 60, 90, 120, 150, 180],
    "grid_layers": [4, 6, 8, 10, 12, 14, 16],
    "grid_drop_pct": [0.015, 0.02, 0.025, 0.03, 0.035, 0.04, 0.045],
    "hard_sl_pct": [-0.15, -0.20, -0.25, -0.30, -0.40],
    "tp_min_profit_pct": [0.01, 0.015, 0.02, 0.025, 0.03, 0.04]
}

def run_single_backtest(args):
    """单核任务封装"""
    task_id, strategy_key, params, csv_path = args
    try:
        # 重定向 stdout 以保持终端整洁
        old_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')
        
        executor = PaperExecutor(initial_capital=10000.0, fast_mode=True)
        feed = CSVDataFeed(filepath=csv_path, symbol="BTCUSDT")
        
        StrategyClass = STRATEGY_MAP.get(strategy_key)
        if not StrategyClass:
            return {'error': f"Unknown strategy {strategy_key}"}
            
        strategy = StrategyClass(name=f"Opt-{task_id}", **params)
        engine = BacktestEngine(strategy=strategy, executor=executor)
        
        report = engine.run(feed, fast_mode=True)
        
        # 还原 stdout
        sys.stdout.close()
        sys.stdout = old_stdout
        
        # 提取关键指标
        res = {
            'task_id': task_id,
            'score': 0.0,
            'return': report.get('total_return', 0),
            'mdd': report.get('max_drawdown', 0),
            'sharpe': report.get('sharpe_ratio', 0),
            'trades': report.get('total_trades', 0),
            'win_rate': report.get('win_rate', 0),
            'params': params
        }
        
        # 评分函数 (收益/风险比 * 夏普)
        if res['trades'] < 10:
            res['score'] = -100
        else:
            # Score = (Return * 100) * (Sharpe + 0.5) / (MaxDD * 100 + 5)
            res['score'] = (res['return'] * 100.0) * (res['sharpe'] + 0.5) / (res['mdd'] * 100.0 + 5.0)
            
        return res
    except Exception as e:
        return {'task_id': task_id, 'error': str(e)}

def get_random_params(strategy_key):
    space = SEARCH_SPACE_ZEN if "zen" in strategy_key else SEARCH_SPACE_MTF
    p = {}
    for k, v in space.items():
        if isinstance(v, list):
            p[k] = random.choice(v)
        elif isinstance(v[0], int) and isinstance(v[1], int):
            p[k] = random.randint(v[0], v[1])
        else:
            p[k] = round(random.uniform(v[0], v[1]), 4)
    return p

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--strategy", type=str, default="zen_7_1")
    parser.add_argument("--procs", type=int, default=min(os.cpu_count(), 6))
    args = parser.parse_args()

    csv_path = os.path.join(BASE_DIR, "data", "btc_1m_2025.csv")
    s_key = args.strategy
    iterations = args.iterations
    
    print("\n" + "="*60)
    print(f"CTS 并发调优引擎 [Zen/MTF 适配版]")
    print(f"策略: {s_key} | 采样: {iterations} | 核心: {args.procs}")
    print("="*60)
    
    start_time = time.time()
    log_file = os.path.join(BASE_DIR, "optimizer", f"study_log_{s_key}.csv")
    if os.path.exists(log_file): os.remove(log_file)
    
    tasks = [(i, s_key, get_random_params(s_key), csv_path) for i in range(iterations)]
    
    all_results = []
    
    # 启动进程池
    with multiprocessing.Pool(processes=args.procs) as pool:
        for res in pool.imap_unordered(run_single_backtest, tasks):
            if 'error' in res:
                print(f"  [Error] Task {res.get('task_id')}: {res['error']}")
                continue
                
            all_results.append(res)
            
            # 记录日志
            row = {'score': res['score'], 'return': res['return'], 'mdd': res['mdd'], 'sharpe': res['sharpe'], 'trades': res['trades'], 'win_rate': res['win_rate']}
            row.update(res['params'])
            df = pd.DataFrame([row])
            df.to_csv(log_file, mode='a', index=False, header=not os.path.exists(log_file))
            
            # 打印进度
            best_score = max([r['score'] for r in all_results])
            print(f"  [{len(all_results)}/{iterations}] Score={res['score']:.2f} | Best={best_score:.2f} | Time={time.time()-start_time:.1f}s")

    if not all_results:
        print("无有效结果。")
        return

    all_results.sort(key=lambda x: x['score'], reverse=True)
    best = all_results[0]
    
    print("\n" + "-"*30)
    print(f"调优完成！最佳配置 ({s_key}):")
    print(f"  收益: {best['return']*100:.2f}% | 回撤: {best['mdd']*100:.2f}% | 夏普: {best['sharpe']:.2f}")
    print(f"  参数: {json.dumps(best['params'])}")
    print(f"总耗时: {time.time() - start_time:.2f}s")

    with open(os.path.join(BASE_DIR, "optimizer", f"best_params_{s_key}.json"), 'w') as f:
        json.dump(best['params'], f, indent=4)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
