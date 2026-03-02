"""
测试 OKX 买入功能 - 不同方式
"""
import time
from okx_config import OKXAPI

api_config = {
    'api_key': '72aac042-9859-48ec-8e27-9722524429a6',
    'api_secret': 'CCFE2963EBD154027557D24CFA2CAA57',
    'passphrase': 'Tonghua9527_',
    'is_demo': True
}

api = OKXAPI(**api_config)

# 获取价格
ticker = api.get_ticker('BTC-USDT')
price = float(ticker['last'])
print(f"当前价格: {price:.2f}")

# 测试 1: 市价单 0.1 BTC (约 6500 USDT)
print("\n1. 测试市价单 0.1 BTC...")
result1 = api.place_order('BTC-USDT', 'buy', 'market', '0.1', force_server=True)
print(f"   结果: {result1}")

# 如果失败，等待后测试限价单
if result1.get('code') != '0':
    time.sleep(1)
    
    # 测试 2: 限价单 0.01 BTC @ 当前价格
    print("\n2. 测试限价单 0.01 BTC...")
    result2 = api.place_order('BTC-USDT', 'buy', 'limit', '0.01', px=str(price), force_server=True)
    print(f"   结果: {result2}")
    
    time.sleep(1)
    
    # 测试 3: 市价单 5000 USDT (使用 sz 为 USDT 金额?)
    print("\n3. 测试市价单 sz=5000...")
    # 尝试直接下单，看看错误信息
    import json
    body = {
        'instId': 'BTC-USDT',
        'tdMode': 'cash',
        'side': 'buy',
        'ordType': 'market',
        'sz': '5000'  # 可能是 USDT 金额？
    }
    result3 = api._request('POST', '/api/v5/trade/order', body=body)
    print(f"   结果: {result3}")
