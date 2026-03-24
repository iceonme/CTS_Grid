"""
鍥炴祴鍏ュ彛鑴氭湰

浣跨敤绀轰緥:
    python run_backtest.py --data btc_1m.csv --capital 10000
"""

import argparse
import sys
from datetime import datetime

from cartridges.strategies import GridRSIStrategy
from cartridges.bridge.executors import PaperExecutor
from cartridges.bridge.datafeeds import CSVDataFeed
from console.engines import BacktestEngine


def main():
    parser = argparse.ArgumentParser(description='Grid RSI 绛栫暐鍥炴祴')
    parser.add_argument('--data', type=str, default='btc_1m.csv',
                        help='鍘嗗彶鏁版嵁鏂囦欢璺緞')
    parser.add_argument('--symbol', type=str, default='BTC-USDT',
                        help='浜ゆ槗瀵?)
    parser.add_argument('--capital', type=float, default=10000.0,
                        help='鍒濆璧勯噾')
    parser.add_argument('--grid-levels', type=int, default=10,
                        help='缃戞牸灞傛暟')
    parser.add_argument('--rsi-period', type=int, default=14,
                        help='RSI鍛ㄦ湡')
    parser.add_argument('--output', type=str, default=None,
                        help='缁撴灉淇濆瓨璺緞')
    
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"Grid RSI 绛栫暐鍥炴祴")
    print(f"{'='*60}")
    print(f"鏁版嵁鏂囦欢: {args.data}")
    print(f"浜ゆ槗瀵? {args.symbol}")
    print(f"鍒濆璧勯噾: ${args.capital:,.2f}")
    print(f"{'='*60}\n")
    
    # 1. 鍒涘缓鏁版嵁娴?
    data_feed = CSVDataFeed(
        filepath=args.data,
        symbol=args.symbol
    )
    
    # 2. 鍒涘缓绛栫暐
    strategy = GridRSIStrategy(
        symbol=args.symbol,
        grid_levels=args.grid_levels,
        rsi_period=args.rsi_period,
        use_kelly_sizing=True,
        trailing_stop=True
    )
    
    # 3. 鍒涘缓鎵ц鍣?
    executor = PaperExecutor(
        initial_capital=args.capital,
        fee_rate=0.001,
        slippage_model='adaptive'
    )
    
    # 4. 鍒涘缓寮曟搸骞惰繍琛?
    engine = BacktestEngine(
        strategy=strategy,
        executor=executor,
        initial_capital=args.capital
    )
    
    def progress_callback(current, total):
        if current % 1000 == 0:
            print(f"杩涘害: 宸插鐞?{current} 鏉℃暟鎹?)
    
    results = engine.run(data_feed, progress_callback)
    
    # 5. 鎵撳嵃鎶ュ憡
    engine.print_report(results)
    
    # 6. 淇濆瓨缁撴灉锛堝彲閫夛級
    if args.output:
        import json
        # 绠€鍖栫粨鏋滅敤浜庝繚瀛?
        save_results = {
            'total_return': results['total_return'],
            'max_drawdown': results['max_drawdown'],
            'sharpe_ratio': results['sharpe_ratio'],
            'total_trades': results['total_trades'],
            'win_rate': results['win_rate'],
            'profit_factor': results['profit_factor'],
        }
        with open(args.output, 'w') as f:
            json.dump(save_results, f, indent=2)
        print(f"\n缁撴灉宸蹭繚瀛樺埌: {args.output}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
