"""
CTS Arena - 2025 鍏ㄥ勾楂橀€熷洖娴嬪伐鍏?
鐢ㄦ硶: python run_backtest_arena.py --strategy grid_rsi_5_2 --params "rsi_period=14"
"""

import sys
import os
import time
import argparse
import json
from datetime import datetime

# 鑷姩澶勭悊璺緞 - 鍚戜笂瀵绘壘椤圭洰鏍圭洰褰?
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from console.engines.backtest import BacktestEngine
from cartridges.bridge.datafeeds.csv_feed import CSVDataFeed
from cartridges.bridge.executors.paper import PaperExecutor

def run_arena(strategy_name: str, params: dict, csv_path: str):
    # 1. 鍔ㄦ€佸姞杞界瓥鐣?(Skill-based loading)
    try:
        if strategy_name == "grid_rsi_5_2":
            from cartridges.strategies.grid_rsi_5_2 import GridRSIStrategyV5_2 as StrategyClass
        elif strategy_name == "grid_mtf_6_0":
            from cartridges.strategies.grid_mtf_6_0 import GridMTFStrategyV6_0 as StrategyClass
        elif strategy_name == "grid_mtf_6_1":
            from cartridges.strategies.grid_mtf_6_1 import GridMTFStrategyV6_1 as StrategyClass
        elif strategy_name == "grid_mtf_6_2":
            from cartridges.strategies.grid_mtf_6_2 import GridMTFStrategyV6_2 as StrategyClass
        elif strategy_name == "grid_mtf_6_3":
            from cartridges.strategies.grid_mtf_6_3 import GridMTFStrategyV6_3 as StrategyClass
        elif strategy_name == "grid_mtf_6_4":
            from cartridges.strategies.grid_mtf_6_4 import GridMTFStrategyV6_4 as StrategyClass
        elif strategy_name == "grid_mtf_6_5":
            from cartridges.strategies.grid_mtf_6_5 import GridMTFStrategyV6_5 as StrategyClass
        elif strategy_name == "grid_jeff_6_5":
            from cartridges.strategies.grid_jeff_6_5 import GridJeff65Strategy as StrategyClass
        elif strategy_name == "grid_mtf_7_0":
            from cartridges.strategies.grid_mtf_7_0_dragon import GridMTFStrategyV7_0 as StrategyClass
        elif strategy_name == "grid_mtf_7_1":
            from cartridges.strategies.grid_mtf_7_1_victory import GridMTFStrategyV7_1 as StrategyClass
        elif strategy_name == "grid_zen_6_5":
            from cartridges.strategies.grid_6_5_zen import GridZen65Strategy as StrategyClass
        elif strategy_name == "zen_7":
            from cartridges.strategies.zen_7 import Zen7Strategy as StrategyClass
        elif strategy_name == "zen_7_1":
            from cartridges.strategies.zen_7_1 import Zen71Strategy as StrategyClass
        elif strategy_name == "grid_rsi_4_0":
            # 鍔ㄦ€佹坊鍔犺矾寰勪互鍔犺浇褰掓。绛栫暐
            sys.path.append(os.path.join(os.path.dirname(__file__), "deprecated", "v4_legacy"))
            from grid_rsi import GridRSIStrategy as StrategyClass
        else:
            print(f"鏈煡绛栫暐: {strategy_name}")
            return
    except ImportError as e:
        print(f"鍔犺浇绛栫暐澶辫触: {e}")
        return

    # 瀹炰緥鍖栫瓥鐣?
    if strategy_name == "grid_rsi_5_2":
        strategy = StrategyClass(symbol="BTCUSDT", **params)
    elif strategy_name == "grid_mtf_6_0":
        # V6.0 鍙兘鍐呴儴浼氬鐞?symbol
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
    
    # 2. 鍒濆鍖栭珮閫熸墽琛屽眰鍜屾暟鎹眰
    executor = PaperExecutor(initial_capital=10000.0, fast_mode=True)
    feed = CSVDataFeed(filepath=csv_path, symbol="BTCUSDT")
    
    # 3. 杩愯鍥炴祴寮曟搸 (Fast Mode)
    engine = BacktestEngine(strategy=strategy, executor=executor)
    
    start_time = time.time()
    print(f"\n[Arena] 姝ｅ湪鍚姩 2025 鍏ㄥ勾鍥炴祴...")
    print(f"[Arena] 绛栫暐: {strategy_name} | 鏁版嵁: {os.path.basename(csv_path)}")
    
    report = engine.run(feed, fast_mode=True)
    
    duration = time.time() - start_time
    
    # 4. 杈撳嚭缁撴灉
    print("\n" + "="*60)
    print(f"鍥炴祴鎴樻姤 - {strategy_name} (2025)")
    print("="*60)
    print(f"澶勭悊鑰楁椂:   {duration:.2f} 绉?)
    print(f"鎬绘敹鐩婄巼:   {report['total_return']*100:.2f}%")
    print(f"鏈€澶у洖鎾?   {report['max_drawdown']*100:.2f}%")
    print(f"澶忔櫘姣旂巼:   {report['sharpe_ratio']:.2f}")
    print(f"鐩堜簭姣?     {report['profit_factor']:.2f}")
    print(f"鑳滅巼:       {report['win_rate']*100:.2f}%")
    print(f"浜ゆ槗鎬绘暟:   {report['total_trades']}")
    print("="*60)
    
    # 淇濆瓨缁撴灉
    result_file = f"arena_result_{strategy_name}_{datetime.now().strftime('%H%M%S')}.json"
    with open(result_file, 'w') as f:
        # 鍙繚瀛樻爣閲忔暟鎹紝涓嶄繚瀛樺法澶х殑 equity_curve 鏁扮粍
        summary = {k: v for k, v in report.items() if k not in ['equity_curve', 'trades', 'signals']}
        json.dump(summary, f, indent=4)
    print(f"[Arena] 鎽樿宸蹭繚瀛樿嚦: {result_file}")

    # 5. 鑷姩鍙鍖?
    try:
        from backtest.utils.plot_arena_results import plot_results
        img_path = plot_results(result_file)
        if img_path:
            print(f"[Arena] 鍙鍖栨洸绾垮凡鐢熸垚: {img_path}")
    except Exception as e:
        print(f"[Arena] 鍙鍖栧け璐? {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CTS Arena Backtest")
    parser.add_argument("--strategy", type=str, default="grid_rsi_5_2", help="绛栫暐鍚嶇О")
    parser.add_argument("--params", type=str, default="{}", help="JSON 鏍煎紡鍙傛暟")
    parser.add_argument("--data", type=str, default="data/btc_1m_2025.csv", help="鏁版嵁璺緞")
    
    args = parser.parse_args()
    
    try:
        params_dict = json.loads(args.params.replace("'", '"'))
    except:
        params_dict = {}
        
    run_arena(args.strategy, params_dict, args.data)
