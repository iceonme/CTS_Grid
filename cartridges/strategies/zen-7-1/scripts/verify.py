import sys
import os
import json
from datetime import datetime

# 鍏佽鐙珛杩愯锛氫复鏃舵坊鍔犲埌 sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(SKILL_DIR)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
# 灏?SKILL_DIR/scripts 鍔犲叆 sys.path 浠ヤ究鐩存帴 import strategy
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from strategy import Zen71Strategy
from console.core import MarketData, StrategyContext

def run_verification():
    print(f"楠岃瘉: 绛栫暐缁勪欢鐙珛鍔犺浇涓庤繍绠楁祴璇?)
    
    # 1. 鍔犺浇鍙傛暟
    config_path = os.path.join(SKILL_DIR, "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    print(f"[OK] 浠?config.json 鍔犺浇鍙傛暟鎴愬姛: {config['params']['capital']} 璧勯噾")
    
    # 2. 瀹炰緥鍖栫瓥鐣?
    strategy = Zen71Strategy(name="zen-7-1", **config["params"])
    strategy.initialize()
    print("[OK] 绛栫暐瀹炰緥鍖栦笌鍒濆鍖栨垚鍔?)
    
    # 3. 妯℃嫙涓婁笅鏂囧拰鏁版嵁娴?
    context = StrategyContext(
        timestamp=datetime.now(),
        cash=config["initial_balance"],
        positions={},
        current_prices={"BTC-USDT-SWAP": 90000}
    )
    
    # 鍠傚叆 65 鏍?K 绾匡紝浣垮叾搴﹁繃 60 鍒嗛挓閲嶉噰鏍峰懆鏈?
    print("妯℃嫙鎺ㄩ€?65 鏍?1m K 绾?(90000 -> 91000)...")
    base_price = 90000
    signals_generated = []
    
    for i in range(1, 66):
        price = base_price + i * 15 # 姣忎釜 bar 娑ㄤ竴鐐?
        data = MarketData(
            timestamp=datetime.now(),
            symbol="BTC-USDT-SWAP",
            open=price - 10,
            high=price + 20,
            low=price - 20,
            close=price,
            volume=5.5
        )
        
        # 鎹曡幏浠讳綍娼滃湪鐨勪俊鍙?
        sigs = strategy.on_data(data, context)
        if sigs:
            signals_generated.extend(sigs)
            
    # 4. 楠岃瘉绛栫暐鐘舵€?
    status = strategy.get_status(context)
    print("\n[OK] 鍥炴函楠岃瘉缁撴潫")
    print("--- 褰撳墠绛栫暐鐘舵€?---")
    print(f"鍐呴儴璁＄畻 RSI: {status.get('rsi', 'N/A')}")
    print(f"璁＄畻鐨勫弬鏁板€? layers={status.get('layers', 0)}")
    print(f"浜х敓鐨勪俊鍙锋暟閲? {len(signals_generated)}")
    print("--------------------")
    print("姝よ剼鏈粎楠岃瘉 API 涓庨€昏緫璺戦€氾紝涓嶄唬琛ㄤ骇鐢熷疄闄呬氦鏄撲俊鍙枫€?)

if __name__ == "__main__":
    run_verification()
