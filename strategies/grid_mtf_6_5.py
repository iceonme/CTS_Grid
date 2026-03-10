import os
import json
import numpy as np
import pandas as pd
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from collections import deque

from core import (
    MarketData, Signal, Side, OrderType, 
    FillEvent, Position, StrategyContext
)
from strategies.base import BaseStrategy
from strategies.grid_mtf_6_0 import IncrementalIndicatorsV6, StrategyState

# ============================================================
# V6.5A：动态网格交易策略 (RSI + 成交量 + K线形态)
# ============================================================

class GridStrategyV65A(BaseStrategy):
    """
    V6.5A 动态网格交易策略
    
    核心改进：去除 MACD 对交易信号的影响，采用 "RSI + 成交量 + K线形态" 三维验证模型。
    MACD 仍计算并展示在 Dashboard 上，但不参与买卖决策。
    新增：回撤急剧扩大或连续亏损后的熔断机制。
    """

    def __init__(self, name: str = "Grid_V65A_MTF", **params):
        super().__init__(name, **params)
        
        current_file_dir = Path(__file__).parent.resolve()
        config_dir = current_file_dir.parent / "config"
        
        self.params_path = params.get('config_path', str(config_dir / 'grid_v65_runtime.json'))
        self.meta_path = self.params_path.replace('runtime.json', 'meta.json')
        self.symbol = params.get('symbol', 'BTCUSDT')
        self.param_metadata = {}
        self._load_params()

        # 数据缓存
        self._data_5m = deque(maxlen=400)
        self._data_15m = deque(maxlen=200)
        self._last_15m_ts: Optional[datetime] = None

        # 策略内部状态 (使用 V6.5A 的独立定义)
        @dataclass
        class StrategyStateV65A:
            current_rsi: float = 50.0
            macd: float = 0.0
            macdsignal: float = 0.0
            macdhist: float = 0.0
            macd_prev: float = 0.0
            macdsignal_prev: float = 0.0
            macdhist_prev: float = 0.0
            atr: float = 0.0
            atr_ma: float = 0.0
            
            volume_ma: float = 0.0
            is_bullish_candle: bool = False
            
            grid_lower: float = 0.0
            grid_upper: float = 0.0
            grid_lines: List[float] = field(default_factory=list)
            
            is_halted: bool = False
            halt_reason: str = ""
            resume_time: Optional[datetime] = None
            pivots_high: List[Dict[str, Any]] = field(default_factory=list)
            pivots_low: List[Dict[str, Any]] = field(default_factory=list)
            
            last_grid_reset: Optional[datetime] = None
            last_buy_time: Optional[datetime] = None
            last_buy_price: float = 0.0
            
            peak_equity: float = 0.0
            current_drawdown: float = 0.0
            consecutive_losses: int = 0
            drawdown_halted: bool = False
            loss_halted: bool = False

        self.state = StrategyStateV65A()

    def _load_params(self):
        if os.path.exists(self.params_path):
            try:
                with open(self.params_path, 'r', encoding='utf-8') as f:
                    self.params.update(json.load(f))
            except Exception as e:
                print(f"[V6.5A] 加载参数失败: {e}")
        
        if os.path.exists(self.meta_path):
            try:
                with open(self.meta_path, 'r', encoding='utf-8') as f:
                    self.param_metadata = json.load(f)
            except Exception as e:
                print(f"[V6.5A] 加载元数据失败: {e}")

    def initialize(self):
        super().initialize()
        print(f"[V6.5A] {self.name} 初始化完成")

    def on_data(self, data: MarketData, context: Optional[StrategyContext]) -> List[Signal]:
        self._update_data(data)
        if len(self._data_5m) < 30 or len(self._data_15m) < 30:
            return []

        self._calculate_indicators()
        if self._check_halt(data, context):
            return []

        self._manage_grid(data)
        if context:
            return self._generate_signals(data, context)
        return []

    def _update_data(self, data: MarketData):
        ts = data.timestamp
        bar_ts = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        
        if self._data_5m and self._data_5m[-1].timestamp.replace(minute=(self._data_5m[-1].timestamp.minute // 5) * 5, second=0, microsecond=0) == bar_ts:
            last = self._data_5m[-1]
            updated = MarketData(
                timestamp=data.timestamp,
                symbol=data.symbol,
                open=last.open,
                high=max(last.high, data.high),
                low=min(last.low, data.low),
                close=data.close,
                volume=data.volume
            )
            self._data_5m[-1] = updated
        else:
            self._data_5m.append(data)
        
        period_ts = ts.replace(minute=(ts.minute // 15) * 15, second=0, microsecond=0)
        if self._last_15m_ts is None or period_ts > self._last_15m_ts:
            self._last_15m_ts = period_ts
            self._data_15m.append({
                'timestamp': period_ts,
                'open': data.open, 'high': data.high, 
                'low': data.low, 'close': data.close, 
                'volume': data.volume
            })
        else:
            bar = self._data_15m[-1]
            bar['high'] = max(bar['high'], data.high)
            bar['low'] = min(bar['low'], data.low)
            bar['close'] = data.close
            
            vol_sum = 0
            for i in range(len(self._data_5m) - 1, -1, -1):
                d = self._data_5m[i]
                d_period_ts = d.timestamp.replace(minute=(d.timestamp.minute // 15) * 15, second=0, microsecond=0)
                if d_period_ts < period_ts:
                    break
                if d_period_ts == period_ts:
                    vol_sum += d.volume
            bar['volume'] = vol_sum

    def _calculate_indicators(self):
        closes_5m = pd.Series([d.close for d in self._data_5m])
        self.state.current_rsi = self._rsi(closes_5m, self.params.get('rsi_period', 14))
        
        highs = pd.Series([d.high for d in self._data_5m])
        lows = pd.Series([d.low for d in self._data_5m])
        closes = pd.Series([d.close for d in self._data_5m])
        atr_val = self._atr(highs, lows, closes, self.params.get('atr_period', 14))
        self.state.atr = atr_val
        self.state.atr_ma = pd.Series([getattr(d, 'atr', atr_val) for d in list(self._data_5m)[-72:]]).mean() if len(self._data_5m) >= 72 else atr_val

        volumes = pd.Series([d.volume for d in self._data_5m])
        vol_ma_period = self.params.get('volume_ma_period', 20)
        vol_ma = volumes.rolling(window=vol_ma_period).mean().iloc[-1]
        self.state.volume_ma = vol_ma if not np.isnan(vol_ma) else 0.0

        latest = self._data_5m[-1]
        self.state.is_bullish_candle = latest.close > latest.open

        df_15m = pd.DataFrame(list(self._data_15m))
        macd, signal, hist = self._macd(df_15m['close'], self.params.get('macd_fast', 12), self.params.get('macd_slow', 26), self.params.get('macd_signal', 9))
        self.state.macd_prev, self.state.macdsignal_prev, self.state.macdhist_prev = self.state.macd, self.state.macdsignal, self.state.macdhist
        self.state.macd, self.state.macdsignal, self.state.macdhist = macd, signal, hist

        df_5m = pd.DataFrame(list(self._data_5m))
        self._find_pivot_points(df_5m)

    def _manage_grid(self, data: MarketData):
        now = data.timestamp
        if not self.state.pivots_high or not self.state.pivots_low:
            lookback = self.params.get('grid_lookback_hours', 6)
            bars = list(self._data_5m)[-int(lookback * 12):]
            if not bars: return
            upper, lower = max(b.high for b in bars), min(b.low for b in bars)
        else:
            upper, lower = max(p['price'] for p in self.state.pivots_high), min(p['price'] for p in self.state.pivots_low)

        range_size = upper - lower
        if range_size <= 0: range_size = upper * 0.01
        buffer = self.params.get('grid_buffer', 0.02)
        self.state.grid_upper, self.state.grid_lower = upper * (1 + buffer), lower * (1 - buffer)
        layers = self.params.get('grid_layers', 5)
        self.state.grid_lines = np.linspace(self.state.grid_lower, self.state.grid_upper, layers + 1).tolist()
        self.state.last_grid_reset = now

    def _check_halt(self, data: MarketData, context: Optional[StrategyContext] = None) -> bool:
        if self.state.is_halted:
            if self.state.resume_time and data.timestamp >= self.state.resume_time:
                self.state.is_halted = False
                print(f"[V6.5A] 恢复交易")
            else: return True
        
        if self.state.atr > self.state.atr_ma * self.params.get('atr_blackswan_mult', 3.0):
            self.state.is_halted = True
            self.state.halt_reason = "波动风控 (ATR异常)"
            self.state.resume_time = data.timestamp + timedelta(minutes=self.params.get('atr_cooldown_min', 30))
            print(f"[V6.5A] 触发熔断: {self.state.halt_reason}")
            return True

        if context:
            pos = context.positions.get(self.symbol)
            equity = context.cash + (float(pos.size) * data.close if pos else 0.0)
            if equity > self.state.peak_equity: self.state.peak_equity = equity
            if self.state.peak_equity > 0: self.state.current_drawdown = (self.state.peak_equity - equity) / self.state.peak_equity
            
            if self.state.current_drawdown > self.params.get('max_drawdown', 0.10):
                self.state.drawdown_halted = True
                self.state.halt_reason = f"回撤风控 ({self.state.current_drawdown:.1%})"
                return True
            else: self.state.drawdown_halted = False

        if self.state.consecutive_losses >= self.params.get('max_consecutive_losses', 5):
            self.state.loss_halted = True
            self.state.halt_reason = f"连续亏损风控 ({self.state.consecutive_losses}次)"
            return True
        return False

    def _generate_signals(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        signals = []
        pos = context.positions.get(self.symbol)
        pos_size = float(pos.size) if pos else 0.0
        layer_value = self.params.get('total_capital', 10000) / self.params.get('grid_layers', 5)
        current_layers = int(round(pos_size * data.close / layer_value)) if pos_size > 0 else 0

        cooldown_lock = False
        if getattr(self.state, 'last_buy_time', None) and data.timestamp < self.state.last_buy_time + timedelta(minutes=self.params.get('buy_cooldown_min', 15)):
            cooldown_lock = True

        vol_confirmed = self.state.volume_ma > 0 and data.volume > self.state.volume_ma * self.params.get('volume_threshold', 1.3)

        if pos_size > 0 and not cooldown_lock:
            if self.state.current_rsi > self.params.get('rsi_sell_threshold', 70) and vol_confirmed and not self.state.is_bullish_candle:
                sell_ratio = min(1, current_layers) / current_layers if current_layers > 0 else 1.0
                signals.append(Signal(timestamp=data.timestamp, symbol=self.symbol, side=Side.SELL, size=pos_size * sell_ratio, reason="V6.5A Sell"))
                if self.state.last_buy_price > 0:
                    if data.close < self.state.last_buy_price: self.state.consecutive_losses += 1
                    else: self.state.consecutive_losses = 0

        if not cooldown_lock and self.state.current_rsi < self.params.get('rsi_buy_threshold', 30) and vol_confirmed and self.state.is_bullish_candle and current_layers < self.params.get('grid_layers', 5):
            signals.append(Signal(timestamp=data.timestamp, symbol=self.symbol, side=Side.BUY, size=layer_value, meta={'size_in_quote': True}, reason="V6.5A Buy"))
            self.state.last_buy_time, self.state.last_buy_price = data.timestamp, data.close
        return signals

    def _rsi(self, series, period):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs.iloc[-1])) if not np.isnan(rs.iloc[-1]) else 50.0

    def _atr(self, high, low, close, period):
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        return tr.rolling(window=period).mean().iloc[-1]

    def _macd(self, series, fast, slow, signal):
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal, adjust=False).mean()
        return macd.iloc[-1], signal_line.iloc[-1], (macd - signal_line).iloc[-1]

    def _find_pivot_points(self, df: pd.DataFrame):
        if len(self._data_5m) < 20: return
        n, window_size = 3, 10
        data_list = list(self._data_5m)
        highs, lows = df['high'].values, df['low'].values
        curr_idx = len(df) - 1
        if curr_idx < window_size + 1: return
        all_h, all_l = [], []
        for i in range(window_size, curr_idx + 1):
            if lows[i] <= min(lows[i-window_size:i]):
                if (i > curr_idx - window_size and (i == curr_idx or lows[i] <= min(lows[i+1:]))) or (i <= curr_idx - window_size and lows[i] < min(lows[i+1 : i+window_size+1])):
                    all_l.append({'price': float(lows[i]), 'time': data_list[i].timestamp.isoformat(), 'index': i})
            if highs[i] >= max(highs[i-window_size:i]):
                if (i > curr_idx - window_size and (i == curr_idx or highs[i] >= max(highs[i+1:]))) or (i <= curr_idx - window_size and highs[i] > max(highs[i+1 : i+window_size+1])):
                    all_h.append({'price': float(highs[i]), 'time': data_list[i].timestamp.isoformat(), 'index': i})
        def _get_n(pivots):
            res = []
            for p in reversed(pivots):
                if not res or (res[-1]['index'] - p['index']) >= window_size: res.append(p)
                if len(res) >= n: break
            res.reverse(); return res
        self.state.pivots_high, self.state.pivots_low = _get_n(all_h), _get_n(all_l)

    def get_status(self, context: Optional[StrategyContext] = None) -> Dict[str, Any]:
        is_bullish = self.state.macdhist > 0
        macd_trend = ("强牛" if is_bullish and self.state.macdhist > self.state.macdhist_prev else "牛市" if is_bullish else "强熊" if self.state.macdhist < self.state.macdhist_prev else "熊市")
        pos = context.positions.get(self.symbol) if context else None
        p_size = float(pos.size) if pos else 0.0
        return {
            'name': self.name, 'current_rsi': round(self.state.current_rsi, 2),
            'macd_trend': macd_trend, 'position_size': p_size,
            'grid_range': f"{self.state.grid_lower:.1f} - {self.state.grid_upper:.1f}",
            'is_halted': self.state.is_halted or self.state.drawdown_halted or self.state.loss_halted,
            'params': self.params
        }

# ============================================================
# V6.5 Winner：大鸡腿版 (趋势锁定 + 均线拦截)
# ============================================================

class GridMTFStrategyV6_5(BaseStrategy):
    """
    V6.5-Winner "大鸡腿"版
    针对 2025 年牛市主升浪优化的专项版本
    """
    def __init__(self, name: str = "Grid_V65_Winner", **params):
        super().__init__(name, **params)
        current_file_dir = Path(__file__).parent.resolve()
        config_dir = current_file_dir.parent / "config"
        self.default_params_path = str(config_dir / 'grid_v60_default.json')
        self.params_path = str(config_dir / 'grid_v65_runtime.json')
        self.symbol = params.get('symbol', 'BTCUSDT')
        self._load_params()
        self._data_5m = deque(maxlen=600) 
        self._data_15m_closes = deque(maxlen=250)
        self._last_5m_ts, self._last_bar_5m = None, None
        self.state = StrategyState()
        self.indicators = IncrementalIndicatorsV6(self.params)
        self._last_15m_ts, self._last_15m_bar_close, self.ma200_15m = None, 0.0, 0.0

    def _load_params(self):
        for path in [self.default_params_path, self.params_path]:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f: self.params.update(json.load(f))

    def on_data(self, data: MarketData, context: Optional[StrategyContext]) -> List[Signal]:
        if not self._last_5m_ts or data.timestamp > self._last_5m_ts:
            if self._last_bar_5m: self.indicators.update_5m(self._last_bar_5m, commit=True)
            self._last_5m_ts = data.timestamp
            ts = data.timestamp
            period_ts = ts.replace(minute=(ts.minute // 15) * 15, second=0, microsecond=0)
            if self._last_15m_ts is None or period_ts > self._last_15m_ts:
                if self._last_15m_ts is not None:
                    self.indicators.update_15m_macd(self._last_15m_bar_close, commit=True)
                    self._data_15m_closes.append(self._last_15m_bar_close)
                self._last_15m_ts, self._last_15m_bar_close = period_ts, data.close
            else: self._last_15m_bar_close = data.close
        self._last_bar_5m = data
        self._data_5m.append(data)
        if len(self._data_15m_closes) < 20: return []
        rsi, atr, atr_ma = self.indicators.update_5m(data, commit=False)
        macd, sig, hist = self.indicators.update_15m_macd(data.close, commit=False)
        self.ma200_15m = np.mean(list(self._data_15m_closes)[-200:]) if len(self._data_15m_closes) >= 200 else np.mean(list(self._data_15m_closes))
        self.state.current_rsi, self.state.atr, self.state.atr_ma = rsi, atr, atr_ma
        self.state.macd, self.state.macdsignal, self.state.macdhist = macd, sig, hist
        if self._check_halt(data): return []
        self._manage_grid(data)
        if context: return self._generate_signals(data, context)
        return []

    def _manage_grid(self, data: MarketData):
        now = data.timestamp
        lookback = self.params.get('grid_lookback_hours', 24)
        need_reset = False
        if self.state.grid_upper == 0 or (self.state.last_grid_reset and (now - self.state.last_grid_reset) > timedelta(hours=lookback)) or abs(data.close - (self.state.grid_upper + self.state.grid_lower)/2) / ((self.state.grid_upper + self.state.grid_lower)/2) > 0.08:
            need_reset = True
        if need_reset:
            bars = list(self._data_5m)
            if not bars: return
            high, low = max(b.high for b in bars), min(b.low for b in bars)
            buffer, layers = 0.03, 6
            self.state.grid_upper, self.state.grid_lower = high * (1 + buffer), low * (1 - buffer)
            self.state.grid_lines = np.linspace(self.state.grid_lower, self.state.grid_upper, layers + 1).tolist()
            self.state.last_grid_reset = now

    def _check_halt(self, data: MarketData) -> bool:
        if self.state.is_halted:
            if self.state.resume_time and data.timestamp >= self.state.resume_time: self.state.is_halted = False
            else: return True
        if self.state.atr > self.state.atr_ma * 3.5:
            self.state.is_halted, self.state.resume_time = True, data.timestamp + timedelta(minutes=60)
            return True
        return False

    def _generate_signals(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        signals = []
        pos = context.positions.get(self.symbol)
        pos_size = pos.size if pos else 0
        is_bullish = self.state.macdhist > 0
        hist_growth = self.state.macdhist - getattr(self.state, 'macdhist_prev', self.state.macdhist)
        self.state.macdhist_prev = self.state.macdhist
        if pos_size > 0 and self.state.current_rsi > 80 and (hist_growth < 0 or not is_bullish):
            signals.append(Signal(data.timestamp, self.symbol, Side.SELL, pos_size, reason="Winner TP"))
        if not signals and data.close >= self.ma200_15m and is_bullish and self.state.current_rsi < 35:
            idx = -1
            for i in range(len(self.state.grid_lines) - 1):
                if self.state.grid_lines[i] <= data.close < self.state.grid_lines[i+1]:
                    idx = i; break
            if idx != -1 and idx < 3:
                layers = 6
                buy_usdt = self.params.get('total_capital', 10000) * ((layers - idx) / sum(range(1, layers + 1))) * np.clip(self.state.atr_ma / (self.state.atr + 1e-9), 0.7, 1.5) * (1.3 if is_bullish and self.state.macdhist > self.state.macdsignal * 0.5 else 1.0)
                if context.cash >= buy_usdt:
                    signals.append(Signal(data.timestamp, self.symbol, Side.BUY, buy_usdt, meta={'size_in_quote': True}, reason="Winner Buy"))
        return signals

    def get_status(self, context=None):
        from strategies.grid_mtf_6_0 import GridMTFStrategyV6_0
        res = GridMTFStrategyV6_0.get_status(self, context)
        res['ma200_15m'] = round(self.ma200_15m, 2)
        return res
