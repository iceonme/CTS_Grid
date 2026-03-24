import sys
import os
import json
from datetime import datetime

# 环境探测
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_DIR = os.getcwd()

if PROJECT_DIR not in sys.path: sys.path.insert(0, PROJECT_DIR)

from scripts.executor import PaperExecutorSkill
from console.core import Order, Side, OrderType

def verify_executor():
    print(">>> paper-executor Skill 验证开始 <<<")
    
    config_path = os.path.join(SKILL_DIR, "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    try:
        executor = PaperExecutorSkill(**config["params"])
        print(f"[OK] Executor 实例化成功")
        
        # 简单撮合测试
        executor.update_market_data(datetime.now(), 90000.0)
        order = Order(symbol="BTC-USDT-SWAP", side=Side.BUY, price=None, size=1000, type=OrderType.MARKET, meta={"size_in_quote": True})
        oid = executor.submit_order(order)
        
        if executor.get_cash() < config["params"]["initial_capital"]:
            print(f"[OK] 订单成交，剩余现金: {executor.get_cash():.2f}")
    except Exception as e:
        print(f"[FAIL] 验证失败: {e}")

    print(">>> 验证流程完成 <<<")

if __name__ == "__main__":
    verify_executor()
