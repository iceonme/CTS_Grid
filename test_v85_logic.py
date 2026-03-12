
import os
import sys
from datetime import datetime, timedelta
from typing import List

# 确保模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import MarketData, StrategyContext, Position
from strategies.grid_v85 import GridStrategyV85

class MockContext(StrategyContext):
    def __init__(self, cash=10000.0, timestamp=None):
        self.cash = cash
        self.positions = {}
        self.current_prices = {}
        self.timestamp = timestamp or datetime.now()

def create_bar(price: float, ts: datetime) -> MarketData:
    return MarketData(
        timestamp=ts,
        symbol="BTC-USDT",
        open=price,
        high=price + 10,
        low=price - 10,
        close=price,
        volume=1.0
    )

def test_5_take_3_logic():
    print("\n[TEST] 验证 5取3 抗插针算法...")
    strategy = GridStrategyV85(name="Test_V85")
    
    # 构造预热数据: 5个时段，其中一个时段有极端插针
    start_time = datetime(2025, 3, 10, 12, 0)
    
    # 正常价格 90000
    prices = [90000] * 240
    # 在第 100 个点加入一个 120000 的插针高点
    prices[100] = 120000 
    # 在第 200 个点加入一个 60000 的插针低点
    prices[200] = 60000
    
    for i, p in enumerate(prices):
        bar = create_bar(p, start_time + timedelta(minutes=i))
        # 模拟插针
        if i == 100: bar.high = 120000
        if i == 200: bar.low = 60000
        
        strategy.on_data(bar, None)
        
    # 触发重算
    strategy._calculate_5_take_3_grid(create_bar(90000, start_time + timedelta(minutes=240)), None)
    
    # 验证插针是否被过滤
    # 如果没过滤，base_top 会非常高。如果过滤了，base_top 应该接近 90000
    print(f"计算出的中枢顶部: {strategy.state.base_top:.2f}")
    assert strategy.state.base_top < 100000, "5取3算法未能成功过滤高位插针"
    assert strategy.state.base_bottom > 80000, "5取3算法未能成功过滤低位插针"
    print("SUCCESS: 5取3 算法验证通过")

def test_layer_locking():
    print("\n[TEST] 验证层级锁定 (防复吸) 逻辑...")
    strategy = GridStrategyV85(name="Test_Locking")
    ctx = MockContext()
    
    # 预热
    start_time = datetime(2025, 3, 10, 12, 0)
    for i in range(240):
        strategy.on_data(create_bar(40000, start_time + timedelta(minutes=i)), ctx)
        
    # 设置一个人工网格: 40000 为底，41000 为顶, n=5
    # 线: [..., 40000, 40200, 40400, 40600, 40800, 41000, ...]
    # L(-1) 区间是 [39800, 40000] (虚) 或 [40000, 40200] (实)
    # 根据 5层模式，l0_idx = 4. 实体层索引 2,3 (买) 5,6 (卖). 
    # 区间索引 3 是 L(-1) [40200, 40400] 穿过 40300 触发买
    strategy.state.grid_lines = [39600, 39800, 40000, 40200, 40400, 40600, 40800, 41000, 41200, 41400]
    strategy.state.last_marker_price = 40500
    
    # 1. 下穿触发买入
    bar1 = create_bar(40250, start_time + timedelta(minutes=241))
    signals = strategy.on_data(bar1, ctx)
    assert len(signals) == 1, "应该触发一次买入"
    assert 3 in strategy.state.layer_holdings, "层级 3 应该被锁定"
    
    # 2. 在同一区间反复横跳，不应该再次买入
    strategy.state.last_marker_price = 40350
    bar2 = create_bar(40250, start_time + timedelta(minutes=242))
    signals = strategy.on_data(bar2, ctx)
    assert len(signals) == 0, "层级已锁定，不应重复买入"
    
    print("SUCCESS: 层级锁定逻辑验证通过")

if __name__ == "__main__":
    try:
        test_5_take_3_logic()
        test_layer_locking()
        print("\n所有核心逻辑测试通过！")
    except AssertionError as e:
        print(f"\n测试失败: {e}")
        sys.exit(1)
