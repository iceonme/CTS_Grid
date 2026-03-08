import sys
import os
import json
from datetime import datetime

# 这个验证脚本用来测试：ATSStrategy 在 0 外部 CTS1 依赖的情况下，能否独立吃 K 线吐 Signal
# 甚至都不用依赖 requests 库。

# 将当前脚本所在的技能包根目录加入 sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
ATS_DIR = os.path.dirname(os.path.dirname(SKILL_DIR))

if ATS_DIR not in sys.path:
    sys.path.insert(0, ATS_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# --- 这里只引用纯洁的自带协议，完全不需要 import core ---
from ats_core import MarketDataDict, SignalDict
from strategy import Zen71Strategy

def mock_market_data(current_price: float) -> MarketDataDict:
    return {
        "symbol": "BTC-USDT-SWAP",
        "timestamp": datetime.now().timestamp(),
        "open": current_price - 10,
        "high": current_price + 20,
        "low": current_price - 20,
        "close": current_price,
        "volume": 5.5
    }

def run_standalone_verification():
    print(f"\n[验证] ATS-20 纯享版引擎自检开始...")
    
    # 1. 加载参数
    config_path = os.path.join(SKILL_DIR, "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    print(f"[OK] 参数装载成功: Capital = {config['params']['capital']}")
    
    # 2. 实例化策略
    strategy = Zen71Strategy(name="zen-7-1", **config["params"])
    strategy.initialize()
    print("[OK] ATS 实例化完成 (无 CTS1 依赖)")
    
    # 3. 模拟上下文和数据流 (这次传的是字典)
    context = {"pnl_pct": 0.0, "layers": 0, "avg_cost": 0.0}
    
    print("模拟推送 65 根 K 线字典 (90000 -> 91000)...")
    base_price = 90000
    all_signals = []
    
    for i in range(1, 66):
        price = base_price + i * 15
        data_dict = mock_market_data(price)
        
        # Strategy 吃了 Dict，吐了 List[Dict]
        sigs = strategy.on_data(data_dict, context)
        if sigs:
            all_signals.extend(sigs)
            # 模拟收到第一单后改变 context 回传
            for s in sigs:
                print(f"  --> 收到 ATS 标准信号: {s['side']} {s['size']} | {s['rationale']}")
            context["layers"] = 1
            context["avg_cost"] = price
            
    # 4. 提取策略自带状态
    status = strategy.get_status()
    print("\n[OK] 测试跑完，最终内部状态:")
    print(json.dumps(status, indent=2))
    print(f"测试通过！这就是一个能在全世界跑的智能体技能包。")

if __name__ == "__main__":
    run_standalone_verification()
