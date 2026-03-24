import os
import sys
import json
import time
from datetime import datetime

# 加入 ethswap 路径
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ETHSWAP_DIR = os.path.join(CURRENT_DIR, "ethswap")
sys.path.insert(0, ETHSWAP_DIR)

from ethswap.config.api_config import OKX_CONFIG
from ethswap.config.okx_config import OKXAPI

def emergency_close():
    print("="*60)
    print(f"OKX 紧急平仓工具 - {datetime.now()}")
    print("="*60)
    
    api = OKXAPI(
        api_key=OKX_CONFIG['api_key'],
        api_secret=OKX_CONFIG['api_secret'],
        passphrase=OKX_CONFIG['passphrase'],
        is_demo=OKX_CONFIG['is_demo']
    )
    
    symbol = 'ETH-USDT-SWAP'
    
    # 1. 查询当前持仓
    print(f"\n[1] 查询 {symbol} 当前持仓...")
    positions = api.get_positions(inst_id=symbol)
    if not positions:
        print("  没有发现任何持仓。")
    else:
        for pos in positions:
            side = pos.get('posSide')
            sz = pos.get('pos')
            print(f"  发现持仓: 方向={side}, 数量={sz}张")
            
            # 2. 执行平仓
            print(f"  正在平掉 {side} 仓位...")
            res = api.close_position(inst_id=symbol, pos_side=side)
            if res and res.get('code') == '0':
                print(f"  >>> {side} 平仓成功！")
            else:
                print(f"  >>> {side} 平仓失败: {res.get('msg') if res else 'TIMEOUT'}")

    # 3. 清理策略本地状态 (v93_state.json)
    state_file = os.path.join(ETHSWAP_DIR, "v93_state.json")
    if os.path.exists(state_file):
        print(f"\n[2] 清理策略本地状态 {state_file}...")
        # 我们不删文件，只是重置持仓相关的计数（如果有的话）
        # 实际上 V93 策略状态保存在内存中，重启后会重新从 API 获取真实持仓
        # 但有些元数据可以清理
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            # 重置杠杆或观察期，确保新环境是清净的
            state['breakout_start_time'] = None 
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=4)
            print("  本地状态重置完成。")
        except Exception as e:
            print(f"  重置本地状态失败: {e}")

    # 4. 清理交易历史 (v93_trades.json)
    trades_file = os.path.join(ETHSWAP_DIR, "v93_trades.json")
    if os.path.exists(trades_file):
        print(f"[3] 清除测试交易历史 {trades_file}...")
        try:
            with open(trades_file, 'w', encoding='utf-8') as f:
                f.write("[]")
            print("  交易历史已排空。")
        except Exception as e:
            print(f"  清理交易历史失败: {e}")

    print("\n" + "="*60)
    print("紧急操作完成")
    print("="*60)

if __name__ == "__main__":
    emergency_close()
