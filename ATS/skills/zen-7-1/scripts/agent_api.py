"""
专为 NLP 大模型或者文字型 Agent 提供的自然语言询问接口。
"""
import os
import json
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
ATS_DIR = os.path.dirname(os.path.dirname(SKILL_DIR))

if ATS_DIR not in sys.path: sys.path.insert(0, ATS_DIR)
if SCRIPT_DIR not in sys.path: sys.path.insert(0, SCRIPT_DIR)

from strategy import Zen71Strategy

def get_trading_advice(price_history_json: str, user_context_json: str) -> str:
    """
    Agent 接口方法。
    输入：近期的历史收盘价数据序列 (JSON String), 当前盈亏仓位(JSON String)
    输出：推荐行动字符串
    """
    try:
        prices = json.loads(price_history_json)
        context = json.loads(user_context_json)
    except Exception as e:
        return f"解析失败，请传入正确的 JSON 数据: {e}"

    if len(prices) < 20:
        return "数据量过少，请提供至少 20 根以上的连续 K 线收盘价。"

    config_path = os.path.join(SKILL_DIR, "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 实例化一个用后即焚的脑子
    strategy = Zen71Strategy(name="zen-7-1", **config["params"])
    strategy.initialize()

    # 快速喂饱它，计算出当前指标状态
    for i, p in enumerate(prices):
        # 伪造一个极简的 MarketDataDict
        data = {
            "symbol": "USER-SYMBOL",
            "timestamp": 0,
            "open": p, "high": p, "low": p, "close": p, "volume": 0
        }
        
        # 只在最后一步看有没有出信号，或人为强制让它处于第 60 分钟切片上以触发判定
        if i == len(prices) - 1:
            strategy.bar_counter = strategy.resample_min - 1 # Trick: 强制下一步进入结算层
            
        sigs = strategy.on_data(data, context)

    # 获取最后状态与信号
    status = strategy.get_status()
    rsi_val = status.get("rsi", 50)

    if not sigs:
        advice = f"分析结果：【HOLD / 观望】。\n指标简报：当前 RSI 为 {rsi_val:.1f}，暂未发现明显的动能扩张或网格摊薄买点。"
    else:
        s = sigs[-1] # 取最新一条
        advice = f"分析结果：【强烈建议 {s['side']}】。\n具体动作：{s['type']} 订单，大小 {s['size']}。\n原因判定：{s['rationale']}\n内部指标 RSI 为 {rsi_val:.1f}。"

    return advice

if __name__ == "__main__":
    # 用例：如果有人写命令 `python agent_api.py '[60000, 61000, ...]'`
    import argparse
    parser = argparse.ArgumentParser(description="ATS Agent API Interface")
    parser.add_argument("--prices", type=str, default="[90000, 90500, 91000, 89000, 85000]", help="JSON array of historical close prices")
    parser.add_argument("--ctx", type=str, default='{"layers": 0, "pnl_pct": 0}', help="JSON dict of current position context")
    args = parser.parse_args()
    
    print("\n--- Agent 建议请求回应 ---")
    res = get_trading_advice(args.prices, args.ctx)
    print(res)
    print("--------------------------\n")
