
import unittest
import sys
import os
from pathlib import Path

# 娣诲姞椤圭洰鏍圭洰褰曞埌 sys.path
root_dir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(root_dir))

from datetime import datetime
from unittest.mock import MagicMock
from cartridges.strategies.grid_mtf_6_0 import GridMTFStrategyV6_0
from console.core import MarketData, StrategyContext, Position, Side

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
        
        # 妯℃嫙 360 鏍规暟鎹互鍒濆鍖栫綉鏍?
        for i in range(361):
            data = MarketData(
                timestamp=datetime.now(),
                symbol="BTC-USDT",
                open=70000, high=71000, low=69000, close=70000, volume=1
            )
            self.strategy.on_data(data, None)

    def test_signal_mutual_exclusion(self):
        """娴嬭瘯鍗曟煴淇″彿鎺掓枼锛氫笉鑳藉悓鏃朵骇鐢熶拱鍏ュ拰鍗栧嚭淇″彿"""
        # 鎵嬪姩鏋勯€犱竴涓棦婊¤冻涔板叆锛圧SI浣庯級鍙堟弧瓒冲崠鍑猴紙MACD姝诲弶锛夌殑鏋佺鍦烘櫙
        self.strategy.state.current_rsi = 10 # 婊¤冻 RSI 涔板叆
        self.strategy.state.macdhist = -1
        self.strategy.state.macdhist_prev = 1 # 婊¤冻 MACD 鍗栧嚭
        
        data = MarketData(
            timestamp=datetime.now(), symbol="BTC-USDT",
            open=70000, high=70000, low=70000, close=70000, volume=1
        )
        
        # 鍋囪鏈夋寔浠擄紝瑙﹀彂鍗栧嚭鏉′欢
        mock_context = MagicMock(spec=StrategyContext)
        mock_context.positions = {"BTC-USDT": Position(symbol="BTC-USDT", size=0.1, avg_price=70000, entry_time=datetime.now())}
        mock_context.cash = 5000
        
        signals = self.strategy._generate_signals(data, mock_context)
        
        # 楠岃瘉缁撴灉
        sides = [s.side for s in signals]
        self.assertFalse(Side.BUY in sides and Side.SELL in sides, "鍚屼竴鏃堕棿鐐逛笉搴斾骇鐢熷鍐蹭俊鍙?)
        print(f"Verified signals: {[s.reason for s in signals]}")

if __name__ == '__main__':
    unittest.main()
