"""
娴嬭瘯 OKX 涔板叆鍔熻兘
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
print("OKX 涔板叆娴嬭瘯")
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

# 3. 璁＄畻涔板叆鏁伴噺锛堟祴璇曚笉鍚岄噾棰濓級
test_amounts = [10, 50, 100, 500, 1000]  # 娴嬭瘯涓嶅悓閲戦

print(f"\n3. 鍑嗗娴嬭瘯涓嶅悓閲戦...")
print(f"   褰撳墠浠锋牸: {current_price:.2f} USDT")

# 4. 娴嬭瘯涓嶅悓閲戦
for test_usdt in test_amounts:
    test_btc = test_usdt / current_price
    print(f"\n4. 娴嬭瘯涔板叆 {test_usdt} USDT ({test_btc:.6f} BTC)...")
    
    result = api.place_order('BTC-USDT', 'buy', 'market', str(test_btc), force_server=True)
    
    if result and result.get('code') == '0':
        print(f"   SUCCESS! 閲戦 {test_usdt} USDT 閫氳繃!")
        order_id = result['data'][0].get('ordId')
        print(f"   璁㈠崟ID: {order_id}")
        break
    else:
        error_msg = result.get('data', [{}])[0].get('sMsg', 'Unknown error')
        print(f"   FAILED: {error_msg}")

print("\n" + "=" * 60)
