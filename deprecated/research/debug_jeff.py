import sys
import os
import builtins
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from engines.backtest import BacktestEngine
from datafeeds.csv_feed import CSVDataFeed
from executors.paper import PaperExecutor
from strategies.grid_jeff_6_5 import GridJeff65Strategy

class SimpleLogger:
    def info(self, msg): print(msg)
    def warning(self, msg): print(f"[WARN] {msg}")
    def error(self, msg): print(f"[ERR] {msg}")
    def debug(self, msg): pass

csv_path = 'data/btc_1m_2025.csv'

strategy = GridJeff65Strategy(
    name="Jeff_Debug", 
    symbol="BTCUSDT",
    min_profit_filter=True,
    min_profit_ratio=0.005 # 要求 0.5% 利润
)
strategy.set_logger(SimpleLogger())

executor = PaperExecutor(initial_capital=10000.0, fast_mode=True)
feed = CSVDataFeed(filepath=csv_path, symbol="BTCUSDT")

engine = BacktestEngine(strategy=strategy, executor=executor)

import builtins

class Logger:
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, "w", encoding='utf-8')

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()

sys.stdout = Logger("debug_trades.txt")

print("开始带日志的回测...")
report = engine.run(feed, fast_mode=True)

print("总盈亏: ", report['total_return'])
print("总交易数: ", report['total_trades'])

sys.stdout = sys.stdout.terminal
