
import os
import sys
from datetime import datetime, timezone

# Setup path to match run_eth_swap_v93.py
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# Note: we need to go up one level then enter Okx_4_0 (the root)
ROOT_DIR = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "ethswap"))

from ethswap.strategies.eth_swap_v93 import V93Strategy
from ethswap.executors.okx_swap import OKXSwapExecutor
from ethswap.datafeeds.okx_feed import OKXDataFeed
from ethswap.engines.live import LiveEngine
from ethswap.config.api_config import OKX_CONFIG, DEFAULT_SYMBOL

def test_warmup():
    print("Testing Engine Warmup Summary...")
    
    strategy = V93Strategy(symbol=DEFAULT_SYMBOL)
    executor = OKXSwapExecutor(
        api_key=OKX_CONFIG['api_key'],
        api_secret=OKX_CONFIG['api_secret'],
        passphrase=OKX_CONFIG['passphrase'],
        is_demo=True
    )
    data_feed = OKXDataFeed(
        symbol=DEFAULT_SYMBOL,
        api_key=OKX_CONFIG['api_key'],
        api_secret=OKX_CONFIG['api_secret'],
        passphrase=OKX_CONFIG['passphrase'],
        is_demo=True
    )
    
    engine = LiveEngine(
        strategy=strategy,
        executor=executor,
        data_feed=data_feed,
        warmup_bars=10 # Short warmup for speed
    )
    
    engine.warmup()
    print("Warmup finished.")

if __name__ == "__main__":
    test_warmup()
