"""
测试OKXExecutor的持仓跟踪功能
验证demo模式下本地持仓跟踪是否能正确反映交易结果
"""
import sys
sys.path.insert(0, 'C:/cs/CTS_GRID/cts_grid')

from datetime import datetime
from core import FillEvent, Side, Position
from executors.okx import OKXExecutor


class MockOKXAPI:
    """模拟OKX API用于测试"""
    def __init__(self):
        self.balances_data = {'details': []}  # 模拟空持仓（延迟场景）
        
    def get_balances(self):
        # 模拟balance API延迟 - 始终返回空持仓
        return self.balances_data
    
    def get_positions(self):
        # demo模式下positions API通常返回空
        return []
    
    def get_ticker(self, inst_id):
        return {'last': '50000.00'}


class MockOKXExecutor(OKXExecutor):
    """用于测试的模拟执行器"""
    def __init__(self):
        # 跳过父类的API初始化
        self.is_demo = True
        self._order_map = {}
        self._last_trade_fetch = 0.0
        self._recent_trades = []
        self._local_positions = {}
        self._fill_callbacks = []
        self.api = MockOKXAPI()
        
        # 注册本地持仓跟踪回调
        self.register_fill_callback(self._on_fill_update_position)


def test_local_position_tracking():
    """测试本地持仓跟踪功能"""
    print("=" * 60)
    print("测试: Demo模式下本地持仓跟踪")
    print("=" * 60)
    
    executor = MockOKXExecutor()
    
    # 模拟API返回空持仓（延迟场景）
    print("\n[步骤1] API返回空持仓（模拟延迟）")
    positions = executor.get_all_positions()
    print(f"  获取持仓数量: {len(positions)}")
    assert len(positions) == 0, "API延迟时应返回空持仓"
    
    # 模拟买入成交
    print("\n[步骤2] 模拟买入成交: 0.001 BTC @ 50000")
    fill_buy = FillEvent(
        order_id="test_001",
        symbol="BTC-USDT",
        side=Side.BUY,
        filled_size=0.001,
        filled_price=50000.0,
        timestamp=datetime.now(),
        fee=0.0,
        quote_amount=50.0
    )
    executor._notify_fill(fill_buy)
    
    # 验证本地持仓已更新
    print("\n[步骤3] 检查本地持仓")
    positions = executor.get_all_positions()
    print(f"  获取持仓数量: {len(positions)}")
    
    if len(positions) == 0:
        print("  [FAIL] 本地持仓未正确跟踪")
        return False
    
    pos = positions[0]
    print(f"  持仓symbol: {pos.symbol}")
    print(f"  持仓size: {pos.size}")
    print(f"  持仓均价: {pos.avg_price}")
    
    # 验证持仓值
    assert abs(pos.size - 0.001) < 1e-9, f"持仓数量错误: {pos.size}"
    assert abs(pos.avg_price - 50000.0) < 1e-9, f"持仓均价错误: {pos.avg_price}"
    print("  [PASS] 本地持仓跟踪正确")
    
    # 模拟再次买入（测试加仓和均价计算）
    print("\n[步骤4] 模拟再次买入: 0.002 BTC @ 51000")
    fill_buy2 = FillEvent(
        order_id="test_002",
        symbol="BTC-USDT",
        side=Side.BUY,
        filled_size=0.002,
        filled_price=51000.0,
        timestamp=datetime.now(),
        fee=0.0,
        quote_amount=102.0
    )
    executor._notify_fill(fill_buy2)
    
    positions = executor.get_all_positions()
    pos = positions[0]
    expected_size = 0.003  # 0.001 + 0.002
    expected_avg = (0.001 * 50000 + 0.002 * 51000) / 0.003  # 约 50666.67
    
    print(f"  持仓size: {pos.size} (期望: {expected_size})")
    print(f"  持仓均价: {pos.avg_price:.2f} (期望: {expected_avg:.2f})")
    
    assert abs(pos.size - expected_size) < 1e-9, f"加仓后持仓数量错误: {pos.size}"
    assert abs(pos.avg_price - expected_avg) < 1e-6, f"加仓后均价计算错误: {pos.avg_price}"
    print("  [PASS] 加仓和均价计算正确")
    
    # 模拟卖出（部分减仓）
    print("\n[步骤5] 模拟卖出: 0.001 BTC @ 52000")
    fill_sell = FillEvent(
        order_id="test_003",
        symbol="BTC-USDT",
        side=Side.SELL,
        filled_size=0.001,
        filled_price=52000.0,
        timestamp=datetime.now(),
        fee=0.0,
        quote_amount=52.0
    )
    executor._notify_fill(fill_sell)
    
    positions = executor.get_all_positions()
    pos = positions[0]
    expected_size = 0.002  # 0.003 - 0.001
    
    print(f"  持仓size: {pos.size} (期望: {expected_size})")
    
    assert abs(pos.size - expected_size) < 1e-9, f"减仓后持仓数量错误: {pos.size}"
    print("  [PASS] 减仓计算正确")
    
    # 模拟全部卖出
    print("\n[步骤6] 模拟全部卖出: 0.002 BTC @ 52000")
    fill_sell_all = FillEvent(
        order_id="test_004",
        symbol="BTC-USDT",
        side=Side.SELL,
        filled_size=0.002,
        filled_price=52000.0,
        timestamp=datetime.now(),
        fee=0.0,
        quote_amount=104.0
    )
    executor._notify_fill(fill_sell_all)
    
    positions = executor.get_all_positions()
    print(f"  获取持仓数量: {len(positions)}")
    
    assert len(positions) == 0, "全部卖出后应无持仓"
    print("  [PASS] 全部卖出后持仓清零正确")
    
    print("\n" + "=" * 60)
    print("[PASS] 所有测试通过!")
    print("=" * 60)
    return True


