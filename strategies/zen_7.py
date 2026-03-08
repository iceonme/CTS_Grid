import numpy as np
from collections import deque
from datetime import datetime
from typing import List, Dict, Any

from core import MarketData, Signal, Side, StrategyContext, FillEvent
from strategies.base import BaseStrategy

class Z7Indicators:
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

        # 1. Update RSI (Wilder's Smoothing or Simple MA)
        # Standard RSI usually uses Wilder's EMA, but Jeff logic used SMA style. We'll stick to a standard SMA RSI buffer for parity or Wilder's. Let's use SMA style:
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
        self.entry_price = 0.0
        self.position_size = 0.0
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

class Zen7Strategy(BaseStrategy):
    """
    Zen 7.py (Dynamic Volatility & Momentum Resonance)
    周期：通过内部 resample_min 控制（默认 60 分钟 = 1H）
    """
    def __init__(self, name="Grid_Zen_7_0", **params):
        super().__init__(name, **params)
        self.resample_min = params.get('resample_min', 60)
        self.indicators = Z7Indicators(resample_min=self.resample_min)
        self.state = StrategyState()
        
        self.symbol = params.get('symbol', 'BTCUSDT')
        self.capital = params.get('capital', 10000.0)
        self.last_ts = None
        self.last_minute_ts = None
        
    def initialize(self):
        super().initialize()
        self.indicators = Z7Indicators(resample_min=self.resample_min)
        self.state = StrategyState()

    def on_data(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        # Handle 1m bar deduplication just in case
        if self.last_minute_ts and data.timestamp <= self.last_minute_ts:
            return []
        self.last_minute_ts = data.timestamp
        
        # In case we pass 1H data directly from feed, resample_min shouldn't process 60 bars.
        # But we assume feed is 1m.
        bar_completed = self.indicators.update(data, True)
        
        if not self.indicators.is_ready:
            return []
            
        signals = []
        pos = context.positions.get(self.symbol)
        pos_size = pos.size if pos else 0
        cash = context.cash
        
        ind = self.indicators
        
        # Exit Logic evaluating on every minute or only on completed bars?
        # A hard stop loss check can be intraday (1m) or wait for 1H close. 
        # Requirement: "价格收盘有效跌破布林带中轨". This implies waiting for bar close.
        # We will check entry/exit ONLY when a 1H bar completes, giving true 1H strategy behavior.
        if bar_completed:
            # Update position tracking
            if pos_size > 0:
                if ind.rsi > self.state.highest_rsi_since_entry:
                    self.state.highest_rsi_since_entry = ind.rsi
                if data.close >= ind.boll_up:
                    self.state.touched_upper_band = True
                    
            if pos_size > 0:
                sell_reason = ""
                sig_type = ""
                
                # 1. Stop Loss: MACD死叉 或 收盘跌破中轨
                if ind.macd_hist < 0 or data.close < ind.boll_mid:
                    sell_reason = f"SL: MACD={ind.macd_hist:.2f}, Close={data.close:.2f}<Mid={ind.boll_mid:.2f}"
                    sig_type = "SELL_SL"
                    
                # 2. Take Profit: 之前触及上轨且RSI曾>70，且当前收盘未破前高
                elif self.state.touched_upper_band and self.state.highest_rsi_since_entry > 70:
                    if data.close < self.state.highest_close_since_entry:
                        sell_reason = f"TP: Momentum Exhaustion (RSI>{self.state.highest_rsi_since_entry:.1f})"
                        sig_type = "SELL_TP"
                        
                # 记录最高收盘价
                if data.close > self.state.highest_close_since_entry:
                    self.state.highest_close_since_entry = data.close
                    
                if sig_type != "":
                    signals.append(Signal(
                        timestamp=data.timestamp,
                        symbol=self.symbol,
                        side=Side.SELL,
                        size=pos_size,
                        meta={'type': sig_type},
                        reason=sell_reason
                    ))
            
            # Entry Logic
            elif pos_size == 0 and cash > 100:
                # Cond 1: Volatility Expansion
                cond1 = (ind.bbw > ind.bbw_ma20) and (data.close > ind.boll_mid)
                # Cond 2: MACD Trend
                cond2 = (ind.macd > 0) and (ind.macd_hist > 0)
                # Cond 3: Pullback & Volume
                cond3 = (40 <= ind.rsi <= 55) and (ind.current_bar_volume < ind.volume_ma5)
                # Cond 4: Hook
                cond4 = (ind.rsi > ind.prev_rsi)
                
                if cond1 and cond2 and cond3 and cond4:
                    buy_size = self.capital if cash >= self.capital else cash
                    signals.append(Signal(
                        timestamp=data.timestamp,
                        symbol=self.symbol,
                        side=Side.BUY,
                        size=buy_size * 0.99, # leave room for fee
                        meta={'size_in_quote': True, 'type': 'BUY_RESONANCE'},
                        reason=f"Resonance Buy: BBW>MA, MACD={ind.macd:.1f}, RSI={ind.rsi:.1f}, Vol < VolMA"
                    ))
                    
        return signals

    def on_fill(self, fill: FillEvent):
        sig_type = fill.meta.get('type', 'UNKNOWN')
        if fill.side == Side.BUY:
            self.state.entry_price = fill.filled_price
            self.state.position_size += fill.filled_size
            self.state.stats['buy_count'] += 1
            self.state.stats['total_trades'] += 1
            # Reset TP state
            self.state.touched_upper_band = False
            self.state.highest_rsi_since_entry = self.indicators.rsi
            self.state.highest_close_since_entry = fill.filled_price
            self.log(f"[{fill.timestamp}] 🚀 共振买入 | 价格: {fill.filled_price:.2f} | 数量: {fill.filled_size:.4f}")
            
        elif fill.side == Side.SELL:
            pnl_pct = (fill.filled_price - self.state.entry_price) / self.state.entry_price * 100 if self.state.entry_price else 0
            self.state.position_size = 0.0
            self.state.entry_price = 0.0
            emoji = "✅" if sig_type == "SELL_TP" else "🛑"
            
            if sig_type == "SELL_TP":
                self.state.stats['sell_tp'] += 1
            elif sig_type == "SELL_SL":
                self.state.stats['sell_sl'] += 1
                
            self.state.stats['total_trades'] += 1
            self.log(f"[{fill.timestamp}] {emoji} 平仓 ({sig_type}) | 价格: {fill.filled_price:.2f} | 盈亏: {pnl_pct:+.2f}%")

    def get_status(self, context=None) -> Dict[str, Any]:
        return {
            'name': self.name,
            'rsi': round(self.indicators.rsi, 2),
            'macd_hist': round(self.indicators.macd_hist, 2),
            'bbw': round(self.indicators.bbw, 2),
            'bbw_ma20': round(self.indicators.bbw_ma20, 2),
            'stats': self.state.stats
        }
