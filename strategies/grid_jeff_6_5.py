import numpy as np
import pandas as pd
from collections import deque
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from core import MarketData, Signal, Side, StrategyContext, FillEvent
from strategies.base import BaseStrategy

class JeffIndicators:
    # 1分钟增量计算 RSI 和 MACD
    def __init__(self, rsi_period=14, macd_fast=12, macd_slow=26, macd_sig=9):
        self.rsi_period = rsi_period
        
        self.gain_dq = deque(maxlen=rsi_period)
        self.loss_dq = deque(maxlen=rsi_period)
        self.gain_sum = 0.0
        self.loss_sum = 0.0
        self.prev_close = 0.0
        self.count = 0
        
        self.alpha_f = 2.0 / (macd_fast + 1)
        self.alpha_s = 2.0 / (macd_slow + 1)
        self.alpha_sig = 2.0 / (macd_sig + 1)
        
        self.ema_f = 0.0
        self.ema_s = 0.0
        self.ema_sig = 0.0
        
    def update(self, close: float) -> tuple:
        if self.count == 0:
            self.prev_close = close
            self.ema_f = self.ema_s = self.ema_sig = close
            self.count += 1
            return 50.0, 0.0, 0.0, 0.0
            
        # RSI (SMA style for simple smoothing typically used in basic grid algos or standard Wilders depending on engine. We use SMA here to match Jeff docs if not specified, or Wilder's)
        diff = close - self.prev_close
        gain = max(diff, 0)
        loss = max(-diff, 0)
        
        count = len(self.gain_dq)
        if count == self.rsi_period:
            self.gain_sum -= self.gain_dq[0]
            self.loss_sum -= self.loss_dq[0]
            
        self.gain_dq.append(gain)
        self.gain_sum += gain
        self.loss_dq.append(loss)
        self.loss_sum += loss
        
        p = self.rsi_period
        avg_gain = self.gain_sum / (count + 1 if count + 1 < p else p)
        avg_loss = self.loss_sum / (count + 1 if count + 1 < p else p)
        
        rs = avg_gain / avg_loss if avg_loss > 1e-9 else 100.0
        rsi = 100.0 - (100.0 / (1.0 + rs)) if avg_loss > 1e-9 else 100.0
        
        self.prev_close = close
        
        # MACD
        self.ema_f = close * self.alpha_f + self.ema_f * (1 - self.alpha_f)
        self.ema_s = close * self.alpha_s + self.ema_s * (1 - self.alpha_s)
        macd = self.ema_f - self.ema_s
        self.ema_sig = macd * self.alpha_sig + self.ema_sig * (1 - self.alpha_sig)
        hist = macd - self.ema_sig
        
        self.count += 1
        return rsi, macd, self.ema_sig, hist

class StrategyState:
    def __init__(self):
        self.entry_prices = []
        self.cooldown_until = None
        self.current_rsi = 50.0
        self.macd = 0.0
        self.macdsignal = 0.0
        self.macdhist = 0.0
        self.macd_status = '中性'
        self.macd_status_prev = '中性'
        self.stats = {
            'gold_buy': 0, 'silver_buy': 0,
            'gold_sell': 0, 'silver_sell': 0,
            'total_trades': 0
        }

