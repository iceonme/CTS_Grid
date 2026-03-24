
import sys
import os
from datetime import datetime, timedelta

# 娣诲姞鏍圭洰褰?
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from console.core import MarketData, StrategyContext, Side
from cartridges.strategies import GridMTFStrategyV6_0

def test_v6_strategy():
    print("=== V6.0 MTF 绛栫暐鍗曞厓娴嬭瘯 ===")
    
    # 1. 鍒濆鍖栫瓥鐣?
    params = {
        'rsi_buy_threshold': 30,
        'rsi_sell_threshold': 70,
        'grid_layers': 5,
        'total_capital': 10000
    }
    strat = GridMTFStrategyV6_0(name="Test_V6", **params)
    strat.initialize()

    # 2. 妯℃嫙鏁版嵁鐢熸垚 (浜х敓涓€娈典笅璺岃秼鍔垮悗瑙﹀簳鍙嶅脊)
    base_price = 50000.0
    start_time = datetime(2024, 1, 1, 12, 0)
    
    data_list = []
    # 鐢熸垚 100 鏍?5m 绾?
    for i in range(100):
        # 涓嬭穼瓒嬪娍
        price = base_price - i * 10
        data = MarketData(
            timestamp=start_time + timedelta(minutes=i*5),
            symbol="BTC-USDT-SWAP",
            open=price + 5,
            high=price + 10,
            low=price - 10,
            close=price,
            volume=1.0
        )
        data_list.append(data)

    # 3. 鍠傞鏁版嵁
    print(f"姝ｅ湪杈撳叆 {len(data_list)} 鏍?K 绾胯繘琛屾祴璇?..")
    signals_count = 0
    for data in data_list:
        context = StrategyContext(
            timestamp=data.timestamp,
            cash=10000.0,
            positions={},
            current_prices={data.symbol: data.close}
        )
        signals = strat.on_data(data, context)
        if signals:
            for sig in signals:
                print(f"[{sig.timestamp}] 淇″彿杈撳嚭: {sig.side.value} | 鏁伴噺: {sig.size} | 鍘熷洜: {sig.reason}")
                signals_count += 1

    status = strat.get_status()
    print("\n绛栫暐鏈€缁堢姸鎬?")
    print(f"  RSI: {status['current_rsi']}")
    print(f"  MACD Hist: {status['macdhist']}")
    print(f"  缃戞牸鑼冨洿: {status['grid_range']}")
    
    if signals_count > 0:
        print("\n[OK] 绛栫暐娴嬭瘯閫氳繃锛岃兘澶熸甯镐骇鍑轰俊鍙枫€?)
    else:
        print("\n[WARN] 绛栫暐鏈骇鍑轰俊鍙凤紝鍙兘闇€瑕佹洿闀跨殑鏁版嵁棰勭儹鎴栦笉鍚岀殑琛屾儏妯℃嫙銆?)

if __name__ == "__main__":
    test_v6_strategy()
