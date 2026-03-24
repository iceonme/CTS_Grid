"""
多交易所本地模拟盘系统
支持：币安、OKX、Bybit等
"""

import pandas as pd
import numpy as np
import time
import json
from datetime import datetime, timedelta
from collections import deque
import warnings
warnings.filterwarnings('ignore')


class MultiExchangePaperTrading:
    """多交易所本地模拟盘系统"""
    
    def __init__(self, initial_capital=10000, base_currency='USDT', 
                 fee_rate=0.001, slippage_model='adaptive'):
        self.initial_capital = initial_capital
        self.base_currency = base_currency
        self.fee_rate = fee_rate
        self.slippage_model = slippage_model
        
        # 账户状态
        self.cash = initial_capital
        self.positions = {}
        self.total_value_history = []
        self.trades = []
        self.signals = []
        
        # 模拟参数
        self.latency_ms = 200
        self.slippage_base = 0.0005
        
        # 策略嵌入
        self.strategy = None
        self.is_running = False
        self.current_timestamp = None
        
    def set_strategy(self, strategy_class, **strategy_params):
        """设置交易策略"""
        self.strategy = strategy_class(**strategy_params)
        print(f"策略已设置: {strategy_class.__name__}")
        
    def set_latency(self, latency_ms):
        """设置网络延迟"""
        self.latency_ms = latency_ms
        print(f"网络延迟设置为: {latency_ms}ms")
        
    def set_slippage_model(self, model, base_slippage=0.0005):
        """设置滑点模型"""
        self.slippage_model = model
        self.slippage_base = base_slippage
        print(f"滑点模型: {model}, 基础滑点: {base_slippage*100}%")
        
    def calculate_slippage(self, symbol, side, amount, price, orderbook=None):
        """计算实际成交滑点"""
        if self.slippage_model == 'none':
            return 0
        
        if self.slippage_model == 'fixed':
            return self.slippage_base
        
        # 自适应模型
        if orderbook is None:
            depth_factor = 1.0
        else:
            depth_factor = self._calculate_depth_impact(orderbook, amount, price)
        
        slippage = self.slippage_base * depth_factor * (1 + np.random.normal(0, 0.3))
        slippage = max(0.0001, min(0.005, slippage))
        return slippage
    
    def _calculate_depth_impact(self, orderbook, amount, price):
        """计算订单簿深度对滑点的影响"""
        simulated_depth = price * 100
        impact = amount / simulated_depth
        return 1 + impact * 10
    
    def simulate_latency(self):
        """模拟网络延迟"""
        if self.latency_ms > 0:
            actual_latency = self.latency_ms * (0.8 + np.random.random() * 0.4)
            time.sleep(actual_latency / 1000)
    
    def execute_order(self, symbol, side, amount, price, timestamp, orderbook=None):
        """执行模拟订单"""
        self.simulate_latency()
        
        slippage = self.calculate_slippage(symbol, side, amount, price, orderbook)
        
        if side == 'BUY':
            executed_price = price * (1 + slippage)
        else:
            executed_price = price * (1 - slippage)
        
        trade_value = amount * executed_price
        fee = trade_value * self.fee_rate
        
        if side == 'BUY':
            total_cost = trade_value + fee
            if total_cost > self.cash:
                print(f"[警告] 资金不足: 需要${total_cost:.2f}, 可用${self.cash:.2f}")
                return None
            
            self.cash -= total_cost
            
            if symbol not in self.positions:
                self.positions[symbol] = {'amount': 0, 'avg_price': 0}
            
            pos = self.positions[symbol]
            total_amount = pos['amount'] + amount
            pos['avg_price'] = (pos['amount'] * pos['avg_price'] + amount * executed_price) / total_amount
            pos['amount'] = total_amount
            
        else:
            if symbol not in self.positions or self.positions[symbol]['amount'] < amount:
                print(f"[警告] 持仓不足: 需要{amount}, 可用{self.positions.get(symbol, {}).get('amount', 0)}")
                return None
            
            self.cash += (trade_value - fee)
            self.positions[symbol]['amount'] -= amount
            
            if self.positions[symbol]['amount'] <= 0:
                del self.positions[symbol]
        
        trade_record = {
            'timestamp': timestamp,
            'symbol': symbol,
            'side': side,
            'amount': amount,
            'theoretical_price': price,
            'executed_price': executed_price,
            'slippage': slippage,
            'fee': fee,
            'total_value': self.get_total_value(price),
            'cash': self.cash,
            'position': self.positions.get(symbol, {'amount': 0, 'avg_price': 0})
        }
        self.trades.append(trade_record)
        
        print(f"[成交] {side} {amount:.6f} {symbol} @ ${executed_price:.2f} "
              f"(滑点: {slippage*100:.3f}%, 手续费: ${fee:.2f})")
        
        return trade_record
    
    def get_total_value(self, current_price):
        """计算当前总资产价值"""
        position_value = sum(
            pos['amount'] * current_price 
            for symbol, pos in self.positions.items()
        )
        return self.cash + position_value
    
    def run_simulation(self, data_feed, symbol='BTC/USDT', verbose=True):
        """运行模拟盘"""
        self.is_running = True
        print(f"\n{'='*60}")
        print(f"模拟盘启动 | 初始资金: ${self.initial_capital:.2f} {self.base_currency}")
        print(f"滑点模型: {self.slippage_model} | 延迟: {self.latency_ms}ms")
        print(f"{'='*60}\n")
        
        for i, tick in enumerate(data_feed):
            if not self.is_running:
                break
            
            if isinstance(tick, pd.Series):
                timestamp = tick.name
                open_p = tick['open']
                high = tick['high']
                low = tick['low']
                close = tick['close']
                volume = tick.get('volume', 0)
            else:
                timestamp = tick['timestamp']
                open_p = tick['open']
                high = tick['high']
                low = tick['low']
                close = tick['close']
                volume = tick.get('volume', 0)
            
            self.current_timestamp = timestamp
            
            if self.strategy:
                signal = self.strategy.generate_signal(
                    open_p, high, low, close, volume, timestamp
                )
                
                if signal:
                    self.signals.append({
                        'timestamp': timestamp,
                        'signal': signal,
                        'price': close
                    })
                    
                    if signal['action'] in ['BUY', 'SELL']:
                        self.execute_order(
                            symbol=symbol,
                            side=signal['action'],
                            amount=signal.get('amount', 0),
                            price=close,
                            timestamp=timestamp
                        )
            
            total_value = self.get_total_value(close)
            self.total_value_history.append({
                'timestamp': timestamp,
                'total_value': total_value,
                'cash': self.cash,
                'position_value': total_value - self.cash,
                'price': close
            })
            
            if verbose and i % 100 == 0:
                print(f"[{timestamp}] 价格: ${close:.2f} | "
                      f"总资产: ${total_value:.2f} | "
                      f"持仓: {self.positions.get(symbol, {}).get('amount', 0):.6f}")
        
        self.is_running = False
        return self.generate_report()
    
    def generate_report(self):
        """生成模拟盘报告"""
        if not self.total_value_history:
            return "无交易记录"
        
        df = pd.DataFrame(self.total_value_history)
        final_value = df['total_value'].iloc[-1]
        total_return = (final_value - self.initial_capital) / self.initial_capital
        
        df['peak'] = df['total_value'].cummax()
        df['drawdown'] = (df['peak'] - df['total_value']) / df['peak']
        max_dd = df['drawdown'].max()
        
        returns = df['total_value'].pct_change().dropna()
        sharpe = returns.mean() / returns.std() * np.sqrt(252*24*60) if len(returns) > 1 else 0
        
        report = {
            'initial_capital': self.initial_capital,
            'final_value': final_value,
            'total_return': total_return,
            'max_drawdown': max_dd,
            'sharpe_ratio': sharpe,
            'total_trades': len(self.trades),
            'cash_remaining': self.cash,
            'positions': self.positions,
            'trades': self.trades
        }
        
        print(f"\n{'='*60}")
        print("模拟盘报告")
        print(f"{'='*60}")
        print(f"初始资金:     ${self.initial_capital:>12,.2f}")
        print(f"最终资产:     ${final_value:>12,.2f}")
        print(f"总收益率:     {total_return*100:>11.2f}%")
        print(f"最大回撤:     {max_dd*100:>11.2f}%")
        print(f"夏普比率:     {sharpe:>12.2f}")
        print(f"交易次数:     {len(self.trades):>12}")
        print(f"剩余现金:     ${self.cash:>12,.2f}")
        print(f"当前持仓:     {self.positions}")
        print(f"{'='*60}\n")
        
        return report
    
    def stop(self):
        """停止模拟"""
        self.is_running = False
        print("模拟盘已停止")
    
    def reset(self):
        """重置模拟盘"""
        self.cash = self.initial_capital
        self.positions = {}
        self.total_value_history = []
        self.trades = []
        self.signals = []
        self.is_running = False
        print("模拟盘已重置")


