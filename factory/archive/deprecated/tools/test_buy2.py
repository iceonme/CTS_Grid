"""
娴嬭瘯 OKX 涔板叆鍔熻兘 - 涓嶅悓鏂瑰紡
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

# 鑾峰彇浠锋牸
ticker = api.get_ticker('BTC-USDT')
price = float(ticker['last'])
print(f"褰撳墠浠锋牸: {price:.2f}")

# 娴嬭瘯 1: 甯備环鍗?0.1 BTC (绾?6500 USDT)
print("\n1. 娴嬭瘯甯備环鍗?0.1 BTC...")
result1 = api.place_order('BTC-USDT', 'buy', 'market', '0.1', force_server=True)
print(f"   缁撴灉: {result1}")

# 濡傛灉澶辫触锛岀瓑寰呭悗娴嬭瘯闄愪环鍗?
if result1.get('code') != '0':
    time.sleep(1)
    
    # 娴嬭瘯 2: 闄愪环鍗?0.01 BTC @ 褰撳墠浠锋牸
    print("\n2. 娴嬭瘯闄愪环鍗?0.01 BTC...")
    result2 = api.place_order('BTC-USDT', 'buy', 'limit', '0.01', px=str(price), force_server=True)
    print(f"   缁撴灉: {result2}")
    
    time.sleep(1)
    
    # 娴嬭瘯 3: 甯備环鍗?5000 USDT (浣跨敤 sz 涓?USDT 閲戦?)
    print("\n3. 娴嬭瘯甯備环鍗?sz=5000...")
    # 灏濊瘯鐩存帴涓嬪崟锛岀湅鐪嬮敊璇俊鎭?
    import json
    body = {
        'instId': 'BTC-USDT',
        'tdMode': 'cash',
        'side': 'buy',
        'ordType': 'market',
        'sz': '5000'  # 鍙兘鏄?USDT 閲戦锛?
    }
    result3 = api._request('POST', '/api/v5/trade/order', body=body)
    print(f"   缁撴灉: {result3}")
