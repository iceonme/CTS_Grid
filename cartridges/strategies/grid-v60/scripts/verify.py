import sys
import os
import json
from datetime import datetime

# 环境自探测：确保能找到项目根目录和 strategy 模块
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(SKILL_DIR)))

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from strategy import GridMTFStrategyV6_0
from console.core import MarketData, StrategyContext

def verify_skill():
    print(">>> grid-v60 Skill 完整性验证开始 <<<")
    
    # 1. 检查配置
    config_path = os.path.join(SKILL_DIR, "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    print(f"[OK] config.json 加载成功，目标标的: {config['symbol']}")
    
    # 2. 实例化测试
    try:
        strategy = GridMTFStrategyV6_0(name="test-v60", **config["params"])
        strategy.initialize()
        print("[OK] 策略类实例化与初始化成功")
    except Exception as e:
        print(f"[FAIL] 策略实例化失败: {e}")
        return

    # 3. 基础指标运算测试
    print("模拟推送测试数据...")
    context = StrategyContext(
        timestamp=datetime.now(),
        cash=config["initial_balance"],
        positions={},
        current_prices={config["symbol"]: 90000}
    )
    
    # 推送一段简单的价格波动
    for i in range(20):
        data = MarketData(
            timestamp=datetime.now(),
            symbol=config["symbol"],
            open=90000 + i, high=90100 + i, low=89900 + i, close=90050 + i,
            volume=10
        )
        strategy.on_data(data, context)
        
    status = strategy.get_status(context)
    print("\n[OK] 验证流程完成")
    print(f"--- 状态摘要 ---")
    print(f"策略名称: {status['name']}")
    print(f"实时 RSI: {status['current_rsi']}")
    print(f"MACD 趋势: {status['macd_trend']}")
    print(f"网格状态: {status['signal_text']}")
    print("----------------")

if __name__ == "__main__":
    verify_skill()
