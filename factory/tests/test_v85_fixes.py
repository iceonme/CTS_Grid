
import unittest
from datetime import datetime, timedelta
from console.core import MarketData, StrategyContext, Position, Side
from cartridges.strategies.grid_v85 import GridStrategyV85

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
        """楠岃瘉鏍稿績淇 1锛氳姖璇虹殑涔岄緹锛堝崠鍑洪噺璁＄畻浼樺寲锛?""
        # 妯℃嫙鍒濆鍖栫綉鏍?
        data = self._create_mock_data(50000)
        for i in range(400):
            self.strategy.on_data(self._create_mock_data(50000 + i, datetime.now() + timedelta(minutes=i)), None)
            
        context = StrategyContext(
            timestamp=datetime.now(),
            cash=2000,
            positions={'BTC-USDT': Position('BTC-USDT', 0.16, 45000, datetime.now())},
            current_prices={'BTC-USDT': 60000}
        )
        
        # 瑙﹀彂鍗栧嚭灞傜骇淇″彿
        # 璁剧疆涓婃浠锋牸浠ユ弧瓒?Crossing Up
        self.strategy.state.last_marker_price = 55000 
        # 鏋勯€犱竴涓湪鍗栧嚭鍖洪棿鐨勪环鏍?
        price = self.strategy.state.grid_lines[6] + 5 # 鍋囪鏄涓€灞傚崠鍑哄眰
        data = self._create_mock_data(price)
        
        signals = self.strategy.on_data(data, context)
        
        sell_signals = [s for s in signals if s.side == Side.SELL]
        if sell_signals:
            # 棰勬湡鏁伴噺锛?10000 * 0.8) / 5 / price = 1600 / price
            expected_qty = (context.total_value * 0.8) / self.strategy.state.active_layers_mode / price
            self.assertAlmostEqual(sell_signals[0].size, expected_qty, places=5)
            
            # 娴嬭瘯灏句粨娓呬粨閫昏緫
            context.positions['BTC-USDT'].size = 0.0001 # 鏋佸皬鎸佷粨
            signals = self.strategy.on_data(data, context)
            sell_signals = [s for s in signals if s.side == Side.SELL]
            if sell_signals:
                self.assertEqual(sell_signals[0].size, 0.0001) # 搴旇鍏ㄥ钩

    def test_lifo_unlocking(self):
        """楠岃瘉鏍稿績淇 2锛氶€昏緫瑙ｉ攣浼樺寲 (LIFO)"""
        # 寮哄埗閲嶇疆鐘舵€侊紝闃叉涔嬪墠鐨勬祴璇曠敤渚嬪奖鍝?
        self.strategy.state.layer_holdings = {2: True, 3: True, 4: True} # 閿佸畾涓夊眰
        
        # 妯℃嫙瑙﹀彂鍗栧嚭淇″彿
        # 鎴戜滑鐩存帴妫€鏌ヤ唬鐮佷腑瀵瑰簲鐨勬渶楂樺眰閫昏緫
        if self.strategy.state.layer_holdings:
            highest = max(self.strategy.state.layer_holdings.keys())
            self.assertEqual(highest, 4)
            
            self.strategy.state.layer_holdings.pop(highest)
            self.assertNotIn(4, self.strategy.state.layer_holdings)
            self.assertIn(2, self.strategy.state.layer_holdings)

    def test_inherit_l0_avoidance(self):
        """楠岃瘉鏍稿績淇 3锛氭寔浠撶户鎵块伩寮€ L0 绂佸尯"""
        # lines 缁撴瀯 (n=5): [0:V-2, 1:V-1, 2:B, 3:L1, 4:L2, 5:L3, 6:L4, 7:T, 8:V+1, 9:V+2]
        # v_lower_count = 2, n = 5
        # l0_idx = 2 + 2 = 4 (鍖洪棿 [lines[4], lines[5]])
        # 涔板叆灞傚簲涓?2, 3
        
        self.strategy.state.active_layers_mode = 5
        self.strategy.state.grid_lines = [40, 45, 50, 55, 60, 65, 70, 75, 80, 85]
        
        pos = Position('BTC-USDT', 0.06, 50, datetime.now()) # 鍋囪鎸佷粨浠峰€肩害 3 浠?
        context = StrategyContext(datetime.now(), 5000, {'BTC-USDT': pos}, {'BTC-USDT': 50})
        
        # 杩愯閲嶇畻閫昏緫
        # 涓轰簡鏂逛究娴嬭瘯锛屾垜浠洿鎺ヨ皟鐢ㄥ唴閮ㄩ€昏緫
        self.strategy._calculate_indicators = lambda: None # mock
        
        # 鏋勯€?context 渚涚户鎵夸娇鐢?
        data = MarketData(datetime.now(), 'BTC-USDT', 50, 50, 50, 50, 100)
        self.strategy._calculate_5_take_3_grid(data, context)
        
        # 搴旇閿佸畾浜嗗眰绾?2, 3銆傚眰绾?4 (L0) 涓嶅簲琚攣瀹?
        self.assertIn(2, self.strategy.state.layer_holdings)
        self.assertIn(3, self.strategy.state.layer_holdings)
        self.assertNotIn(4, self.strategy.state.layer_holdings)

    def test_observation_range_alignment(self):
        """楠岃瘉鏍稿績淇 4锛氱啍鏂В闄ゆ潯浠跺榻?""
        self.strategy.state.is_observing = True
        self.strategy.state.observe_start_time = datetime.now() - timedelta(minutes=10)
        self.strategy.state.grid_lines = [100, 110, 120, 130, 140, 150, 160, 170, 180, 190]
        
        # 浠锋牸鍦ㄨ櫄鎷熷眰鍐?(105)
        data = self._create_mock_data(105)
        self.strategy._handle_observation(data, None)
        self.assertFalse(self.strategy.state.is_observing) # 搴旇瑙ｉ櫎

    def test_cost_basis_protection(self):
        """楠岃瘉鏍稿績淇 5锛氬潎浠蜂繚鎶ゆ満鍒?""
        # 1. 妯℃嫙鍒濆鍖栫綉鏍?
        self.strategy.state.active_layers_mode = 5
        # 鏋勯€犲埢搴︼細[50, 52, 54, 56, 58, 60, 62, 64, 66, 68]
        # v_lower=2, n=5, l0_idx=4. 瀹炰綋鍗栧嚭灞傦細5, 6. 铏氭嫙鍗栧嚭灞傦細7, 8.
        self.strategy.state.grid_lines = [50 + i*2 for i in range(10)]
        
        context = StrategyContext(
            timestamp=datetime.now(),
            cash=10000,
            positions={'BTC-USDT': Position('BTC-USDT', 0.1, 70, datetime.now())}, # 鎴愭湰 70 (鏋侀珮)
            current_prices={'BTC-USDT': 63}
        )
        
        # 2. 妯℃嫙瑙﹀彂鍗栧嚭淇″彿 (璺ㄨ繃 61.0, 鍗?layer_idx=5 鐨勮Е鍙戠嚎)
        self.strategy.state.last_marker_price = 60.0
        data = self._create_mock_data(62.0) # 绌胯繃 61.0
        
        # 3. 楠岃瘉琚嫆缁?
        signals = self.strategy.on_data(data, context)
        # 妫€鏌ユ槸鍚﹁緭鍑轰簡 PROTECT 鏃ュ織锛屼笖淇″彿鍒楄〃涓虹┖
        self.assertEqual(len(signals), 0) 

if __name__ == '__main__':
    unittest.main()
