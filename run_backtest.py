"""
回测入口脚本

使用示例:
    python run_backtest.py --data btc_1m.csv --capital 10000
"""

import argparse
import sys
from datetime import datetime

from strategies import GridRSIStrategy
from executors import PaperExecutor
from datafeeds import CSVDataFeed
from engines import BacktestEngine


def main():
    parser = argparse.ArgumentParser(description='Grid RSI 策略回测')
    parser.add_argument('--data', type=str, default='btc_1m.csv',
                        help='历史数据文件路径')
    parser.add_argument('--symbol', type=str, default='BTC-USDT',
                        help='交易对')
    parser.add_argument('--capital', type=float, default=10000.0,
                        help='初始资金')
    parser.add_argument('--grid-levels', type=int, default=10,
                        help='网格层数')
    parser.add_argument('--rsi-period', type=int, default=14,
                        help='RSI周期')
    parser.add_argument('--output', type=str, default=None,
                        help='结果保存路径')
    
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"Grid RSI 策略回测")
    print(f"{'='*60}")
    print(f"数据文件: {args.data}")
    print(f"交易对: {args.symbol}")
    print(f"初始资金: ${args.capital:,.2f}")
    print(f"{'='*60}\n")
    
    # 1. 创建数据流
    data_feed = CSVDataFeed(
        filepath=args.data,
        symbol=args.symbol
    )
    
    # 2. 创建策略
    strategy = GridRSIStrategy(
        symbol=args.symbol,
        grid_levels=args.grid_levels,
        rsi_period=args.rsi_period,
        use_kelly_sizing=True,
        trailing_stop=True
    )
    
    # 3. 创建执行器
    executor = PaperExecutor(
        initial_capital=args.capital,
        fee_rate=0.001,
        slippage_model='adaptive'
    )
    
    # 4. 创建引擎并运行
    engine = BacktestEngine(
        strategy=strategy,
        executor=executor,
        initial_capital=args.capital
    )
    
    def progress_callback(current, total):
        if current % 1000 == 0:
            print(f"进度: 已处理 {current} 条数据")
    
    results = engine.run(data_feed, progress_callback)
    
    # 5. 打印报告
    engine.print_report(results)
    
    # 6. 保存结果（可选）
    if args.output:
        import json
        # 简化结果用于保存
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
        print(f"\n结果已保存到: {args.output}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
