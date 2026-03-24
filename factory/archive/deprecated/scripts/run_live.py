"""
瀹炵洏浜ゆ槗鍏ュ彛鑴氭湰

浣跨敤绀轰緥:
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
    parser = argparse.ArgumentParser(description='Grid RSI 绛栫暐瀹炵洏浜ゆ槗')
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
                        help='浜ゆ槗瀵?)
    parser.add_argument('--timeframe', type=str, default='1m',
                        help='K绾垮懆鏈?)
    parser.add_argument('--demo', action='store_true',
                        help='浣跨敤妯℃嫙鐩?)
    parser.add_argument('--capital', type=float, default=None,
                        help='鍒濆璧勯噾锛堢敤浜庤绠桺NL鍩哄噯锛?)
    
    args = parser.parse_args()
    
    if not all([args.api_key, args.secret, args.passphrase]):
        print("閿欒: 闇€瑕佹彁渚?API Key, Secret 鍜?Passphrase")
        print("鍙互閫氳繃鐜鍙橀噺 OKX_API_KEY, OKX_SECRET, OKX_PASSPHRASE 璁剧疆")
        return 1
    
    print(f"\n{'='*60}")
    print(f"Grid RSI 绛栫暐瀹炵洏浜ゆ槗")
    print(f"{'='*60}")
    print(f"妯″紡: {'妯℃嫙鐩? if args.demo else '瀹炵洏'}")
    print(f"浜ゆ槗瀵? {args.symbol}")
    print(f"K绾垮懆鏈? {args.timeframe}")
    print(f"{'='*60}\n")
    
    # 1. 鍒涘缓鏁版嵁娴?
    data_feed = OKXDataFeed(
        symbol=args.symbol,
        timeframe=args.timeframe,
        api_key=args.api_key,
        api_secret=args.secret,
        passphrase=args.passphrase,
        is_demo=args.demo,
        poll_interval=2.0
    )
    
    # 2. 鍒涘缓绛栫暐
    strategy = GridRSIStrategy(
        symbol=args.symbol,
        grid_levels=10,
        use_kelly_sizing=True,
        trailing_stop=True
    )
    
    # 3. 鍒涘缓鎵ц鍣紙OKX 鐪熷疄浜ゆ槗锛?
    executor = OKXExecutor(
        api_key=args.api_key,
        api_secret=args.secret,
        passphrase=args.passphrase,
        is_demo=args.demo
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
        print("\n鐢ㄦ埛涓柇锛屾鍦ㄥ仠姝?..")
        engine.stop()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
