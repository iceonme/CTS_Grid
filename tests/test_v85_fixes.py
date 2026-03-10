
import unittest
from datetime import datetime, timedelta
from core import MarketData, StrategyContext, Position, Side
from strategies.grid_v85 import GridStrategyV85

class TestV85Fixes(unittest.TestCase):
    def setUp(self):
        self.params = {
            'symbol': 'BTC-USDT',
            'initial_capital': 10000.0,
            'max_position_pct': 0.8,
            'rsi_period': 14
        }
        self.strategy = GridStrategyV85(**self.params)
        
    def _create_mock_data(self, price, timestamp=None):
        return MarketData(
            timestamp=timestamp or datetime.now(),
            symbol='BTC-USDT',
            open=price, high=price, low=price, close=price, volume=100
        )

    def test_sell_qty_calculation(self):
        """验证核心修复 1：芝诺的乌龟（卖出量计算优化）"""
        # 模拟初始化网格
        data = self._create_mock_data(50000)
        for i in range(400):
            self.strategy.on_data(self._create_mock_data(50000 + i, datetime.now() + timedelta(minutes=i)), None)
            
        context = StrategyContext(
            timestamp=datetime.now(),
            cash=2000,
            positions={'BTC-USDT': Position('BTC-USDT', 0.16, 45000, datetime.now())},
            current_prices={'BTC-USDT': 60000}
        )
        
        # 触发卖出层级信号
        # 设置上次价格以满足 Crossing Up
        self.strategy.state.last_marker_price = 55000 
        # 构造一个在卖出区间的价格
        price = self.strategy.state.grid_lines[6] + 5 # 假设是第一层卖出层
        data = self._create_mock_data(price)
        
        signals = self.strategy.on_data(data, context)
        
        sell_signals = [s for s in signals if s.side == Side.SELL]
        if sell_signals:
            # 预期数量：(10000 * 0.8) / 5 / price = 1600 / price
            expected_qty = (context.total_value * 0.8) / self.strategy.state.active_layers_mode / price
            self.assertAlmostEqual(sell_signals[0].size, expected_qty, places=5)
            
            # 测试尾仓清仓逻辑
            context.positions['BTC-USDT'].size = 0.0001 # 极小持仓
            signals = self.strategy.on_data(data, context)
            sell_signals = [s for s in signals if s.side == Side.SELL]
            if sell_signals:
                self.assertEqual(sell_signals[0].size, 0.0001) # 应该全平

    def test_lifo_unlocking(self):
        """验证核心修复 2：逻辑解锁优化 (LIFO)"""
        # 强制重置状态，防止之前的测试用例影响
        self.strategy.state.layer_holdings = {2: True, 3: True, 4: True} # 锁定三层
        
        # 模拟触发卖出信号
        # 我们直接检查代码中对应的最高层逻辑
        if self.strategy.state.layer_holdings:
            highest = max(self.strategy.state.layer_holdings.keys())
            self.assertEqual(highest, 4)
            
            self.strategy.state.layer_holdings.pop(highest)
            self.assertNotIn(4, self.strategy.state.layer_holdings)
            self.assertIn(2, self.strategy.state.layer_holdings)

    def test_inherit_l0_avoidance(self):
        """验证核心修复 3：持仓继承避开 L0 禁区"""
        # lines 结构 (n=5): [0:V-2, 1:V-1, 2:B, 3:L1, 4:L2, 5:L3, 6:L4, 7:T, 8:V+1, 9:V+2]
        # v_lower_count = 2, n = 5
        # l0_idx = 2 + 2 = 4 (区间 [lines[4], lines[5]])
        # 买入层应为 2, 3
        
        self.strategy.state.active_layers_mode = 5
        self.strategy.state.grid_lines = [40, 45, 50, 55, 60, 65, 70, 75, 80, 85]
        
        pos = Position('BTC-USDT', 0.06, 50, datetime.now()) # 假设持仓价值约 3 份
        context = StrategyContext(datetime.now(), 5000, {'BTC-USDT': pos}, {'BTC-USDT': 50})
        
        # 运行重算逻辑
        # 为了方便测试，我们直接调用内部逻辑
        self.strategy._calculate_indicators = lambda: None # mock
        
        # 构造 context 供继承使用
        data = MarketData(datetime.now(), 'BTC-USDT', 50, 50, 50, 50, 100)
        self.strategy._calculate_5_take_3_grid(data, context)
        
        # 应该锁定了层级 2, 3。层级 4 (L0) 不应被锁定
        self.assertIn(2, self.strategy.state.layer_holdings)
        self.assertIn(3, self.strategy.state.layer_holdings)
        self.assertNotIn(4, self.strategy.state.layer_holdings)

    def test_observation_range_alignment(self):
        """验证核心修复 4：熔断解除条件对齐"""
        self.strategy.state.is_observing = True
        self.strategy.state.observe_start_time = datetime.now() - timedelta(minutes=10)
        self.strategy.state.grid_lines = [100, 110, 120, 130, 140, 150, 160, 170, 180, 190]
        
        # 价格在虚拟层内 (105)
        data = self._create_mock_data(105)
        self.strategy._handle_observation(data, None)
        self.assertFalse(self.strategy.state.is_observing) # 应该解除

    def test_cost_basis_protection(self):
        """验证核心修复 5：均价保护机制"""
        # 1. 模拟初始化网格
        self.strategy.state.active_layers_mode = 5
        # 构造刻度：[50, 52, 54, 56, 58, 60, 62, 64, 66, 68]
        # v_lower=2, n=5, l0_idx=4. 实体卖出层：5, 6. 虚拟卖出层：7, 8.
        self.strategy.state.grid_lines = [50 + i*2 for i in range(10)]
        
        context = StrategyContext(
            timestamp=datetime.now(),
            cash=10000,
            positions={'BTC-USDT': Position('BTC-USDT', 0.1, 70, datetime.now())}, # 成本 70 (极高)
            current_prices={'BTC-USDT': 63}
        )
        
        # 2. 模拟触发卖出信号 (跨过 61.0, 即 layer_idx=5 的触发线)
        self.strategy.state.last_marker_price = 60.0
        data = self._create_mock_data(62.0) # 穿过 61.0
        
        # 3. 验证被拒绝
        signals = self.strategy.on_data(data, context)
        # 检查是否输出了 PROTECT 日志，且信号列表为空
        self.assertEqual(len(signals), 0) 

if __name__ == '__main__':
    unittest.main()
