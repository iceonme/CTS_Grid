"""
CTS Arena - 2025 全年高速回测工具
用法: python run_backtest_arena.py --strategy grid_rsi_5_2 --params "rsi_period=14"
"""

import sys
import os
import time
import argparse
import json
from datetime import datetime

# 自动处理路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from engines.backtest import BacktestEngine
from datafeeds.csv_feed import CSVDataFeed
from executors.paper import PaperExecutor

def run_arena(strategy_name: str, params: dict, csv_path: str):
    # 1. 动态加载策略 (Skill-based loading)
    try:
        if strategy_name == "grid_rsi_5_2":
            from strategies.grid_rsi_5_2 import GridRSIStrategyV5_2 as StrategyClass
        elif strategy_name == "grid_mtf_6_0":
            from strategies.grid_mtf_6_0 import GridMTFStrategyV6_0 as StrategyClass
        elif strategy_name == "grid_mtf_6_1":
            from strategies.grid_mtf_6_1 import GridMTFStrategyV6_1 as StrategyClass
        elif strategy_name == "grid_mtf_6_2":
            from strategies.grid_mtf_6_2 import GridMTFStrategyV6_2 as StrategyClass
        elif strategy_name == "grid_mtf_6_3":
            from strategies.grid_mtf_6_3 import GridMTFStrategyV6_3 as StrategyClass
        elif strategy_name == "grid_mtf_6_4":
            from strategies.grid_mtf_6_4 import GridMTFStrategyV6_4 as StrategyClass
        elif strategy_name == "grid_mtf_6_5":
            from strategies.grid_mtf_6_5 import GridMTFStrategyV6_5 as StrategyClass
        elif strategy_name == "grid_jeff_6_5":
            from strategies.grid_jeff_6_5 import GridJeff65Strategy as StrategyClass
        elif strategy_name == "grid_mtf_7_0":
            from strategies.grid_mtf_7_0_dragon import GridMTFStrategyV7_0 as StrategyClass
        elif strategy_name == "grid_mtf_7_1":
            from strategies.grid_mtf_7_1_victory import GridMTFStrategyV7_1 as StrategyClass
        elif strategy_name == "grid_zen_6_5":
            from strategies.grid_6_5_zen import GridZen65Strategy as StrategyClass
        elif strategy_name == "zen_7":
            from strategies.zen_7 import Zen7Strategy as StrategyClass
        elif strategy_name == "zen_7_1":
            from strategies.zen_7_1 import Zen71Strategy as StrategyClass
        elif strategy_name == "grid_rsi_4_0":
            # 动态添加路径以加载归档策略
            sys.path.append(os.path.join(os.path.dirname(__file__), "deprecated", "v4_legacy"))
            from grid_rsi import GridRSIStrategy as StrategyClass
        else:
            print(f"未知策略: {strategy_name}")
            return
    except ImportError as e:
        print(f"加载策略失败: {e}")
        return

    # 实例化策略
    if strategy_name == "grid_rsi_5_2":
        strategy = StrategyClass(symbol="BTCUSDT", **params)
    elif strategy_name == "grid_mtf_6_0":
        # V6.0 可能内部会处理 symbol
        strategy = StrategyClass(name=f"Arena-{strategy_name}", **params)
    elif strategy_name == "grid_mtf_6_1":
        strategy = StrategyClass(name=f"Arena-{strategy_name}", **params)
    elif strategy_name == "grid_mtf_6_2":
        strategy = StrategyClass(name=f"Arena-{strategy_name}", **params)
    elif strategy_name == "grid_mtf_6_3":
        strategy = StrategyClass(name=f"Arena-{strategy_name}", **params)
    elif strategy_name == "grid_mtf_6_4":
        strategy = StrategyClass(name=f"Arena-{strategy_name}", **params)
    elif strategy_name == "grid_mtf_6_5":
        strategy = StrategyClass(name=f"Arena-{strategy_name}", **params)
    elif strategy_name == "grid_jeff_6_5":
        strategy = StrategyClass(name=f"Arena-{strategy_name}", **params)
    elif strategy_name == "grid_mtf_7_0":
        strategy = StrategyClass(name=f"Arena-{strategy_name}", **params)
    elif strategy_name == "grid_mtf_7_1":
        strategy = StrategyClass(name=f"Arena-{strategy_name}", **params)
    elif strategy_name == "grid_zen_6_5":
        strategy = StrategyClass(name=f"Arena-{strategy_name}", **params)
    elif strategy_name == "zen_7":
        strategy = StrategyClass(name=f"Arena-{strategy_name}", **params)
    elif strategy_name == "zen_7_1":
        strategy = StrategyClass(name=f"Arena-{strategy_name}", **params)
    elif strategy_name == "grid_rsi_4_0":
        strategy = StrategyClass(symbol="BTCUSDT", **params)
    else:
        strategy = StrategyClass(name=f"Arena-{strategy_name}", **params)
    
    # 2. 初始化高速执行层和数据层
    executor = PaperExecutor(initial_capital=10000.0, fast_mode=True)
    feed = CSVDataFeed(filepath=csv_path, symbol="BTCUSDT")
    
    # 3. 运行回测引擎 (Fast Mode)
    engine = BacktestEngine(strategy=strategy, executor=executor)
    
    start_time = time.time()
    print(f"\n[Arena] 正在启动 2025 全年回测...")
    print(f"[Arena] 策略: {strategy_name} | 数据: {os.path.basename(csv_path)}")
    
    report = engine.run(feed, fast_mode=True)
    
    duration = time.time() - start_time
    
    # 4. 输出结果
    print("\n" + "="*60)
    print(f"回测战报 - {strategy_name} (2025)")
    print("="*60)
    print(f"处理耗时:   {duration:.2f} 秒")
    print(f"总收益率:   {report['total_return']*100:.2f}%")
    print(f"最大回撤:   {report['max_drawdown']*100:.2f}%")
    print(f"夏普比率:   {report['sharpe_ratio']:.2f}")
    print(f"盈亏比:     {report['profit_factor']:.2f}")
    print(f"胜率:       {report['win_rate']*100:.2f}%")
    print(f"交易总数:   {report['total_trades']}")
    print("="*60)
    
    # 保存结果
    result_file = f"arena_result_{strategy_name}_{datetime.now().strftime('%H%M%S')}.json"
    with open(result_file, 'w') as f:
        # 只保存标量数据，不保存巨大的 equity_curve 数组
        summary = {k: v for k, v in report.items() if k not in ['equity_curve', 'trades', 'signals']}
        json.dump(summary, f, indent=4)
    print(f"[Arena] 摘要已保存至: {result_file}")

    # 5. 自动可视化
    try:
        from plot_arena_results import plot_results
        img_path = plot_results(result_file)
        if img_path:
            print(f"[Arena] 可视化曲线已生成: {img_path}")
    except Exception as e:
        print(f"[Arena] 可视化失败: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CTS Arena Backtest")
    parser.add_argument("--strategy", type=str, default="grid_rsi_5_2", help="策略名称")
    parser.add_argument("--params", type=str, default="{}", help="JSON 格式参数")
    parser.add_argument("--data", type=str, default="data/btc_1m_2025.csv", help="数据路径")
    
    args = parser.parse_args()
    
    try:
        params_dict = json.loads(args.params.replace("'", '"'))
    except:
        params_dict = {}
        
    run_arena(args.strategy, params_dict, args.data)
