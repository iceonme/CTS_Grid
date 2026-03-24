import os
import sys
import json
from datetime import datetime

# 加入 ethswap 路径
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ETHSWAP_DIR = os.path.join(CURRENT_DIR, "ethswap")
sys.path.insert(0, ETHSWAP_DIR)

from ethswap.config.api_config import OKX_CONFIG
from ethswap.config.okx_config import OKXAPI

def diagnose():
    print("="*60)
    print(f"OKX 账户最终验证工具 - {datetime.now()}")
    print("="*60)
    
    api = OKXAPI(
        api_key=OKX_CONFIG['api_key'],
        api_secret=OKX_CONFIG['api_secret'],
        passphrase=OKX_CONFIG['passphrase'],
        is_demo=OKX_CONFIG['is_demo']
    )
    
    # 1.获取当前配置
    res = api._request('GET', '/api/v5/account/config')
    if res and res.get('code') == '0':
        data = res['data'][0]
        print(f"账户模式 (acctLv): {data.get('acctLv')}")
        print(f"持仓模式 (posMode): {data.get('posMode')}")
    else:
        print("无法获取配置")

    # 1.5 获取当前持仓
    print("\n检查当前持仓...")
    res_pos = api._request('GET', '/api/v5/account/positions', {'instId': 'ETH-USDT-SWAP'})
    if res_pos and res_pos.get('code') == '0':
        pos_list = res_pos.get('data', [])
        if not pos_list:
            print("目前没有 ETH-USDT-SWAP 持仓")
        for p in pos_list:
            print(f"持仓: {p.get('posSide')} | 数量: {p.get('pos')} | 均价: {p.get('avgPx')}")
    else:
        print("无法获取持仓")

    # 2.获取余额
    res_bal = api._request('GET', '/api/v5/account/balance', {'ccy': 'USDT'})
    if res_bal and res_bal.get('code') == '0':
        print(f"可用余额 (USDT): {res_bal['data'][0]['details'][0].get('availBal')}")
    else:
        print("无法获取余额")

    # 3.测试下单 (平多)
    cl_ord_id = f"v93_{int(datetime.now().timestamp()*1000)}"
    print(f"\n测试下单 (平多 sz=1) | clOrdId: {cl_ord_id}...")
    res_ord = api._request('POST', '/api/v5/trade/order', body={
        'instId': 'ETH-USDT-SWAP',
        'tdMode': 'cross',
        'side': 'sell',
        'ordType': 'market',
        'sz': '1',
        'posSide': 'long',
        'clOrdId': cl_ord_id
    })
    
    if res_ord and res_ord.get('code') == '0':
        print(f">>> 验证成功：可以使用 clOrdId {cl_ord_id} 下单！")
    else:
        code = res_ord.get('code') if res_ord else "TIMEOUT"
        msg = res_ord.get('msg') if res_ord else "???"
        s_msg = ""
        if res_ord and 'data' in res_ord:
            s_msg = res_ord['data'][0].get('sMsg', '')
        print(f">>> 平仓失败: {msg} (Code: {code}) | {s_msg}")

    print("="*60)

if __name__ == "__main__":
    diagnose()
