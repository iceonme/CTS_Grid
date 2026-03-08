import numpy as np
from collections import deque
from datetime import datetime, timedelta
from typing import List, Dict, Any

from core import MarketData, Signal, Side, StrategyContext, FillEvent
from strategies.base import BaseStrategy

class Z71Indicators:
    def __init__(self, resample_min=60, boll_period=20, boll_std=2, macd_fast=12, macd_slow=26, macd_sig=9, rsi_period=14, vol_ma_period=5):
        self.resample_min = resample_min
        
        # Indicator params
        self.boll_period = boll_period
        self.boll_std = boll_std
        self.rsi_period = rsi_period
        self.vol_ma_period = vol_ma_period
        
        # MACD EMA alphas
        self.alpha_f = 2.0 / (macd_fast + 1)
        self.alpha_s = 2.0 / (macd_slow + 1)
        self.alpha_sig = 2.0 / (macd_sig + 1)
        
        # Data storage for resampling
        self.current_bar_open = 0.0
        self.current_bar_high = 0.0
        self.current_bar_low = float('inf')
        self.current_bar_close = 0.0
        self.current_bar_volume = 0.0
        self.bar_count = 0
        
        # Historical Data (Resampled)
        self.closes = deque(maxlen=max(boll_period, 50))
        self.volumes = deque(maxlen=max(vol_ma_period, 50))
        
        # RSI state
        self.gain_sum = 0.0
        self.loss_sum = 0.0
        self.gain_dq = deque(maxlen=rsi_period)
        self.loss_dq = deque(maxlen=rsi_period)
        
        # MACD state
        self.ema_f = 0.0
        self.ema_s = 0.0
        self.ema_sig = 0.0
        
        # BOLL state
        self.bbw_history = deque(maxlen=20) # for MA(BBW, 20)
        
        # Current finalized indicator values
        self.rsi = 50.0
        self.prev_rsi = 50.0
        self.macd = 0.0
        self.macd_sig = 0.0
        self.macd_hist = 0.0
        self.boll_mid = 0.0
        self.boll_up = 0.0
        self.boll_down = 0.0
        self.bbw = 0.0
        self.bbw_ma20 = 0.0
        self.volume_ma5 = 0.0
        
        self.is_ready = False

    def update(self, data: MarketData, is_new_minute: bool) -> bool:
        """
        Updates the indicator. Returns True if a new resampled bar was just finalized.
        """
        if self.bar_count == 0:
            self.current_bar_open = data.open
            self.current_bar_high = data.high
            self.current_bar_low = data.low
            self.current_bar_close = data.close
            self.current_bar_volume = data.volume
        else:
            self.current_bar_high = max(self.current_bar_high, data.high)
            self.current_bar_low = min(self.current_bar_low, data.low)
            self.current_bar_close = data.close
            self.current_bar_volume += data.volume
            
        self.bar_count += 1
        
        # Finalize bar
        if self.bar_count >= self.resample_min:
            self._finalize_bar(self.current_bar_close, self.current_bar_volume)
            self.bar_count = 0
            return True
        return False

    def _finalize_bar(self, close: float, volume: float):
        if len(self.closes) == 0:
            self.ema_f = self.ema_s = self.ema_sig = close
            self.closes.append(close)
            self.volumes.append(volume)
            # init rsi dq with 0
            for _ in range(self.rsi_period):
                self.gain_dq.append(0)
                self.loss_dq.append(0)
            return

        prev_close = self.closes[-1]
        self.closes.append(close)
        self.volumes.append(volume)

        # 1. Update RSI (SMA style for simple smoothing)
        diff = close - prev_close
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
        
        avg_gain = self.gain_sum / self.rsi_period
        avg_loss = self.loss_sum / self.rsi_period
        
        rs = avg_gain / avg_loss if avg_loss > 1e-9 else 100.0
        self.prev_rsi = self.rsi
        self.rsi = 100.0 - (100.0 / (1.0 + rs)) if avg_loss > 1e-9 else 100.0

        # 2. Update MACD
        self.ema_f = close * self.alpha_f + self.ema_f * (1 - self.alpha_f)
        self.ema_s = close * self.alpha_s + self.ema_s * (1 - self.alpha_s)
        self.macd = self.ema_f - self.ema_s
        self.ema_sig = self.macd * self.alpha_sig + self.ema_sig * (1 - self.alpha_sig)
        self.macd_hist = self.macd - self.ema_sig

        # 3. Update BOLL
        if len(self.closes) >= self.boll_period:
            recent_closes = list(self.closes)[-self.boll_period:]
            self.boll_mid = float(np.mean(recent_closes))
            std = float(np.std(recent_closes))
            self.boll_up = self.boll_mid + self.boll_std * std
            self.boll_down = self.boll_mid - self.boll_std * std
            self.bbw = self.boll_up - self.boll_down
            self.bbw_history.append(self.bbw)
            
            if len(self.bbw_history) == 20:
                self.bbw_ma20 = float(np.mean(self.bbw_history))

        # 4. Update Volume MA
        if len(self.volumes) >= self.vol_ma_period:
            recent_vols = list(self.volumes)[-self.vol_ma_period:]
            self.volume_ma5 = float(np.mean(recent_vols))

        if len(self.closes) >= self.boll_period and len(self.bbw_history) == 20:
            self.is_ready = True

