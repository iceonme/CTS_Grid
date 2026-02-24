"""
测试 OKX 买入功能 - 修复精度问题后
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
print("OKX 买入测试 - 修复精度问题")
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

# 3. 测试修复后的下单逻辑
print("\n3. 测试修复后的下单逻辑...")
print("-" * 60)

# OKX 参数
min_order_usdt = 100  # 最小订单金额
tick_sz = 0.01       # 价格精度 (2位小数)
lot_sz = 0.00001     # 数量精度 (5位小数)

# 计算订单参数 (模拟修复后的逻辑)
test_usdt = max(100, min_order_usdt)  # 至少 100 USDT
order_btc = test_usdt / current_price
order_btc = round(order_btc, 5)       # 截断到 5 位小数
order_px = round(current_price, 2)    # 截断到 2 位小数
actual_cost = order_btc * order_px

print(f"\n   测试参数:")
print(f"   - 下单金额: {test_usdt} USDT")
print(f"   - 当前价格: {current_price:.2f} USDT")
print(f"   - 调整后价格: {order_px:.2f} USDT")
print(f"   - BTC 数量: {order_btc:.5f} BTC")
print(f"   - 实际成本: {actual_cost:.2f} USDT")

# 检查最小数量
if order_btc < lot_sz:
    print(f"\n   ✗ BTC 数量太小: {order_btc:.5f} < {lot_sz}")
    exit(1)

# 检查资金
if actual_cost > avail_bal:
    print(f"\n   ✗ 资金不足: 需要 {actual_cost:.2f}, 可用 {avail_bal:.2f}")
    exit(1)

# 4. 执行下单
print("\n4. 执行限价单买入...")
print(f"   下单: {order_btc:.5f} BTC @ {order_px:.2f} USDT")
print("-" * 60)

result = api.place_order('BTC-USDT', 'buy', 'limit', str(order_btc), px=str(order_px), force_server=True)

print(f"\n   返回结果:")
print(f"   {result}")

if result and result.get('code') == '0':
    print("\n" + "=" * 60)
    print("[SUCCESS] 下单成功!")
    print("=" * 60)
    order_id = result['data'][0].get('ordId')
    print(f"   订单ID: {order_id}")
else:
    print("\n" + "=" * 60)
    print("[FAILED] 下单失败!")
    print("=" * 60)
    error_msg = result.get('data', [{}])[0].get('sMsg', 'Unknown error') if result else 'No response'
    error_code = result.get('data', [{}])[0].get('sCode', 'Unknown') if result else 'N/A'
    print(f"   错误码: {error_code}")
    print(f"   错误信息: {error_msg}")

print("\n" + "=" * 60)