class GridJeff65Strategy(BaseStrategy):
    def __init__(self, name="Grid_Jeff_65A", **params):
        super().__init__(name, **params)
        self.indicators = JeffIndicators()
        self.state = StrategyState()
        
        # 参数
        self.symbol = params.get('symbol', 'BTCUSDT')
        self.capital = params.get('capital', 10000)
        self.grid_layers = params.get('grid_layers', 5)
        self.layer_value = self.capital / self.grid_layers
        
        self.rsi_buy = params.get('rsi_buy_threshold', 30)
        self.rsi_sell_silver = params.get('rsi_sell_silver', 65)
        self.rsi_sell_gold = params.get('rsi_sell_gold', 70)
        self.cooldown_min = params.get('cooldown_min', 15)
        self.min_profit_filter = params.get('min_profit_filter', False)
        self.min_profit_ratio = params.get('min_profit_ratio', 0.005) # 0.5%
        
        self.last_ts = None
        self._prev_macd = 0.0
        self._prev_sig = 0.0
        
    def initialize(self):
        super().initialize()
        self.indicators = JeffIndicators()
        self.state = StrategyState()

    def on_data(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        is_new_bar = (not self.last_ts) or (data.timestamp > self.last_ts)
        if not is_new_bar:
            return []
            
        self.last_ts = data.timestamp
        
        rsi, macd, macdsig, hist = self.indicators.update(data.close)
        
        self.state.current_rsi = rsi
        self.state.macd = macd
        self.state.macdsignal = macdsig
        self.state.macdhist = hist
        
        # MACD状态
        curr, prev = macd, self._prev_macd
        sig_curr, sig_prev = macdsig, self._prev_sig
        
        status = '中性'
        if curr > sig_curr and prev <= sig_prev:
            status = '金叉'
        elif curr < sig_curr and prev >= sig_prev:
            status = '死叉'
        elif curr > sig_curr:
            status = '多头'
        else:
            status = '空头'
            
        self._prev_macd = curr
        self._prev_sig = sig_curr
            
        self.state.macd_status_prev = self.state.macd_status
        self.state.macd_status = status
        
        if self.indicators.count < 30:
            return []
            
        if self.state.cooldown_until and data.timestamp < self.state.cooldown_until:
            return []
            
        signals = []
        layers = len(self.state.entry_prices)
        
        pos = context.positions.get(data.symbol)
        pos_size = pos.size if pos else 0
        cash = context.cash
        
        # 买入
        if rsi < self.rsi_buy and layers < self.grid_layers and cash > self.layer_value:
            if status == '金叉':
                buy_layers = min(2, self.grid_layers - layers)
                sig_type = 'GOLD'
            else:
                buy_layers = 1
                sig_type = 'SILVER'
                
            buy_usdt = buy_layers * self.layer_value
            if cash >= buy_usdt:
                signals.append(Signal(
                    timestamp=data.timestamp,
                    symbol=data.symbol,
                    side=Side.BUY,
                    size=buy_usdt,
                    meta={'size_in_quote': True, 'layers': buy_layers, 'type': sig_type},
                    reason=f"{sig_type} Buy: RSI={rsi:.1f} MACD={status}"
                ))
                self.state.cooldown_until = data.timestamp + timedelta(minutes=self.cooldown_min)
                
        # 卖出
        elif layers > 0 and pos_size > 0:
            if rsi > self.rsi_sell_gold and status == '死叉':
                sell_layers = min(2, layers)
                sig_type = 'GOLD'
            elif rsi > self.rsi_sell_silver:
                sell_layers = 1
                sig_type = 'SILVER'
            else:
                sell_layers = 0
                
            if sell_layers > 0:
                sell_btc = 0
                avg_cost = 0
                cost_sum = 0
                for i in range(sell_layers):
                    if i < len(self.state.entry_prices):
                        cost = self.state.entry_prices[i]
                        sell_btc += self.layer_value / cost
                        cost_sum += cost * (self.layer_value / cost)
                
                if sell_btc > 0:
                    avg_cost = cost_sum / sell_btc
                    # 盈利校验过滤器
                    if self.min_profit_filter and data.close <= avg_cost * (1 + self.min_profit_ratio):
                        # 如果开启了只盈不亏，并且当前价格比这批卖出层的成本价还低，则放弃本次卖出信号
                        sell_btc = 0
                        sell_layers = 0
                
                # 如果是最后一层，全平仓防止粉尘
                if sell_layers >= layers or (pos_size - sell_btc) * data.close < 10:
                    sell_btc = pos_size
                
                if sell_btc > 0:
                    signals.append(Signal(
                        timestamp=data.timestamp,
                        symbol=data.symbol,
                        side=Side.SELL,
                        size=sell_btc,
                        meta={'layers': sell_layers, 'type': sig_type},
                        reason=f"{sig_type} Sell: RSI={rsi:.1f} MACD={status}"
                    ))
                    self.state.cooldown_until = data.timestamp + timedelta(minutes=self.cooldown_min)
                    
        return signals

    def on_fill(self, fill: FillEvent):
        # When signal is executed
        # If signal meta is lost, estimate layers
        layers_filled = fill.meta.get('layers', None)
        sig_type = fill.meta.get('type', 'SILVER')
        
        if fill.side == Side.BUY:
            if layers_filled is None:
                layers_filled = max(1, round((fill.filled_size * fill.filled_price) / self.layer_value))
            for _ in range(int(layers_filled)):
                self.state.entry_prices.append(fill.filled_price)
            if sig_type == 'GOLD': self.state.stats['gold_buy'] += 1
            else: self.state.stats['silver_buy'] += 1
            self.state.stats['total_trades'] += 1
            self.log(f"[{fill.timestamp}] 开仓 {sig_type} | 价格: {fill.filled_price:.2f} | 数量: {fill.filled_size:.4f} | 当前层数: {len(self.state.entry_prices)}")
            
        elif fill.side == Side.SELL:
            if layers_filled is None:
                layers_filled = max(1, round((fill.filled_size * fill.filled_price) / self.layer_value))
            popped_costs = []
            for _ in range(min(int(layers_filled), len(self.state.entry_prices))):
                if self.state.entry_prices:
                    popped_costs.append(self.state.entry_prices.pop(0))
            if sig_type == 'GOLD': self.state.stats['gold_sell'] += 1
            else: self.state.stats['silver_sell'] += 1
            self.state.stats['total_trades'] += 1
            
            avg_pop = sum(popped_costs)/len(popped_costs) if popped_costs else 0
            pnl_pct = (fill.filled_price - avg_pop) / avg_pop * 100 if avg_pop else 0
            self.log(f"[{fill.timestamp}] 平仓 {sig_type} | 价格: {fill.filled_price:.2f} | 成本: {avg_pop:.2f} | 盈亏: {pnl_pct:+.2f}% | 数量: {fill.filled_size:.4f} | 当前层数: {len(self.state.entry_prices)}")

    def get_status(self, context=None) -> Dict[str, Any]:
        return {
            'name': self.name,
            'current_rsi': round(self.state.current_rsi, 2),
            'macd': round(self.state.macd, 4),
            'macd_status': self.state.macd_status,
            'layers': len(self.state.entry_prices),
            'stats': self.state.stats
        }
