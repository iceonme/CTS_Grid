import numpy as np
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from core import MarketData, Signal, Side, StrategyContext, FillEvent
from strategies.base import BaseStrategy
from strategies.grid_jeff_6_5 import GridJeff65Strategy, JeffIndicators, StrategyState

class GridZen65Strategy(GridJeff65Strategy):
    """
    Zen 6.5 策略：
    1. 继承 Jeff 6.5A 逻辑 (RSI 触发, MACD 仓位流)
    2. 固定本金: 仓位始终基于初始 10000 计算，不复利。
    3. 全仓止损: 当全仓盈亏低于 -2.5% 时，清仓离场。
    """
    def __init__(self, name="Grid_Zen_65", **params):
        # 强制设置 min_profit_filter 为 True，符合 Zen 的“盈利提取”逻辑（必须盈利才出）
        params['min_profit_filter'] = True
        super().__init__(name, **params)
        
        self.stop_loss_threshold = params.get('stop_loss_threshold', -0.10) # 修正为 -10%
        self.fixed_capital = params.get('fixed_capital', 10000.0)
        self.layer_value = self.fixed_capital / self.grid_layers
        
        self._prev_rsi = 50.0
        self._prev_hist = 0.0
        
    def on_data(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        # 首先更新指标
        rsi, macd, macdsig, hist = self.indicators.update(data.close)
        
        # 记录前值以便判断“钩头”和“转弱”
        prev_rsi = self._prev_rsi
        prev_hist = self._prev_hist
        self._prev_rsi = rsi
        self._prev_hist = hist
        
        # 更新状态
        self.state.current_rsi = rsi
        self.state.macd = macd
        self.state.macdsignal = macdsig
        self.state.macdhist = hist

        # 止损检查
        pos = context.positions.get(data.symbol)
        if pos and pos.size > 0:
            if self.state.entry_prices:
                cost_basis = sum(self.state.entry_prices) / len(self.state.entry_prices)
                pnl_pct = (data.close / cost_basis) - 1
                
                if pnl_pct <= self.stop_loss_threshold:
                    self.log(f"[{data.timestamp}] STOP LOSS triggered! Price: {data.close:.2f} | Cost: {cost_basis:.2f} | PnL: {pnl_pct*100:.2f}%")
                    self.state.cooldown_until = data.timestamp + timedelta(minutes=self.cooldown_min * 2)
                    return [Signal(
                        timestamp=data.timestamp,
                        symbol=data.symbol,
                        side=Side.SELL,
                        size=pos.size,
                        meta={'layers': len(self.state.entry_prices), 'type': 'STOP_LOSS'},
                        reason=f"STOP LOSS triggered: {pnl_pct*100:.2f}%"
                    )]

        # 走常规逻辑前的状态更新逻辑复用自基类，但我们需要稍微修改卖点判断
        if self.indicators.count < 30:
            return []
        if self.state.cooldown_until and data.timestamp < self.state.cooldown_until:
            return []

        # 状态机：MACD 状态判断 (逻辑保持同原策略)
        curr_sig = macdsig
        prev_macd = self.state.macd # 上次保存在状态里的
        prev_sig = self.state.macdsignal
        
        status = '中性'
        if macd > curr_sig and prev_macd <= prev_sig: status = '金叉'
        elif macd < curr_sig and prev_macd >= prev_sig: status = '死叉'
        elif macd > curr_sig: status = '多头'
        else: status = '空头'
        self.state.macd_status = status

        signals = []
        layers = len(self.state.entry_prices)
        pos_size = pos.size if pos else 0
        cash = context.cash
        
        # 买入逻辑 (保持原样: RSI 低吸)
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
                    timestamp=data.timestamp, symbol=data.symbol, side=Side.BUY,
                    size=buy_usdt, meta={'size_in_quote': True, 'layers': buy_layers, 'type': sig_type},
                    reason=f"{sig_type} Buy: RSI={rsi:.1f}"
                ))
                self.state.cooldown_until = data.timestamp + timedelta(minutes=self.cooldown_min)

        # 卖出逻辑 (优化卖点)
        elif layers > 0 and pos_size > 0:
            sell_layers = 0
            sig_type = 'SILVER'
            
            # 原有强力卖点
            if rsi > self.rsi_sell_gold and status == '死叉':
                sell_layers = min(2, layers)
                sig_type = 'GOLD'
            elif rsi > self.rsi_sell_silver:
                sell_layers = 1
                sig_type = 'SILVER'
            # 优化加餐：动量减弱卖点
            elif rsi > 60 and rsi < prev_rsi and hist < prev_hist and hist > 0:
                # RSI 钩头向下 且 MACD 红柱缩短 且 处于超买区边缘
                sell_layers = 1
                sig_type = 'MOMENTUM_EXIT'
                
            if sell_layers > 0:
                # 盈利校验
                cost_sum = sum(self.state.entry_prices[:sell_layers])
                avg_cost = cost_sum / (sell_layers * (self.layer_value / cost_basis)) if layers > 0 else 0 # 简化估算
                # 重新精确计算
                sell_btc_est = 0
                cost_sum_exact = 0
                for i in range(sell_layers):
                    if i < len(self.state.entry_prices):
                        c = self.state.entry_prices[i]
                        sell_btc_est += self.layer_value / c
                        cost_sum_exact += self.layer_value
                
                exact_avg_cost = cost_sum_exact / sell_btc_est if sell_btc_est > 0 else 999999
                
                if data.close > exact_avg_cost * (1 + self.min_profit_ratio):
                    # 只有盈利才出 (Zen的核心盈利保护)
                    if sell_layers >= layers or (pos_size - sell_btc_est) * data.close < 10:
                        sell_btc_est = pos_size
                    
                    signals.append(Signal(
                        timestamp=data.timestamp, symbol=data.symbol, side=Side.SELL,
                        size=sell_btc_est, meta={'layers': sell_layers, 'type': sig_type},
                        reason=f"{sig_type} Exit: RSI={rsi:.1f} Momentum Weakening"
                    ))
                    self.state.cooldown_until = data.timestamp + timedelta(minutes=self.cooldown_min)

        return signals

    def on_fill(self, fill: FillEvent):
        # 覆写 on_fill 以便在止损平仓时打印特殊日志
        sig_type = fill.meta.get('type', 'SILVER')
        if fill.side == Side.SELL and sig_type == 'STOP_LOSS':
            popped_costs = []
            while self.state.entry_prices:
                popped_costs.append(self.state.entry_prices.pop(0))
            
            avg_pop = sum(popped_costs)/len(popped_costs) if popped_costs else 0
            pnl_pct = (fill.filled_price - avg_pop) / avg_pop * 100 if avg_pop else 0
            self.state.stats['total_trades'] += 1
            self.log(f"[{fill.timestamp}] ❌ 止损完成 | 价格: {fill.filled_price:.2f} | 盈亏: {pnl_pct:+.2f}% | 数量: {fill.filled_size:.4f}")
        else:
            super().on_fill(fill)
