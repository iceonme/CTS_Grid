import sys
import os
import json
from datetime import datetime

# 允许独立运行：临时添加到 sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(SKILL_DIR)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
# 将 SKILL_DIR/scripts 加入 sys.path 以便直接 import strategy
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from strategy import Zen71Strategy
from core import MarketData, StrategyContext

def run_verification():
    print(f"验证: 策略组件独立加载与运算测试")
    
    # 1. 加载参数
    config_path = os.path.join(SKILL_DIR, "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    print(f"[OK] 从 config.json 加载参数成功: {config['params']['capital']} 资金")
    
    # 2. 实例化策略
    strategy = Zen71Strategy(name="zen-7-1", **config["params"])
    strategy.initialize()
    print("[OK] 策略实例化与初始化成功")
    
    # 3. 模拟上下文和数据流
    context = StrategyContext(
        timestamp=datetime.now(),
        cash=config["initial_balance"],
        positions={},
        current_prices={"BTC-USDT-SWAP": 90000}
    )
    
    # 喂入 65 根 K 线，使其度过 60 分钟重采样周期
    print("模拟推送 65 根 1m K 线 (90000 -> 91000)...")
    base_price = 90000
    signals_generated = []
    
    for i in range(1, 66):
        price = base_price + i * 15 # 每个 bar 涨一点
        data = MarketData(
            timestamp=datetime.now(),
            symbol="BTC-USDT-SWAP",
            open=price - 10,
            high=price + 20,
            low=price - 20,
            close=price,
            volume=5.5
        )
        
        # 捕获任何潜在的信号
        sigs = strategy.on_data(data, context)
        if sigs:
            signals_generated.extend(sigs)
            
    # 4. 验证策略状态
    status = strategy.get_status(context)
    print("\n[OK] 回溯验证结束")
    print("--- 当前策略状态 ---")
    print(f"内部计算 RSI: {status.get('rsi', 'N/A')}")
    print(f"计算的参数值: layers={status.get('layers', 0)}")
    print(f"产生的信号数量: {len(signals_generated)}")
    print("--------------------")
    print("此脚本仅验证 API 与逻辑跑通，不代表产生实际交易信号。")

if __name__ == "__main__":
    run_verification()
