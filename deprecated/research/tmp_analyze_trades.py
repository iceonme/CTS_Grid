
import json
import os
from datetime import datetime

trades_file = r'c:\CS\zen\trading_trades_grid_v60_v60.json'

def analyze():
    if not os.path.exists(trades_file):
        print("File not found")
        return

    content = ""
    for enc in ['utf-8', 'gbk', 'utf-16']:
        try:
            with open(trades_file, 'r', encoding=enc) as f:
                content = f.read()
            break
        except Exception:
            continue
    
    if not content:
        print("Could not read file")
        return

    # 尝试多种方式修复 JSON
    data = []
    try:
        data = json.loads(content)
    except Exception:
        # 针对追加写入导致的非标准 JSON 情况进行流式解析匹配
        import re
        matches = re.findall(r'\{[^{}]*\}', content)
        for m in matches:
            try:
                data.append(json.loads(m))
            except:
                continue

    # 过滤 3月11日 23:00 至今的交易
    start_time = "2026-03-11T23:00"
    recent_trades = [t for t in data if str(t.get('time', '')) >= start_time]
    
    print(f"--- Analysis from {start_time} to Now ---")
    print(f"Total trades found: {len(recent_trades)}")
    
    reasons = {}
    for t in recent_trades:
        r = t.get('reason', 'Unknown')
        reasons[r] = reasons.get(r, 0) + 1
        
        time_val = t.get('time')
        side = t.get('side')
        price = t.get('price')
        print(f"Time: {time_val}, Side: {side}, Price: {price}, Reason: {r}")

    print("\n--- Reason Statistics ---")
    for r, count in reasons.items():
        print(f"{r}: {count}")

if __name__ == "__main__":
    analyze()
