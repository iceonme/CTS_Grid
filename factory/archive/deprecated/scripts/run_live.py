"""
实盘交易入口脚本

使用示例:
    python run_live.py --api-key xxx --secret xxx --passphrase xxx --demo
"""

import argparse
import sys
import os
from datetime import datetime

from cartridges.strategies import GridRSIStrategy
from cartridges.bridge.executors import OKXExecutor
from cartridges.bridge.datafeeds import OKXDataFeed
from console.engines import LiveEngine


def main():
    parser = argparse.ArgumentParser(description='Grid RSI 策略实盘交易')
    parser.add_argument('--api-key', type=str, 
                        default=os.getenv('OKX_API_KEY'),
                        help='OKX API Key')
    parser.add_argument('--secret', type=str,
                        default=os.getenv('OKX_SECRET'),
                        help='OKX API Secret')
    parser.add_argument('--passphrase', type=str,
                        default=os.getenv('OKX_PASSPHRASE'),
                        help='OKX Passphrase')
    parser.add_argument('--symbol', type=str, default='BTC-USDT',
                        help='交易瀵?)
    parser.add_argument('--timeframe', type=str, default='1m',
                        help='K线周鏈?)
    parser.add_argument('--demo', action='store_true',
                        help='使用模拟鐩?)
    parser.add_argument('--capital', type=float, default=None,
                        help='初始资金（用于计算PNL基准锛?)
    
    args = parser.parse_args()
    
    if not all([args.api_key, args.secret, args.passphrase]):
        print("错误: 闇€要提渚?API Key, Secret 鍜?Passphrase")
        print("可以通过环境变量 OKX_API_KEY, OKX_SECRET, OKX_PASSPHRASE 设置")
        return 1
    
    print(f"\n{'='*60}")
    print(f"Grid RSI 策略实盘交易")
    print(f"{'='*60}")
    print(f"模式: {'模拟鐩? if args.demo else '实盘'}")
    print(f"交易瀵? {args.symbol}")
    print(f"K线周鏈? {args.timeframe}")
    print(f"{'='*60}\n")
    
    # 1. 创建数据娴?
    data_feed = OKXDataFeed(
        symbol=args.symbol,
        timeframe=args.timeframe,
        api_key=args.api_key,
        api_secret=args.secret,
        passphrase=args.passphrase,
        is_demo=args.demo,
        poll_interval=2.0
    )
    
    # 2. 创建策略
    strategy = GridRSIStrategy(
        symbol=args.symbol,
        grid_levels=10,
        use_kelly_sizing=True,
        trailing_stop=True
    )
    
    # 3. 创建执行器（OKX 真实交易锛?
    executor = OKXExecutor(
        api_key=args.api_key,
        api_secret=args.secret,
        passphrase=args.passphrase,
        is_demo=args.demo
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
        print("\n用户中断，正在停姝?..")
        engine.stop()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
