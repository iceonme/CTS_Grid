"""
测试 OKX 买入功能
"""
import time
from okx_config import OKXAPI

# API 配置
api_config = {
    'api_key': '72aac042-9859-48ec-8e27-9722524429a6',
    'api_secret': 'CCFE2963EBD154027557D24CFA2CAA57',
    'passphrase': 'Tonghua9527_',
    'is_demo': True
}

print("=" * 60)
print("OKX 买入测试")
print("=" * 60)

# 初始化 API
api = OKXAPI(**api_config)

# 1. 获取当前价格
print("\n1. 获取当前 BTC 价格...")
ticker = api.get_ticker('BTC-USDT')
if ticker:
    current_price = float(ticker['last'])
    print(f"   当前价格: {current_price:.2f} USDT")
else:
    print("   ✗ 获取价格失败")
    exit(1)

# 2. 获取账户余额
print("\n2. 获取账户余额...")
balance = api.get_balance()
if balance:
    avail_bal = balance['availBal']
    print(f"   可用 USDT: {avail_bal:.2f}")
else:
    print("   ✗ 获取余额失败")
    exit(1)

# 3. 计算买入数量（测试不同金额）
test_amounts = [10, 50, 100, 500, 1000]  # 测试不同金额

print(f"\n3. 准备测试不同金额...")
print(f"   当前价格: {current_price:.2f} USDT")

# 4. 测试不同金额
for test_usdt in test_amounts:
    test_btc = test_usdt / current_price
    print(f"\n4. 测试买入 {test_usdt} USDT ({test_btc:.6f} BTC)...")
    
    result = api.place_order('BTC-USDT', 'buy', 'market', str(test_btc), force_server=True)
    
    if result and result.get('code') == '0':
        print(f"   SUCCESS! 金额 {test_usdt} USDT 通过!")
        order_id = result['data'][0].get('ordId')
        print(f"   订单ID: {order_id}")
        break
    else:
        error_msg = result.get('data', [{}])[0].get('sMsg', 'Unknown error')
        print(f"   FAILED: {error_msg}")

print("\n" + "=" * 60)
