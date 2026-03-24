import sys
import os
import time
from datetime import datetime

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from cartridges.bridge.datafeeds import OKXDataFeed
from cartridges.bridge.utils.okx_api import OKX_DEMO_CONFIG, DEFAULT_SYMBOL
from cartridges.strategies.grid_mtf_6_0 import GridMTFStrategyV6_0
from cartridges.bridge.executors.paper import PaperExecutor
from console.runner import MultiStrategyRunner, StrategySlot

def main():
    print("=== V6.0 Revival Slots Backtest ===")
    
    feed = OKXDataFeed(
        symbol=DEFAULT_SYMBOL,
        timeframe='1m',
        api_key=OKX_DEMO_CONFIG['api_key'],
        api_secret=OKX_DEMO_CONFIG['api_secret'],
        passphrase=OKX_DEMO_CONFIG['passphrase'],
        is_demo=True,
        record_to=f"factory/data/market/{DEFAULT_SYMBOL.replace('-', '_')}_1m.csv"
    )
    
    strategy = GridMTFStrategyV6_0(
        name="Grid_V60_Revival",
        symbol=DEFAULT_SYMBOL,
        initial_capital=10000.0,
        verbose=True
    )
    
    executor = PaperExecutor(initial_capital=10000.0)
    runner = MultiStrategyRunner() # Default without dashboard for pure testing
    
    slot = StrategySlot(
        slot_id="test_v60",
        display_name="Grid V6.0 Slots Headless",
        strategy=strategy,
        executor=executor,
        initial_balance=10000.0,
        state_file=f"trading_state_test_v60.json",
        trades_file=f"trading_trades_test_v60.json"
    )
    runner.add_slot(slot)
    
    print("[V6.0] 预热数据中...")
    from console.engines import LiveEngine
    warmup_engine = LiveEngine(strategy, executor, feed, warmup_bars=300)
    
    if warmup_engine.warmup():
        print(f"[V6.0] 预热完成")
        
    print("\n[V6.0] 开始执行...")
    
    try:
        # Just run a few loops to verify execution doesn't throw errors
        count = 0
        for market_data in feed.stream():
            if market_data:
                runner.on_bar(market_data)
                count += 1
                if count > 1000: # limit iterations for quick test
                    break
    except KeyboardInterrupt:
        pass
        
    print("\n--- Strategy State (Slots) ---")
    for idx, s in enumerate(strategy.state.slots):
        print(f"Slot {idx}: Size {s['size']:.5f} BTC @ {s['buy_price']:.1f} (Layer {s['layer_idx']}, Virtual={s['is_virtual']})")

if __name__ == "__main__":
    main()
