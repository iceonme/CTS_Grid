import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from engines.backtest import BacktestEngine
from datafeeds.csv_feed import CSVDataFeed
from executors.paper import PaperExecutor
from strategies.grid_6_5_zen import GridZen65Strategy

class SimpleLogger:
    def info(self, msg): print(msg)
    def warning(self, msg): print(f"[WARN] {msg}")
    def error(self, msg): print(f"[ERR] {msg}")
    def debug(self, msg): pass

csv_path = 'data/btc_1m_2025.csv'

strategy = GridZen65Strategy(
    name="Zen_Debug", 
    symbol="BTCUSDT",
    grid_layers=5,
    stop_loss_threshold=-0.025
)
strategy.set_logger(SimpleLogger())

executor = PaperExecutor(initial_capital=10000.0, fast_mode=True)
feed = CSVDataFeed(filepath=csv_path, symbol="BTCUSDT")
engine = BacktestEngine(strategy=strategy, executor=executor)

print("开始 Zen 策略 Debug 回测...")
report = engine.run(feed, fast_mode=True)
print(f"总盈亏:  {report['total_return']}")
print(f"总交易数:  {report['total_trades']}")
