"""
妯℃嫙鐩樺叆鍙ｈ剼鏈?

浣跨敤绀轰緥:
    python run_paper.py --data btc_1m.csv --speed 10
"""

import argparse
import sys
import time
from datetime import datetime

from cartridges.strategies import GridRSIStrategy
from cartridges.bridge.executors import PaperExecutor
from cartridges.bridge.datafeeds import CSVDataFeed
from console.engines import LiveEngine


def main():
    parser = argparse.ArgumentParser(description='Grid RSI 绛栫暐妯℃嫙鐩?)
    parser.add_argument('--data', type=str, default='btc_1m.csv',
                        help='鍘嗗彶鏁版嵁鏂囦欢璺緞')
    parser.add_argument('--symbol', type=str, default='BTC-USDT',
                        help='浜ゆ槗瀵?)
    parser.add_argument('--capital', type=float, default=10000.0,
                        help='鍒濆璧勯噾')
    parser.add_argument('--speed', type=float, default=1.0,
                        help='鍥炴斁閫熷害鍊嶇巼 (1.0=姝ｅ父閫熷害)')
    
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"Grid RSI 绛栫暐妯℃嫙鐩?)
    print(f"{'='*60}")
    print(f"鏁版嵁鏂囦欢: {args.data}")
    print(f"浜ゆ槗瀵? {args.symbol}")
    print(f"鍒濆璧勯噾: ${args.capital:,.2f}")
    print(f"鍥炴斁閫熷害: {args.speed}x")
    print(f"{'='*60}\n")
    
    # 1. 鍒涘缓鏁版嵁娴?
    data_feed = CSVDataFeed(
        filepath=args.data,
        symbol=args.symbol
    )
    
    # 2. 鍒涘缓绛栫暐
    strategy = GridRSIStrategy(
        symbol=args.symbol,
        grid_levels=10,
        use_kelly_sizing=True,
        trailing_stop=True
    )
    
    # 3. 鍒涘缓鎵ц鍣紙妯℃嫙鎵ц锛?
    executor = PaperExecutor(
        initial_capital=args.capital,
        fee_rate=0.001,
        slippage_model='adaptive',
        latency_ms=200
    )
    
    # 4. 鍒涘缓寮曟搸
    engine = LiveEngine(
        strategy=strategy,
        executor=executor,
        data_feed=data_feed,
        warmup_bars=100
    )
    
    # 5. 鍚姩
    try:
        engine.run()
    except KeyboardInterrupt:
        print("\n鐢ㄦ埛涓柇")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
