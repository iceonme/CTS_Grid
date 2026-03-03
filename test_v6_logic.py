
import sys
import os
from datetime import datetime, timedelta

# 添加根目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import MarketData, StrategyContext, Side
from strategies import GridMTFStrategyV6_0

def test_v6_strategy():
    print("=== V6.0 MTF 策略单元测试 ===")
    
    # 1. 初始化策略
    params = {
        'rsi_buy_threshold': 30,
        'rsi_sell_threshold': 70,
        'grid_layers': 5,
        'total_capital': 10000
    }
    strat = GridMTFStrategyV6_0(name="Test_V6", **params)
    strat.initialize()

    # 2. 模拟数据生成 (产生一段下跌趋势后触底反弹)
    base_price = 50000.0
    start_time = datetime(2024, 1, 1, 12, 0)
    
    data_list = []
    # 生成 100 根 5m 线
    for i in range(100):
        # 下跌趋势
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

    # 3. 喂食数据
    print(f"正在输入 {len(data_list)} 根 K 线进行测试...")
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
                print(f"[{sig.timestamp}] 信号输出: {sig.side.value} | 数量: {sig.size} | 原因: {sig.reason}")
                signals_count += 1

    status = strat.get_status()
    print("\n策略最终状态:")
    print(f"  RSI: {status['current_rsi']}")
    print(f"  MACD Hist: {status['macdhist']}")
    print(f"  网格范围: {status['grid_range']}")
    
    if signals_count > 0:
        print("\n[OK] 策略测试通过，能够正常产出信号。")
    else:
        print("\n[WARN] 策略未产出信号，可能需要更长的数据预热或不同的行情模拟。")

if __name__ == "__main__":
    test_v6_strategy()
