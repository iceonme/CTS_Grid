"""
娴嬭瘯 OKX 涔板叆鍔熻兘 - 淇绮惧害闂鍚?
"""
import time
from okx_config import OKXAPI

# API 閰嶇疆
api_config = {
    'api_key': '72aac042-9859-48ec-8e27-9722524429a6',
    'api_secret': 'CCFE2963EBD154027557D24CFA2CAA57',
    'passphrase': 'Tonghua9527_',
    'is_demo': True
}

print("=" * 60)
print("OKX 涔板叆娴嬭瘯 - 淇绮惧害闂")
print("=" * 60)

# 鍒濆鍖?API
api = OKXAPI(**api_config)

# 1. 鑾峰彇褰撳墠浠锋牸
print("\n1. 鑾峰彇褰撳墠 BTC 浠锋牸...")
ticker = api.get_ticker('BTC-USDT')
if ticker:
    current_price = float(ticker['last'])
    print(f"   褰撳墠浠锋牸: {current_price:.2f} USDT")
else:
    print("   鉁?鑾峰彇浠锋牸澶辫触")
    exit(1)

# 2. 鑾峰彇璐︽埛浣欓
print("\n2. 鑾峰彇璐︽埛浣欓...")
balance = api.get_balance()
if balance:
    avail_bal = balance['availBal']
    print(f"   鍙敤 USDT: {avail_bal:.2f}")
else:
    print("   鉁?鑾峰彇浣欓澶辫触")
    exit(1)

# 3. 娴嬭瘯淇鍚庣殑涓嬪崟閫昏緫
print("\n3. 娴嬭瘯淇鍚庣殑涓嬪崟閫昏緫...")
print("-" * 60)

# OKX 鍙傛暟
min_order_usdt = 100  # 鏈€灏忚鍗曢噾棰?
tick_sz = 0.01       # 浠锋牸绮惧害 (2浣嶅皬鏁?
lot_sz = 0.00001     # 鏁伴噺绮惧害 (5浣嶅皬鏁?

# 璁＄畻璁㈠崟鍙傛暟 (妯℃嫙淇鍚庣殑閫昏緫)
test_usdt = max(100, min_order_usdt)  # 鑷冲皯 100 USDT
order_btc = test_usdt / current_price
order_btc = round(order_btc, 5)       # 鎴柇鍒?5 浣嶅皬鏁?
order_px = round(current_price, 2)    # 鎴柇鍒?2 浣嶅皬鏁?
actual_cost = order_btc * order_px

print(f"\n   娴嬭瘯鍙傛暟:")
print(f"   - 涓嬪崟閲戦: {test_usdt} USDT")
print(f"   - 褰撳墠浠锋牸: {current_price:.2f} USDT")
print(f"   - 璋冩暣鍚庝环鏍? {order_px:.2f} USDT")
print(f"   - BTC 鏁伴噺: {order_btc:.5f} BTC")
print(f"   - 瀹為檯鎴愭湰: {actual_cost:.2f} USDT")

# 妫€鏌ユ渶灏忔暟閲?
if order_btc < lot_sz:
    print(f"\n   鉁?BTC 鏁伴噺澶皬: {order_btc:.5f} < {lot_sz}")
    exit(1)

# 妫€鏌ヨ祫閲?
if actual_cost > avail_bal:
    print(f"\n   鉁?璧勯噾涓嶈冻: 闇€瑕?{actual_cost:.2f}, 鍙敤 {avail_bal:.2f}")
    exit(1)

# 4. 鎵ц涓嬪崟
print("\n4. 鎵ц闄愪环鍗曚拱鍏?..")
print(f"   涓嬪崟: {order_btc:.5f} BTC @ {order_px:.2f} USDT")
print("-" * 60)

result = api.place_order('BTC-USDT', 'buy', 'limit', str(order_btc), px=str(order_px), force_server=True)

print(f"\n   杩斿洖缁撴灉:")
print(f"   {result}")

if result and result.get('code') == '0':
    print("\n" + "=" * 60)
    print("[SUCCESS] 涓嬪崟鎴愬姛!")
    print("=" * 60)
    order_id = result['data'][0].get('ordId')
    print(f"   璁㈠崟ID: {order_id}")
else:
    print("\n" + "=" * 60)
    print("[FAILED] 涓嬪崟澶辫触!")
    print("=" * 60)
    error_msg = result.get('data', [{}])[0].get('sMsg', 'Unknown error') if result else 'No response'
    error_code = result.get('data', [{}])[0].get('sCode', 'Unknown') if result else 'N/A'
    print(f"   閿欒鐮? {error_code}")
    print(f"   閿欒淇℃伅: {error_msg}")

print("\n" + "=" * 60)
