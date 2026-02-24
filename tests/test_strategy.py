"""
策略单元测试

运行: python -m pytest tests/test_strategy.py -v
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from core import MarketData, StrategyContext, Side
from strategies import GridRSIStrategy


class TestGridRSIStrategy(unittest.TestCase):
    """Grid RSI 策略测试"""
    
    def setUp(self):
        """测试前准备"""
        self.strategy = GridRSIStrategy(
            symbol="BTC-USDT",
            grid_levels=5,
            rsi_period=14,
            base_position_pct=0.1
        )
        self.strategy.initialize()
    
    def _create_market_data(self, timestamp, open_p, high, low, close, volume=100):
        """创建市场数据"""
        return MarketData(
            timestamp=timestamp,
            symbol="BTC-USDT",
            open=open_p,
            high=high,
            low=low,
            close=close,
            volume=volume
        )
    
    def _create_context(self, cash=10000, positions=None):
        """创建策略上下文"""
        return StrategyContext(
            timestamp=datetime.now(),
            cash=cash,
            positions=positions or {},
            current_prices={"BTC-USDT": 50000}
        )
    
    def test_initialization(self):
        """测试策略初始化"""
        self.assertEqual(self.strategy.name, "GridRSI_V4")
        self.assertEqual(self.strategy.symbol, "BTC-USDT")
        self.assertEqual(self.strategy.params['grid_levels'], 5)
    
    def test_signal_generation(self):
        """测试信号生成"""
        # 生成足够的测试数据
        base_time = datetime.now()
        context = self._create_context()
        
        # 先生成 20 条数据预热
        for i in range(20):
            data = self._create_market_data(
                timestamp=base_time + timedelta(minutes=i),
                open_p=40000 + i * 10,
                high=40100 + i * 10,
                low=39900 + i * 10,
                close=40000 + i * 10
            )
            signals = self.strategy.on_data(data, context)
        
        # 验证策略已初始化网格
        self.assertIsNotNone(self.strategy.state.grid_upper)
        self.assertIsNotNone(self.strategy.state.grid_lower)
        self.assertEqual(len(self.strategy.state.grid_prices), 5)
    
    def test_rsi_calculation(self):
        """测试 RSI 计算"""
        df = pd.DataFrame({
            'close': [100, 102, 101, 103, 105, 104, 106, 108, 107, 109, 
                      110, 108, 106, 104, 102, 100, 98, 96, 94, 92]
        })
        
        # 通过策略内部方法计算
        rsi = self.strategy._calculate_rsi(df['close'])
        
        # RSI 应该在 0-100 之间
        self.assertGreaterEqual(rsi, 0)
        self.assertLessEqual(rsi, 100)
    
    def test_position_size_calculation(self):
        """测试仓位计算"""
        context = self._create_context(cash=10000)
        
        # 买入信号较强时
        size = self.strategy._calculate_position_size(context, rsi_signal=0.8, is_buy=True)
        self.assertGreater(size, 0)
        self.assertLessEqual(size, context.cash * 0.95)


class TestSignal(unittest.TestCase):
    """信号类测试"""
    
    def test_signal_creation(self):
        """测试信号创建"""
        from core import Signal
        
        signal = Signal(
            timestamp=datetime.now(),
            symbol="BTC-USDT",
            side=Side.BUY,
            size=100,
            price=50000,
            reason="Test"
        )
        
        self.assertEqual(signal.symbol, "BTC-USDT")
        self.assertEqual(signal.side, Side.BUY)
        self.assertEqual(signal.size, 100)


if __name__ == '__main__':
    unittest.main()
