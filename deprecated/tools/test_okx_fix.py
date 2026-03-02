
import sys
import os
sys.path.append(os.getcwd())
from okx_config import OKXAPI
import json

def test_auth():
    api_config = {
        'api_key': '72aac042-9859-48ec-8e27-9722524429a6',
        'api_secret': 'CCFE2963EBD154027557D24CFA2CAA57',
        'passphrase': 'Tonghua9527_',
        'is_demo': True
    }
    
    api = OKXAPI(**api_config)
    
    print("--- 验证 GET 请求 (余额) ---")
    balance = api.get_balance()
    if balance:
        print(f"成功获取余额: {balance['availBal']} USDT")
    else:
        print("获取余额失败")
        
    print("\n--- 验证 GET 请求 (持仓) ---")
    positions = api.get_positions('BTC-USDT')
    if positions is not None:
        print(f"成功获取持仓，当前持仓数量: {len(positions)}")
    else:
        print("获取持仓失败")

    print("\n--- 验证 POST 请求 (模拟下单测试) ---")
    # 这里我们使用一个小额的买单来测试，OKX 模拟盘应该允许
    # 注意：这里调用的是 place_order，内部如果 force_server=True 会真实发给服务器
    order_result = api.place_order(inst_id='BTC-USDT', side='buy', sz='0.01', force_server=True)
    if order_result and order_result.get('code') == '0':
        print(f"下单测试成功! OrdId: {order_result['data'][0].get('ordId')}")
    else:
        print(f"下单测试失败: {order_result}")

if __name__ == "__main__":
    test_auth()
