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

# ============================================================
# 高性能增量指标引擎 (适配 V6.0 逻辑)
# ============================================================

class IncrementalIndicatorsV6:
    def __init__(self, p: dict):
        self.p = p
        self.count_5m = 0
        self.count_15m = 0
        
        # RSI 5m (SMA Based)
        self.rsi_period = p.get('rsi_period', 14)
        self.gain_dq = deque(maxlen=self.rsi_period)
        self.loss_dq = deque(maxlen=self.rsi_period)
        self.gain_sum = 0.0
        self.loss_sum = 0.0
        self.prev_close_5m = 0.0
        
        # ATR 5m (SMA Based)
        self.atr_period = p.get('atr_period', 14)
        self.tr_dq = deque(maxlen=self.atr_period)
        self.tr_sum = 0.0
        self.prev_close_tr = 0.0
        
        # ATR MA (72 periods of ATR)
        self.atr_ma_dq = deque(maxlen=72)
        self.atr_ma_sum = 0.0
        
        # MACD 15m (EMA Based)
        self.m_fast = p.get('macd_fast', 12)
        self.m_slow = p.get('macd_slow', 26)
        self.m_sig = p.get('macd_signal', 9)
        self.ema_f = 0.0
        self.ema_s = 0.0
        self.ema_sig = 0.0
        self.alpha_f = 2.0 / (self.m_fast + 1)
        self.alpha_s = 2.0 / (self.m_slow + 1)
        self.alpha_sig = 2.0 / (self.m_sig + 1)

    def update_5m(self, d: MarketData, commit: bool = True):
        c, h, l = d.close, d.high, d.low
        if self.count_5m == 0:
            if commit:
                self.prev_close_5m = self.prev_close_tr = c
                self.count_5m += 1
            return 50.0, 0.0, 0.0

        diff = c - self.prev_close_5m
        gain = max(diff, 0); loss = max(-diff, 0)
        tr = max(h - l, abs(h - self.prev_close_tr), abs(l - self.prev_close_tr))

        def get_sma(dq, cur_sum, val, p):
            count = len(dq)
            if count == 0: return val
            s = cur_sum + val - (dq[0] if count == p else 0)
            return s / (count if count < p else p)

        rsi_g = get_sma(self.gain_dq, self.gain_sum, gain, self.rsi_period)
        rsi_l = get_sma(self.loss_dq, self.loss_sum, loss, self.rsi_period)
        rs = rsi_g / rsi_l if rsi_l > 1e-9 else 100.0
        rsi = 100.0 - (100.0 / (1.0 + rs)) if rsi_l > 1e-9 else 100.0
        
        atr = get_sma(self.tr_dq, self.tr_sum, tr, self.atr_period)
        atr_ma = get_sma(self.atr_ma_dq, self.atr_ma_sum, atr, 72)

        if commit:
            if len(self.gain_dq) == self.rsi_period: self.gain_sum -= self.gain_dq.popleft()
            self.gain_dq.append(gain); self.gain_sum += gain
            if len(self.loss_dq) == self.rsi_period: self.loss_sum -= self.loss_dq.popleft()
            self.loss_dq.append(loss); self.loss_sum += loss
            if len(self.tr_dq) == self.atr_period: self.tr_sum -= self.tr_dq.popleft()
            self.tr_dq.append(tr); self.tr_sum += tr
            if len(self.atr_ma_dq) == 72: self.atr_ma_sum -= self.atr_ma_dq.popleft()
            self.atr_ma_dq.append(atr); self.atr_ma_sum += atr
            self.prev_close_5m = self.prev_close_tr = c
            self.count_5m += 1
            
        return rsi, atr, atr_ma

    def update_15m_macd(self, close: float, commit: bool = True):
        if self.count_15m == 0:
            if commit:
                self.ema_f = self.ema_s = close
                self.count_15m += 1
            return 0.0, 0.0, 0.0

        f = close * self.alpha_f + self.ema_f * (1 - self.alpha_f)
        s = close * self.alpha_s + self.ema_s * (1 - self.alpha_s)
        macd = f - s
        sig = macd * self.alpha_sig + self.ema_sig * (1 - self.alpha_sig)
        hist = macd - sig

        if commit:
            self.ema_f, self.ema_s, self.ema_sig = f, s, sig
            self.count_15m += 1
            
        return macd, sig, hist

