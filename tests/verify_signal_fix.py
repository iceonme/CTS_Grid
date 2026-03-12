
import unittest
import sys
import os
from pathlib import Path

# 添加项目根目录到 sys.path
root_dir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(root_dir))

from datetime import datetime
from unittest.mock import MagicMock
from strategies.grid_mtf_6_0 import GridMTFStrategyV6_0
from core import MarketData, StrategyContext, Position, Side

class TestGridV60Fix(unittest.TestCase):
    def setUp(self):
        self.params = {
            "symbol": "BTC-USDT",
            "total_capital": 10000,
            "grid_period_initial": 6,
            "rsi_buy": 30,
            "rsi_sell": 70
        }
        self.strategy = GridMTFStrategyV6_0(name="TestStrat", **self.params)
        self.strategy.initialize()
        
        # 模拟 360 根数据以初始化网格
        for i in range(361):
            data = MarketData(
                timestamp=datetime.now(),
                symbol="BTC-USDT",
                open=70000, high=71000, low=69000, close=70000, volume=1
            )
            self.strategy.on_data(data, None)

    def test_signal_mutual_exclusion(self):
        """测试单柱信号排斥：不能同时产生买入和卖出信号"""
        # 手动构造一个既满足买入（RSI低）又满足卖出（MACD死叉）的极端场景
        self.strategy.state.current_rsi = 10 # 满足 RSI 买入
        self.strategy.state.macdhist = -1
        self.strategy.state.macdhist_prev = 1 # 满足 MACD 卖出
        
        data = MarketData(
            timestamp=datetime.now(), symbol="BTC-USDT",
            open=70000, high=70000, low=70000, close=70000, volume=1
        )
        
        # 假设有持仓，触发卖出条件
        mock_context = MagicMock(spec=StrategyContext)
        mock_context.positions = {"BTC-USDT": Position(symbol="BTC-USDT", size=0.1, avg_price=70000, entry_time=datetime.now())}
        mock_context.cash = 5000
        
        signals = self.strategy._generate_signals(data, mock_context)
        
        # 验证结果
        sides = [s.side for s in signals]
        self.assertFalse(Side.BUY in sides and Side.SELL in sides, "同一时间点不应产生对冲信号")
        print(f"Verified signals: {[s.reason for s in signals]}")

if __name__ == '__main__':
    unittest.main()
