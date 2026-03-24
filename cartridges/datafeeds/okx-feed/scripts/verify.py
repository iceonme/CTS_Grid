import sys
import os
import json
from datetime import datetime

# 环境探测
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_DIR = os.getcwd()

if PROJECT_DIR not in sys.path: sys.path.insert(0, PROJECT_DIR)

from scripts.feed import OKXDataFeedSkill

def verify_feed():
    print(">>> okx-feed Skill 验证开始 <<<")
    
    config_path = os.path.join(SKILL_DIR, "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    print(f"[OK] config.json 加载成功")
    
    # 实例化测试 (不填 API Key，仅测试静态逻辑)
    try:
        feed = OKXDataFeedSkill(**config["params"])
        print(f"[OK] DataFeed 实例化成功")
        print(f"参数校验: Symbol={feed.symbol}, Interval={feed.poll_interval}")
    except Exception as e:
        print(f"[FAIL] 实例化失败: {e}")

    print(">>> 验证流程完成 <<<")

if __name__ == "__main__":
    verify_feed()
