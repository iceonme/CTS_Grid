"""
娴嬭瘯OKXExecutor鐨勬寔浠撹窡韪姛鑳?
楠岃瘉demo妯″紡涓嬫湰鍦版寔浠撹窡韪槸鍚﹁兘姝ｇ‘鍙嶆槧浜ゆ槗缁撴灉
"""
import sys
sys.path.insert(0, 'C:/cs/CTS_GRID/cts_grid')

from datetime import datetime
from console.core import FillEvent, Side, Position
from cartridges.bridge.executors.okx import OKXExecutor


class MockOKXAPI:
    """妯℃嫙OKX API鐢ㄤ簬娴嬭瘯"""
    def __init__(self):
        self.balances_data = {'details': []}  # 妯℃嫙绌烘寔浠擄紙寤惰繜鍦烘櫙锛?
        
    def get_balances(self):
        # 妯℃嫙balance API寤惰繜 - 濮嬬粓杩斿洖绌烘寔浠?
        return self.balances_data
    
    def get_positions(self):
        # demo妯″紡涓媝ositions API閫氬父杩斿洖绌?
        return []
    
    def get_ticker(self, inst_id):
        return {'last': '50000.00'}


class MockOKXExecutor(OKXExecutor):
    """鐢ㄤ簬娴嬭瘯鐨勬ā鎷熸墽琛屽櫒"""
    def __init__(self):
        # 璺宠繃鐖剁被鐨凙PI鍒濆鍖?
        self.is_demo = True
        self._order_map = {}
        self._last_trade_fetch = 0.0
        self._recent_trades = []
        self._local_positions = {}
        self._fill_callbacks = []
        self.api = MockOKXAPI()
        
        # 娉ㄥ唽鏈湴鎸佷粨璺熻釜鍥炶皟
        self.register_fill_callback(self._on_fill_update_position)


