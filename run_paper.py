"""
模拟盘入口脚本

使用示例:
    python run_paper.py --data btc_1m.csv --speed 10
"""

import argparse
import sys
import time
from datetime import datetime

from strategies import GridRSIStrategy
from executors import PaperExecutor
from datafeeds import CSVDataFeed
from engines import LiveEngine


def main():
    parser = argparse.ArgumentParser(description='Grid RSI 策略模拟盘')
    parser.add_argument('--data', type=str, default='btc_1m.csv',
                        help='历史数据文件路径')
    parser.add_argument('--symbol', type=str, default='BTC-USDT',
                        help='交易对')
    parser.add_argument('--capital', type=float, default=10000.0,
                        help='初始资金')
    parser.add_argument('--speed', type=float, default=1.0,
                        help='回放速度倍率 (1.0=正常速度)')
    
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"Grid RSI 策略模拟盘")
    print(f"{'='*60}")
    print(f"数据文件: {args.data}")
    print(f"交易对: {args.symbol}")
    print(f"初始资金: ${args.capital:,.2f}")
    print(f"回放速度: {args.speed}x")
    print(f"{'='*60}\n")
    
    # 1. 创建数据流
    data_feed = CSVDataFeed(
        filepath=args.data,
        symbol=args.symbol
    )
    
    # 2. 创建策略
    strategy = GridRSIStrategy(
        symbol=args.symbol,
        grid_levels=10,
        use_kelly_sizing=True,
        trailing_stop=True
    )
    
    # 3. 创建执行器（模拟执行）
    executor = PaperExecutor(
        initial_capital=args.capital,
        fee_rate=0.001,
        slippage_model='adaptive',
        latency_ms=200
    )
    
    # 4. 创建引擎
    engine = LiveEngine(
        strategy=strategy,
        executor=executor,
        data_feed=data_feed,
        warmup_bars=100
    )
    
    # 5. 启动
    try:
        engine.run()
    except KeyboardInterrupt:
        print("\n用户中断")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