class DataFeed:
    """数据接入模块"""
    
    @staticmethod
    def from_dataframe(df, symbol='BTC/USDT'):
        """从DataFrame创建数据流"""
        for timestamp, row in df.iterrows():
            yield {
                'timestamp': timestamp,
                'symbol': symbol,
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row.get('volume', 0)
            }
    
    @staticmethod
    def from_exchange(exchange_name='binance', symbol='BTC/USDT', 
                      timeframe='1m', limit=1000):
        """从交易所获取实时数据"""
        try:
            import ccxt
            
            exchange_class = getattr(ccxt, exchange_name)
            exchange = exchange_class({'enableRateLimit': True})
            
            print(f"连接到 {exchange_name}...")
            
            while True:
                try:
                    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                    
                    for candle in ohlcv:
                        yield {
                            'timestamp': pd.to_datetime(candle[0], unit='ms'),
                            'symbol': symbol,
                            'open': candle[1],
                            'high': candle[2],
                            'low': candle[3],
                            'close': candle[4],
                            'volume': candle[5]
                        }
                    
                    time.sleep(exchange.rateLimit / 1000)
                    
                except Exception as e:
                    print(f"获取数据错误: {e}")
                    time.sleep(5)
                    
        except ImportError:
            print("请先安装ccxt: pip install ccxt")
            return None
    
    @staticmethod
    def simulate_realtime(df, speed=1.0):
        """模拟实时数据流"""
        for i in range(len(df)):
            row = df.iloc[i]
            timestamp = df.index[i]
            
            yield {
                'timestamp': timestamp,
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row.get('volume', 0)
            }
            
            if speed > 0:
                time.sleep(60 / speed)