def test_local_position_tracking():
    """娴嬭瘯鏈湴鎸佷粨璺熻釜鍔熻兘"""
    print("=" * 60)
    print("娴嬭瘯: Demo妯″紡涓嬫湰鍦版寔浠撹窡韪?)
    print("=" * 60)
    
    executor = MockOKXExecutor()
    
    # 妯℃嫙API杩斿洖绌烘寔浠擄紙寤惰繜鍦烘櫙锛?
    print("\n[姝ラ1] API杩斿洖绌烘寔浠擄紙妯℃嫙寤惰繜锛?)
    positions = executor.get_all_positions()
    print(f"  鑾峰彇鎸佷粨鏁伴噺: {len(positions)}")
    assert len(positions) == 0, "API寤惰繜鏃跺簲杩斿洖绌烘寔浠?
    
    # 妯℃嫙涔板叆鎴愪氦
    print("\n[姝ラ2] 妯℃嫙涔板叆鎴愪氦: 0.001 BTC @ 50000")
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
    
    # 楠岃瘉鏈湴鎸佷粨宸叉洿鏂?
    print("\n[姝ラ3] 妫€鏌ユ湰鍦版寔浠?)
    positions = executor.get_all_positions()
    print(f"  鑾峰彇鎸佷粨鏁伴噺: {len(positions)}")
    
    if len(positions) == 0:
        print("  [FAIL] 鏈湴鎸佷粨鏈纭窡韪?)
        return False
    
    pos = positions[0]
    print(f"  鎸佷粨symbol: {pos.symbol}")
    print(f"  鎸佷粨size: {pos.size}")
    print(f"  鎸佷粨鍧囦环: {pos.avg_price}")
    
    # 楠岃瘉鎸佷粨鍊?
    assert abs(pos.size - 0.001) < 1e-9, f"鎸佷粨鏁伴噺閿欒: {pos.size}"
    assert abs(pos.avg_price - 50000.0) < 1e-9, f"鎸佷粨鍧囦环閿欒: {pos.avg_price}"
    print("  [PASS] 鏈湴鎸佷粨璺熻釜姝ｇ‘")
    
    # 妯℃嫙鍐嶆涔板叆锛堟祴璇曞姞浠撳拰鍧囦环璁＄畻锛?
    print("\n[姝ラ4] 妯℃嫙鍐嶆涔板叆: 0.002 BTC @ 51000")
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
    expected_avg = (0.001 * 50000 + 0.002 * 51000) / 0.003  # 绾?50666.67
    
    print(f"  鎸佷粨size: {pos.size} (鏈熸湜: {expected_size})")
    print(f"  鎸佷粨鍧囦环: {pos.avg_price:.2f} (鏈熸湜: {expected_avg:.2f})")
    
    assert abs(pos.size - expected_size) < 1e-9, f"鍔犱粨鍚庢寔浠撴暟閲忛敊璇? {pos.size}"
    assert abs(pos.avg_price - expected_avg) < 1e-6, f"鍔犱粨鍚庡潎浠疯绠楅敊璇? {pos.avg_price}"
    print("  [PASS] 鍔犱粨鍜屽潎浠疯绠楁纭?)
    
    # 妯℃嫙鍗栧嚭锛堥儴鍒嗗噺浠擄級
    print("\n[姝ラ5] 妯℃嫙鍗栧嚭: 0.001 BTC @ 52000")
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
    
    print(f"  鎸佷粨size: {pos.size} (鏈熸湜: {expected_size})")
    
    assert abs(pos.size - expected_size) < 1e-9, f"鍑忎粨鍚庢寔浠撴暟閲忛敊璇? {pos.size}"
    print("  [PASS] 鍑忎粨璁＄畻姝ｇ‘")
    
    # 妯℃嫙鍏ㄩ儴鍗栧嚭
    print("\n[姝ラ6] 妯℃嫙鍏ㄩ儴鍗栧嚭: 0.002 BTC @ 52000")
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
    print(f"  鑾峰彇鎸佷粨鏁伴噺: {len(positions)}")
    
    assert len(positions) == 0, "鍏ㄩ儴鍗栧嚭鍚庡簲鏃犳寔浠?
    print("  [PASS] 鍏ㄩ儴鍗栧嚭鍚庢寔浠撴竻闆舵纭?)
    
    print("\n" + "=" * 60)
    print("[PASS] 鎵€鏈夋祴璇曢€氳繃!")
    print("=" * 60)
    return True


def test_merge_logic():
    """娴嬭瘯鎸佷粨鍚堝苟閫昏緫"""
    print("\n" + "=" * 60)
    print("娴嬭瘯: 鎸佷粨鍚堝苟閫昏緫")
    print("=" * 60)
    
    executor = MockOKXExecutor()
    
    # 鍒涘缓娴嬭瘯鏁版嵁
    now = datetime.now()
    api_positions = [
        Position(symbol="BTC-USDT", size=0.0, avg_price=0, entry_time=now),  # API杩斿洖闆?
    ]
    local_positions = [
        Position(symbol="BTC-USDT", size=0.001, avg_price=50000, entry_time=now),
    ]
    
    print("\n[鍦烘櫙1] API杩斿洖闆讹紝鏈湴鏈夋寔浠?)
    result = executor._merge_positions(api_positions, local_positions)
    print(f"  鍚堝苟缁撴灉鏁伴噺: {len(result)}")
    print(f"  鎸佷粨size: {result[0].size if result else 'N/A'}")
    
    assert len(result) == 1, "搴旇繑鍥炴湰鍦版寔浠?
    assert abs(result[0].size - 0.001) < 1e-9, "搴斾娇鐢ㄦ湰鍦版寔浠撴暟鎹?
    print("  [PASS] 鍚堝苟閫昏緫姝ｇ‘锛堜娇鐢ㄦ湰鍦版暟鎹級")
    
    # 鍦烘櫙2锛欰PI鏈夋湁鏁堟暟鎹紝浼樺厛浣跨敤API
    api_positions2 = [
        Position(symbol="BTC-USDT", size=0.002, avg_price=51000, entry_time=now),
    ]
    local_positions2 = [
        Position(symbol="BTC-USDT", size=0.001, avg_price=50000, entry_time=now),
    ]
    
    print("\n[鍦烘櫙2] API鏈夋湁鏁堟暟鎹紝浼樺厛浣跨敤API")
    result2 = executor._merge_positions(api_positions2, local_positions2)
    print(f"  鍚堝苟缁撴灉鏁伴噺: {len(result2)}")
    print(f"  鎸佷粨size: {result2[0].size if result2 else 'N/A'}")
    
    assert len(result2) == 1, "搴旇繑鍥炴寔浠?
    assert abs(result2[0].size - 0.002) < 1e-9, "搴斾紭鍏堜娇鐢ˋPI鏁版嵁"
    print("  [PASS] 鍚堝苟閫昏緫姝ｇ‘锛堜紭鍏堜娇鐢ˋPI鏁版嵁锛?)
    
    print("\n" + "=" * 60)
    print("[PASS] 鍚堝苟閫昏緫娴嬭瘯閫氳繃!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    try:
        test_local_position_tracking()
        test_merge_logic()
        print("\n[SUCCESS] 鎵€鏈夋祴璇曢€氳繃!")
    except AssertionError as e:
        print(f"\n[FAIL] 娴嬭瘯澶辫触: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] 娴嬭瘯寮傚父: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