def test_merge_logic():
    """测试持仓合并逻辑"""
    print("\n" + "=" * 60)
    print("测试: 持仓合并逻辑")
    print("=" * 60)
    
    executor = MockOKXExecutor()
    
    # 创建测试数据
    now = datetime.now()
    api_positions = [
        Position(symbol="BTC-USDT", size=0.0, avg_price=0, entry_time=now),  # API返回零
    ]
    local_positions = [
        Position(symbol="BTC-USDT", size=0.001, avg_price=50000, entry_time=now),
    ]
    
    print("\n[场景1] API返回零，本地有持仓")
    result = executor._merge_positions(api_positions, local_positions)
    print(f"  合并结果数量: {len(result)}")
    print(f"  持仓size: {result[0].size if result else 'N/A'}")
    
    assert len(result) == 1, "应返回本地持仓"
    assert abs(result[0].size - 0.001) < 1e-9, "应使用本地持仓数据"
    print("  [PASS] 合并逻辑正确（使用本地数据）")
    
    # 场景2：API有有效数据，优先使用API
    api_positions2 = [
        Position(symbol="BTC-USDT", size=0.002, avg_price=51000, entry_time=now),
    ]
    local_positions2 = [
        Position(symbol="BTC-USDT", size=0.001, avg_price=50000, entry_time=now),
    ]
    
    print("\n[场景2] API有有效数据，优先使用API")
    result2 = executor._merge_positions(api_positions2, local_positions2)
    print(f"  合并结果数量: {len(result2)}")
    print(f"  持仓size: {result2[0].size if result2 else 'N/A'}")
    
    assert len(result2) == 1, "应返回持仓"
    assert abs(result2[0].size - 0.002) < 1e-9, "应优先使用API数据"
    print("  [PASS] 合并逻辑正确（优先使用API数据）")
    
    print("\n" + "=" * 60)
    print("[PASS] 合并逻辑测试通过!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    try:
        test_local_position_tracking()
        test_merge_logic()
        print("\n[SUCCESS] 所有测试通过!")
    except AssertionError as e:
        print(f"\n[FAIL] 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