@dataclass
class StrategyState:
    current_rsi: float = 50.0
    macd: float = 0.0
    macdsignal: float = 0.0
    macdhist: float = 0.0
    macdhist_prev: float = 0.0
    atr: float = 0.0
    atr_ma: float = 0.0
    
    grid_lower: float = 0.0
    grid_upper: float = 0.0
    grid_lines: List[float] = field(default_factory=list)
    
    is_halted: bool = False
    halt_reason: str = ""
    resume_time: Optional[datetime] = None
    
    last_grid_reset: Optional[datetime] = None


class GridMTFStrategyV6_0(BaseStrategy):
    """
    V6.0-MTF 多周期自适应网格策略
    """
    def __init__(self, name: str = "Grid_V60_MTF", **params):
        super().__init__(name, **params)
        
        # 动态定位核心配置目录
        current_file_dir = Path(__file__).parent.resolve()
        config_dir = current_file_dir.parent / "config"
        
        self.default_params_path = str(config_dir / 'grid_v60_default.json')
        self.params_path = str(config_dir / 'grid_v60_runtime.json')
        # 自动推导 meta 路径
        self.meta_path = self.params_path.replace('runtime.json', 'meta.json')
        self.symbol = params.get('symbol', 'BTCUSDT')
        self.param_metadata = {}
        self._load_params()

        # 数据缓存
        self._data_5m = deque(maxlen=400)   # 5m K线缓存 (约33小时，确保能看到完整日结构)
        self._data_15m = deque(maxlen=200)  # 15m 重采样缓存
        self._last_15m_ts: Optional[datetime] = None

        # 策略内部状态
        @dataclass
        class StrategyState:
            current_rsi: float = 50.0
            macd: float = 0.0
            macdsignal: float = 0.0
            macdhist: float = 0.0
            macdhist_prev: float = 0.0
            atr: float = 0.0
            atr_ma: float = 0.0
            
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
        self.state = StrategyState()
        self.indicators = IncrementalIndicatorsV6(self.params)
        self._last_5m_ts = None
        self._last_bar_5m = None
        self._last_15m_bar_close = 0.0

    def _load_params(self):
        """加载运行参数与元数据说明"""
        # 1. 加载默认参数
        if os.path.exists(self.default_params_path):
            try:
                with open(self.default_params_path, 'r', encoding='utf-8') as f:
                    self.params.update(json.load(f))
            except Exception as e:
                print(f"[V6.0] 加载默认参数失败: {e}")

        # 2. 加载运行时覆盖参数
        if os.path.exists(self.params_path):
            try:
                with open(self.params_path, 'r', encoding='utf-8') as f:
                    self.params.update(json.load(f))
            except Exception as e:
                print(f"[V6.0] 加载运行参数失败: {e}")
        
        # 2. 加载元数据 (用于 Dashboard 说明面板)
        if os.path.exists(self.meta_path):
            try:
                with open(self.meta_path, 'r', encoding='utf-8') as f:
                    self.param_metadata = json.load(f)
            except Exception as e:
                print(f"[V6.0] 加载元数据失败: {e}")

    def initialize(self):
        super().initialize()
        self.state = StrategyState()
        self.indicators = IncrementalIndicatorsV6(self.params)
        self._last_5m_ts = None
        self._last_bar_5m = None
        self._data_5m.clear()
        self._data_15m.clear()
        self._last_15m_ts = None
        print(f"[V6.0] {self.name} 初始化完成")

    def on_data(self, data: MarketData, context: Optional[StrategyContext]) -> List[Signal]:
        # 0. 5m 周期推进与指标进位
        is_new_bar = (not self._last_5m_ts) or (data.timestamp > self._last_5m_ts)
        if is_new_bar:
            if self._last_bar_5m:
                self.indicators.update_5m(self._last_bar_5m, commit=True)
            self._last_5m_ts = data.timestamp
            self._update_data(data)
        self._last_bar_5m = data

        if len(self._data_5m) < 30: return []

        # 1. 指标实时预览 (5m RSI, ATR)
        rsi, atr, atr_ma = self.indicators.update_5m(data, commit=False)
        self.state.current_rsi = rsi
        self.state.atr = atr
        self.state.atr_ma = atr_ma

        # 2. 15m MACD 预览与进位
        # 检查是否刚跨越 15m 边界（已经在 _update_data 中处理了聚合，这里执行 MACD 指标计算）
        macd, sig, hist = self.indicators.update_15m_macd(data.close, commit=False)
        self.state.macd = macd
        self.state.macdsignal = sig
        self.state.macdhist = hist
        
        # 3. 熔断检测 (黑天鹅)
        if self._check_halt(data):
            return []

        # 4. 网格管理 (边界计算与重置)
        self._manage_grid(data)

        # 5. 信号生成
        if context:
            return self._generate_signals(data, context)
        return []

    def _update_data(self, data: MarketData):
        """更新 5m 数据并执行 15m 重采样
        
        关键：OKX 数据流每2秒推送一次同一根5分钟K线的最新状态，
        必须将同一5分钟周期的多次推送合并为一条记录，
        否则 _data_5m 里存的是2秒快照而非5分钟K线，所有指标计算都会错误。
        """
        ts = data.timestamp
        # 按5分钟取整作为当前K线的标识时间
        bar_ts = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        
        if self._data_5m and self._data_5m[-1].timestamp.replace(
                minute=(self._data_5m[-1].timestamp.minute // 5) * 5, 
                second=0, microsecond=0) == bar_ts:
            # 同一根5分钟K线：更新最后一条的 high/low/close/volume
            last = self._data_5m[-1]
            updated = MarketData(
                timestamp=data.timestamp,  # 用最新时间戳
                symbol=data.symbol,
                open=last.open,            # open 保持不变（该K线第一次的开盘价）
                high=max(last.high, data.high),
                low=min(last.low, data.low),
                close=data.close,          # close 用最新价
                volume=data.volume         # OKX每次推送的已经是这根5mK线的累计量，故直接覆盖
            )
            self._data_5m[-1] = updated
        else:
            # 新的5分钟周期：追加新记录
            self._data_5m.append(data)
        
        # 15m 重采样逻辑 (以 0, 15, 30, 45 分钟为界)
        period_ts = ts.replace(minute=(ts.minute // 15) * 15, second=0, microsecond=0)
        
        if self._last_15m_ts is None or period_ts > self._last_15m_ts:
            # 旧的 15m 周期结束，正式进位 MACD 引擎
            if self._last_15m_ts is not None:
                self.indicators.update_15m_macd(self._last_15m_bar_close, commit=True)

            self._last_15m_ts = period_ts
            self._last_15m_bar_close = data.close
            self._data_15m.append({
                'timestamp': period_ts,
                'open': data.open, 'high': data.high, 
                'low': data.low, 'close': data.close, 
                'volume': data.volume
            })
        else:
            # 更新当前的 15m 周期
            bar = self._data_15m[-1]
            bar['high'] = max(bar['high'], data.high)
            bar['low'] = min(bar['low'], data.low)
            bar['close'] = data.close
            # 计算 15m 周期内的精确 volume：
            # 找到在当前 15m 周期内（属于这段 period_ts），但【已经完结】（不仅指最新一根正在跑的）的所有 5m K线。
            # 直接遍历 self._data_5m 从后往前找，把 timestamp 大于等于 period_ts 且与 period_ts 属于同一 15m 窗口的所有完整 5m 累加。
            vol_sum = 0
            for i in range(len(self._data_5m) - 1, -1, -1):
                d = self._data_5m[i]
                d_period_ts = d.timestamp.replace(minute=(d.timestamp.minute // 15) * 15, second=0, microsecond=0)
                if d_period_ts < period_ts:
                    break  # 已经跨越到上一个 15m 周期，停止
                if d_period_ts == period_ts:
                    # 只要是属于 this 15m 周期内的 5m K线，直接把它们内部已经整理好的 `volume` 加起来。
                    # 注意如果 `_data_5m` 已经是去重过的，那么最后一根就是包含当前 data.volume 的
                    vol_sum += d.volume
            bar['volume'] = vol_sum

    # 指标计算已移至 IncrementalIndicatorsV6 增量引擎
    def _calculate_indicators(self):
        pass

        # 波段点识别 (3高3低逻辑，集成 V4.0)
        df_5m = pd.DataFrame(list(self._data_5m))
        self._find_pivot_points(df_5m)

    def _manage_grid(self, data: MarketData):
        """以波段结构点驱动动态网格 (3高3低)"""
        now = data.timestamp
        
        # 仅在有完整波段数据时更新网格
        if not self.state.pivots_high or not self.state.pivots_low:
            # 回退到过去 6 小时 ATR 逻辑 (防止冷启动)
            lookback = self.params.get('grid_lookback_hours', 6)
            bars = list(self._data_5m)[-int(lookback * 12):]
            if not bars: return
            upper = max(b.high for b in bars)
            lower = min(b.low for b in bars)
        else:
            # 使用3高3低的极值作为网格边界
            upper = max(p['price'] for p in self.state.pivots_high)
            lower = min(p['price'] for p in self.state.pivots_low)

        # 缓冲区处理
        range_size = upper - lower
        if range_size <= 0: range_size = upper * 0.01
        buffer = self.params.get('grid_buffer', 0.02)
        
        self.state.grid_upper = upper * (1 + buffer)
        self.state.grid_lower = lower * (1 - buffer)
        
        # 生成网格线
        layers = self.params.get('grid_layers', 5)
        self.state.grid_lines = np.linspace(self.state.grid_lower, self.state.grid_upper, layers + 1).tolist()
        self.state.last_grid_reset = now

    def _check_halt(self, data: MarketData) -> bool:
        """黑天鹅检测"""
        if self.state.is_halted:
            if self.state.resume_time and data.timestamp >= self.state.resume_time:
                self.state.is_halted = False
                self.log(f"[V6.0] 恢复交易")
            else:
                return True
        
        # ATR 异常检测
        if self.state.atr > self.state.atr_ma * self.params.get('atr_blackswan_mult', 3.0):
            self.state.is_halted = True
            self.state.halt_reason = "High Volatility (ATR Blackswan)"
            self.state.resume_time = data.timestamp + timedelta(minutes=self.params.get('atr_cooldown_min', 30))
            self.log(f"[V6.0] 触发熔断: {self.state.halt_reason}")
            return True
            
        return False

    def _generate_signals(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        signals = []
        pos = context.positions.get(self.symbol)
        pos_size = float(pos.size) if pos else 0.0
        
        # --- 全局买卖锁定：解决买入秒卖出问题 ---
        cooldown_lock = False
        cooldown_min = self.params.get('buy_cooldown_min', 15)
        if getattr(self.state, 'last_buy_time', None) is not None:
            from datetime import timedelta
            if data.timestamp < self.state.last_buy_time + timedelta(minutes=cooldown_min):
                cooldown_lock = True
        
        # 趋势强度 (15m MACD)
        is_bullish = self.state.macdhist > 0
        is_strong_bull = is_bullish and self.state.macd > 0 and self.state.macdhist > self.state.macdhist_prev if hasattr(self.state, 'macdhist_prev') else False
        self.state.macdhist_prev = self.state.macdhist

        # 1. 卖出逻辑 (加入全局锁定)
        if pos_size > 0 and not cooldown_lock:
            sell_threshold = self.params.get('rsi_sell_threshold', 70)
            if is_strong_bull:
                sell_threshold = self.params.get('rsi_bull_adjust', 60)
            
            if self.state.current_rsi > sell_threshold:
                if getattr(self.state, 'grid_lines', []) and len(self.state.grid_lines) >= 2:
                    if data.close >= self.state.grid_lines[-2]:
                        sell_ratio = 1.0 # 简化全部卖出
                        reason = f"MTF Sell: RSI={self.state.current_rsi:.1f} Bullish={is_bullish} Vol={pos_size:.4f}"
                        signals.append(Signal(
                            timestamp=data.timestamp,
                            symbol=self.symbol,
                            side=Side.SELL,
                            size=pos_size * sell_ratio,
                            reason=reason
                        ))

        # 2. 买入逻辑
        rsi_buy_threshold = self.params.get('rsi_buy_threshold', 35)
        rsi_condition = self.state.current_rsi < rsi_buy_threshold
        
        pivot_condition = False
        if getattr(self.state, 'pivots_low', []):
            lowest_pivot_low = min(p['price'] for p in self.state.pivots_low)
            margin = self.params.get('pivot_buy_margin', 0.005)
            if data.close <= lowest_pivot_low * (1 + margin) and self.state.current_rsi < 45:
                pivot_condition = True
        
        macd_improving = hasattr(self.state, 'macdhist_prev') and self.state.macdhist > self.state.macdhist_prev
        
        can_buy = False
        if rsi_condition and (is_bullish or macd_improving): can_buy = True
        if pivot_condition and self.state.current_rsi < 40: can_buy = True

        if cooldown_lock: can_buy = False

        if can_buy and pos_size > 0:
            price_buffer = self.params.get('buy_price_buffer', 0.003)
            price_dropped = True
            if getattr(self.state, 'last_buy_price', 0) > 0:
                price_dropped = data.close <= self.state.last_buy_price * (1.0 - price_buffer)
            if not price_dropped: can_buy = False

        if can_buy and getattr(self.state, 'grid_lines', []):
            forbidden_zone = self.state.grid_lower + (self.state.grid_upper - self.state.grid_lower) * 0.66
            if data.close > forbidden_zone: can_buy = False

        if can_buy and getattr(self.state, 'grid_lines', []):
            idx = -1
            for i in range(len(self.state.grid_lines) - 1):
                if self.state.grid_lines[i] <= data.close < self.state.grid_lines[i+1]:
                    idx = i
                    break
            if idx != -1:
                layers = self.params.get('grid_layers', 5)
                weight = (layers - idx) / sum(range(1, layers + 1))
                if pivot_condition: weight *= 1.2
                
                buy_usdt = self.params.get('total_capital', 10000) * weight
                
                if context.cash >= buy_usdt * 0.95:
                    pt_str = "(Pivot Support)" if pivot_condition else ""
                    reason = f"MTF Grid Buy: Layer={idx} RSI={self.state.current_rsi:.1f} {pt_str}"
                    signals.append(Signal(
                        timestamp=data.timestamp,
                        symbol=self.symbol,
                        side=Side.BUY,
                        size=buy_usdt,
                        meta={'size_in_quote': True},
                        reason=reason
                    ))
                    self.state.last_buy_time = data.timestamp
                    self.state.last_buy_price = data.close

        return signals

    # --- 技术指标计算工具 (精简版) ---
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
        """
        寻找最近的 n 个结构性波段高点和低点
        核心思路：V4.0 的"取最近 N 个转折点"，而非"取 N 个最极端价格"
        """
        if len(self._data_5m) < 20: return
        
        n = 3  # 3高3低
        # 局部确认判定窗口 (增大到 10 根 = 50 分钟，过滤短期噪点)
        window_size = 10
        
        data_list = list(self._data_5m)
        highs = df['high'].values
        lows = df['low'].values
        curr_idx = len(df) - 1
        
        if curr_idx < window_size + 1:
            return

        all_highs = []
        all_lows = []

        # 全量扫描缓存中的所有数据
        for i in range(window_size, curr_idx + 1):
            # --- 低点检测：比左边 window_size 根都低 ---
            if lows[i] <= min(lows[i-window_size:i]):
                is_pivot = False
                if i > curr_idx - window_size:
                    # 实时区：是 i 到当前之间的最低点
                    if i == curr_idx or lows[i] <= min(lows[i+1:]):
                        is_pivot = True
                else:
                    # 确认区：比右边 window_size 根也低
                    if lows[i] < min(lows[i+1 : i+window_size+1]):
                        is_pivot = True
                
                if is_pivot:
                    ts = data_list[i].timestamp.isoformat()
                    all_lows.append({'price': float(lows[i]), 'time': ts, 'index': i})

            # --- 高点检测：比左边 window_size 根都高 ---
            if highs[i] >= max(highs[i-window_size:i]):
                is_pivot = False
                if i > curr_idx - window_size:
                    if i == curr_idx or highs[i] >= max(highs[i+1:]):
                        is_pivot = True
                else:
                    if highs[i] > max(highs[i+1 : i+window_size+1]):
                        is_pivot = True
                
                if is_pivot:
                    ts = data_list[i].timestamp.isoformat()
                    all_highs.append({'price': float(highs[i]), 'time': ts, 'index': i})

        # 取最近 n 个结构转折点 (从右向左，间隔至少 window_size 根防重叠)
        def _get_recent_n(pivots):
            res = []
            for p in reversed(pivots):  # 从最新往回取
                if not res or (res[-1]['index'] - p['index']) >= window_size:
                    res.append(p)
                if len(res) >= n:
                    break
            res.reverse()  # 恢复时间顺序
            return res

        self.state.pivots_high = _get_recent_n(all_highs)
        self.state.pivots_low = _get_recent_n(all_lows)


    def get_status(self, context: Optional[StrategyContext] = None) -> Dict[str, Any]:
        # 计算辅助显示指标
        is_bullish = self.state.macdhist > 0
        macd_trend = "强牛" if is_bullish and self.state.macdhist > self.state.macdhist_prev else "牛市" if is_bullish else "震荡"
        if self.state.macdhist < 0:
            macd_trend = "强熊" if self.state.macdhist < self.state.macdhist_prev else "熊市"
        
        # 信号状态判定 (用于 UI 显示)
        signal_text = "等待趋势"
        signal_color = "neutral"
        signal_strength = "--"

        if self.state.is_halted:
            signal_text = f"熔断: {self.state.halt_reason}"
            signal_color = "sell"
        elif is_bullish:
            signal_color = "buy"
            # 计算信号强度: 基于 RSI 接近程度和 MACD 增长
            rsi_dist = max(0, self.params.get('rsi_buy_threshold', 28) - self.state.current_rsi)
            if self.state.current_rsi < self.params.get('rsi_buy_threshold', 28):
                signal_text = "多头择时买入"
                signal_strength = "强" if rsi_dist > 5 else "高"
            else:
                signal_text = "趋势持有中"
                signal_strength = "中"
        else:
            signal_strength = "弱" if self.state.macdhist < -5 else "低"

        # 量能分析
        vol_current = 0
        vol_trend = "持平"
        if self._data_5m:
            df = pd.DataFrame(list(self._data_5m))
            vol_current = df['volume'].iloc[-1]
            vol_ma = df['volume'].rolling(20).mean().iloc[-1]
            if not np.isnan(vol_ma) and vol_ma > 0:
                ratio = vol_current / vol_ma
                if ratio > 1.5: vol_trend = "放量"
                elif ratio < 0.6: vol_trend = "缩量"

        pos_count = 0
        pos_size = 0.0
        pos_avg_price = 0.0
        pos_unrealized_pnl = 0.0
        if context and self.symbol in context.positions:
            pos = context.positions[self.symbol]
            pos_size = float(pos.size)
            pos_avg_price = float(pos.avg_price)
            pos_unrealized_pnl = float(pos.unrealized_pnl)
            if pos_size > 0:
                # 简单估算层数: 当前持仓对比网格单层期望
                pos_count = max(1, int(pos_size / (self.params.get('total_capital', 10000) / 70000 / 5))) 

        return {
            'name': self.name,
            'current_rsi': round(self.state.current_rsi, 2),
            'macd': round(self.state.macd, 4),
            'macdsignal': round(self.state.macdsignal, 4),
            'macdhist': round(self.state.macdhist, 4),
            'atr': round(self.state.atr, 2),
            'atrVal': round(self.state.atr, 2),
            'macd_trend': macd_trend,
            'signal_text': signal_text,
            'signal_color': signal_color,
            'signal_strength': signal_strength,
            'position_size': pos_size,
            'position_avg_price': pos_avg_price,
            'position_unrealized_pnl': pos_unrealized_pnl,
            'grid_lower': round(self.state.grid_lower, 2),
            'grid_upper': round(self.state.grid_upper, 2),
            'grid_range': f"{self.state.grid_lower:.1f} - {self.state.grid_upper:.1f}",
            'grid_lines': self.state.grid_lines,
            'rsi_oversold': self.params.get('rsi_buy_threshold', 28),
            'rsi_overbought': self.params.get('rsi_sell_threshold', 70),
            'position_count': pos_count,
            'marketRegime': "上升通道" if is_bullish else "震荡下行" if self.state.macdhist < -5 else "调整阶段",
            'vol_trend': vol_trend,
            'current_volume': round(vol_current, 2),
            'is_halted': self.state.is_halted,
            'halt_reason': self.state.halt_reason,
            'pivots': {
                'pivots_high': getattr(self.state, 'pivots_high', []),
                'pivots_low': getattr(self.state, 'pivots_low', [])
            },
            'params': self.params,
            'param_metadata': self.param_metadata
        }
