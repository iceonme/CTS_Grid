"""
绛栫暐鍗曞厓娴嬭瘯

杩愯: python -m pytest tests/test_strategy.py -v
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from console.core import MarketData, StrategyContext, Side
from cartridges.strategies import GridRSIStrategy


class TestGridRSIStrategy(unittest.TestCase):
    """Grid RSI 绛栫暐娴嬭瘯"""
    
    def setUp(self):
        """娴嬭瘯鍓嶅噯澶?""
        self.strategy = GridRSIStrategy(
            symbol="BTC-USDT",
            grid_levels=5,
            rsi_period=14,
            base_position_pct=0.1
        )
        self.strategy.initialize()
    
    def _create_market_data(self, timestamp, open_p, high, low, close, volume=100):
        """鍒涘缓甯傚満鏁版嵁"""
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
        """鍒涘缓绛栫暐涓婁笅鏂?""
        return StrategyContext(
            timestamp=datetime.now(),
            cash=cash,
            positions=positions or {},
            current_prices={"BTC-USDT": 50000}
        )
    
    def test_initialization(self):
        """娴嬭瘯绛栫暐鍒濆鍖?""
        self.assertEqual(self.strategy.name, "GridRSI_V4")
        self.assertEqual(self.strategy.symbol, "BTC-USDT")
        self.assertEqual(self.strategy.params['grid_levels'], 5)
    
    def test_signal_generation(self):
        """娴嬭瘯淇″彿鐢熸垚"""
        # 鐢熸垚瓒冲鐨勬祴璇曟暟鎹?
        base_time = datetime.now()
        context = self._create_context()
        
        # 鍏堢敓鎴?20 鏉℃暟鎹鐑?
        for i in range(20):
            data = self._create_market_data(
                timestamp=base_time + timedelta(minutes=i),
                open_p=40000 + i * 10,
                high=40100 + i * 10,
                low=39900 + i * 10,
                close=40000 + i * 10
            )
            signals = self.strategy.on_data(data, context)
        
        # 楠岃瘉绛栫暐宸插垵濮嬪寲缃戞牸
        self.assertIsNotNone(self.strategy.state.grid_upper)
        self.assertIsNotNone(self.strategy.state.grid_lower)
        self.assertEqual(len(self.strategy.state.grid_prices), 5)
    
    def test_rsi_calculation(self):
        """娴嬭瘯 RSI 璁＄畻"""
        df = pd.DataFrame({
            'close': [100, 102, 101, 103, 105, 104, 106, 108, 107, 109, 
                      110, 108, 106, 104, 102, 100, 98, 96, 94, 92]
        })
        
        # 閫氳繃绛栫暐鍐呴儴鏂规硶璁＄畻
        rsi = self.strategy._calculate_rsi(df['close'])
        
        # RSI 搴旇鍦?0-100 涔嬮棿
        self.assertGreaterEqual(rsi, 0)
        self.assertLessEqual(rsi, 100)
    
    def test_position_size_calculation(self):
        """娴嬭瘯浠撲綅璁＄畻"""
        context = self._create_context(cash=10000)
        
        # 涔板叆淇″彿杈冨己鏃?
        size = self.strategy._calculate_position_size(context, rsi_signal=0.8, is_buy=True)
        self.assertGreater(size, 0)
        self.assertLessEqual(size, context.cash * 0.95)


class TestSignal(unittest.TestCase):
    """淇″彿绫绘祴璇?""
    
    def test_signal_creation(self):
        """娴嬭瘯淇″彿鍒涘缓"""
        from console.core import Signal
        
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