class StrategyState:
    def __init__(self):
        self.entry_prices = [] # Store prices for grid layers
        self.stats = {
            'buy_count': 0,
            'sell_tp': 0,
            'sell_sl': 0,
            'total_trades': 0
        }
        # Take profit tracking state
        self.touched_upper_band = False
        self.highest_rsi_since_entry = 0.0
        self.highest_close_since_entry = 0.0

class Zen71Strategy(BaseStrategy):
    """
    Zen 7.1.py (Resonance + Grid Optimization)
    引⼊网格摊薄机制，移除 MACD 与跌破中轨敏感止损，升级全局硬兜底与动态止盈。
    """
    def __init__(self, name="Grid_Zen_7_1", **params):
        super().__init__(name, **params)
        self.resample_min = params.get('resample_min', 60)
        self.indicators = Z71Indicators(resample_min=self.resample_min)
        self.state = StrategyState()
        
        self.symbol = params.get('symbol', 'BTCUSDT')
        self.capital = params.get('capital', 10000.0)
        self.grid_layers = params.get('grid_layers', 5)
        self.layer_value = self.capital / self.grid_layers
        
        # 新增优化参数
        self.grid_drop_pct = params.get('grid_drop_pct', 0.02) # 下跌 2% 允许加仓
        self.hard_sl_pct = params.get('hard_sl_pct', -0.10)    # 网格全仓 -10% 硬止损
        self.tp_min_profit_pct = params.get('tp_min_profit_pct', 0.03) # 动态止盈必须保底赚 3%
        
        self.last_ts = None
        self.last_minute_ts = None
        
    def initialize(self):
        super().initialize()
        self.indicators = Z71Indicators(resample_min=self.resample_min)
        self.state = StrategyState()

    def on_data(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        if self.last_minute_ts and data.timestamp <= self.last_minute_ts:
            return []
        self.last_minute_ts = data.timestamp
        
        bar_completed = self.indicators.update(data, True)
        
        if not self.indicators.is_ready:
            return []
            
        signals = []
        pos = context.positions.get(self.symbol)
        pos_size = pos.size if pos else 0
        cash = context.cash
        layers = len(self.state.entry_prices)
        
        ind = self.indicators
        
        # 1m 级别的实时硬止损检查 (不等待 1H 棒极值，防止爆雷)
        if pos_size > 0 and layers > 0:
            avg_cost = sum(self.state.entry_prices) / layers
            pnl_pct = (data.close - avg_cost) / avg_cost
            if pnl_pct <= self.hard_sl_pct:
                signals.append(Signal(
                    timestamp=data.timestamp,
                    symbol=self.symbol,
                    side=Side.SELL,
                    size=pos_size,
                    meta={'type': 'SELL_SL'},
                    reason=f"全局硬止损触发: {pnl_pct*100:.2f}% <= {self.hard_sl_pct*100:.2f}%"
                ))
                return signals # 触发止损直接返回，阻断后续逻辑
                
        # 基于 1H 收盘级别的判定 (进出场都在收线结算)
        if bar_completed:
            # Update tracking metrics
            if pos_size > 0 and layers > 0:
                if ind.rsi > self.state.highest_rsi_since_entry:
                    self.state.highest_rsi_since_entry = ind.rsi
                if data.close >= ind.boll_up:
                    self.state.touched_upper_band = True
                if data.close > self.state.highest_close_since_entry:
                    self.state.highest_close_since_entry = data.close
                    
            if pos_size > 0 and layers > 0:
                avg_cost = sum(self.state.entry_prices) / layers
                pnl_pct = (data.close - avg_cost) / avg_cost
                
                sell_reason = ""
                sig_type = ""
                
                # 2. 动态止盈池 (Take Profit Pool)
                # 条件 A: 整体盈利超过保底(如+3%) 且 曾经上轨超买并出现动能停滞 (当前未破新高)
                tp_cond_a = (pnl_pct >= self.tp_min_profit_pct) and \
                            (self.state.touched_upper_band and self.state.highest_rsi_since_entry > 65) and \
                            (data.close < self.state.highest_close_since_entry)
                
                # 条件 B: 极其疯狂的普涨暴赚 (如达到两倍基础收益的无脑割利润)
                tp_cond_b = pnl_pct >= self.tp_min_profit_pct * 2
                
                if tp_cond_a or tp_cond_b:
                    sell_reason = f"TP: 动态止盈触发 (均价:{avg_cost:.2f}, 盈亏:{pnl_pct*100:.2f}%)"
                    sig_type = "SELL_TP"
                        
                if sig_type != "":
                    # 平仓
                    signals.append(Signal(
                        timestamp=data.timestamp,
                        symbol=self.symbol,
                        side=Side.SELL,
                        size=pos_size,
                        meta={'type': sig_type, 'layers': layers},
                        reason=sell_reason
                    ))
            
            # Entry Logic (网格层推进)
            if (pos_size == 0) or (0 < layers < self.grid_layers):
                # 共振大前置 (无论哪一层，都必须有一定程度的多头特征或者极端超卖才能建仓)
                
                # A: 标准共振 (Volatility Expansion + MACD + Pullback)
                # 适度放宽 RSI 和成交量限制
                cond_resonance = (ind.bbw > ind.bbw_ma20) and (data.close > ind.boll_mid) and \
                                 (ind.macd_hist > 0) and \
                                 (35 <= ind.rsi <= 65) and \
                                 (ind.rsi > ind.prev_rsi)
                
                # B: 极端底网 (用于深水区接飞刀的左侧共振补充)
                # 放宽要求，只要 RSI 是深跌并拐头即可，不追求绝对破下轨
                cond_extreme_dip = (ind.prev_rsi < 35) and (ind.rsi > ind.prev_rsi)
                
                # 是否符合建仓意图
                want_buy = cond_resonance or cond_extreme_dip
                
                # 检查网格层约束
                can_buy = False
                buy_reason = ""
                
                if layers == 0 and cash > self.layer_value * 0.9:
                    # 首仓只需意图
                    if want_buy:
                        can_buy = True
                        buy_reason = "共振开网" if cond_resonance else "极端接针首仓"
                elif layers > 0 and cash > self.layer_value * 0.9:
                    # 补仓则需要意图 + 跌幅足够
                    avg_cost = sum(self.state.entry_prices) / layers
                    if data.close <= avg_cost * (1 - self.grid_drop_pct):
                        if want_buy:
                            can_buy = True
                            buy_reason = f"网格接续 ({layers+1}/{self.grid_layers}): 跌幅满意且触发买点"
                
                if can_buy:
                    # 保留手续费空间
                    buy_size_usdt = self.layer_value
                    if cash < buy_size_usdt:
                        buy_size_usdt = cash
                        
                    signals.append(Signal(
                        timestamp=data.timestamp,
                        symbol=self.symbol,
                        side=Side.BUY,
                        size=buy_size_usdt * 0.99,
                        meta={'size_in_quote': True, 'type': 'BUY_RESONANCE'},
                        reason=buy_reason
                    ))
                    
        return signals

    def on_fill(self, fill: FillEvent):
        sig_type = fill.meta.get('type', 'UNKNOWN')
        if fill.side == Side.BUY:
            self.state.entry_prices.append(fill.filled_price)
            self.state.stats['buy_count'] += 1
            self.state.stats['total_trades'] += 1
            # Reset TP state relative to NEW AVERAGE if we want, or just let it keep tracking the absolute highs
            self.state.touched_upper_band = False
            self.state.highest_rsi_since_entry = self.indicators.rsi
            self.state.highest_close_since_entry = fill.filled_price
            
            self.log(f"[{fill.timestamp}] 🚀 网格买入 ({len(self.state.entry_prices)}层) | 价格: {fill.filled_price:.2f} | 数量: {fill.filled_size:.4f}")
            
        elif fill.side == Side.SELL:
            avg_pop = sum(self.state.entry_prices) / len(self.state.entry_prices) if self.state.entry_prices else 0
            pnl_pct = (fill.filled_price - avg_pop) / avg_pop * 100 if avg_pop else 0
            
            # 清空网格状态
            self.state.entry_prices = []
            
            emoji = "✅" if sig_type == "SELL_TP" else "🛑"
            
            if sig_type == "SELL_TP":
                self.state.stats['sell_tp'] += 1
            elif sig_type == "SELL_SL":
                self.state.stats['sell_sl'] += 1
                
            self.state.stats['total_trades'] += 1
            self.log(f"[{fill.timestamp}] {emoji} 平仓 ({sig_type}) | 价格: {fill.filled_price:.2f} | 均价: {avg_pop:.2f} | 盈亏: {pnl_pct:+.2f}%")

    def get_status(self, context=None) -> Dict[str, Any]:
        return {
            'name': self.name,
            'rsi': round(self.indicators.rsi, 2),
            'layers': len(self.state.entry_prices),
            'avg_cost': round(sum(self.state.entry_prices) / len(self.state.entry_prices) if self.state.entry_prices else 0, 2),
            'stats': self.state.stats
        }
