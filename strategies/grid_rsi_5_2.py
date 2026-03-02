"""
动态网格 RSI 策略 V5.2 (Refactored) — 高性能解耦架构

核心改进 (相较 V5.1):
  1. 架构解耦: IncrementalIndicators / RiskController / GridEngine / DualSignalMatrix
  2. 性能革命: 去 Pandas, O(1) 增量指标, deque 内存优化
  3. 外部JSON配置: 35 参数可被外部 Agent 热更新
  4. 双模式热加载: 定期轮询 + .reload 标记文件主动 Push
"""

from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path
import json, time as _time
import numpy as np
from collections import deque

from core import (
    Signal, MarketData, StrategyContext, FillEvent,
    Side, OrderType, MarketRegime
)
from .base import BaseStrategy

# ============================================================
# 1. 常量
# ============================================================
STRONG_BULLISH = "STRONG_BULLISH"
BULLISH        = "BULLISH"
NEUTRAL        = "NEUTRAL"
BEARISH        = "BEARISH"
STRONG_BEARISH = "STRONG_BEARISH"

_TREND_TO_REGIME = {
    STRONG_BULLISH: MarketRegime.TRENDING_UP,
    BULLISH:        MarketRegime.TRENDING_UP,
    NEUTRAL:        MarketRegime.RANGING,
    BEARISH:        MarketRegime.TRENDING_DOWN,
    STRONG_BEARISH: MarketRegime.TRENDING_DOWN,
}
_TREND_BOOST = {
    STRONG_BULLISH: 0.3, BULLISH: 0.1, NEUTRAL: 0.0,
    BEARISH: -0.2, STRONG_BEARISH: -0.4,
}
_TREND_LABELS = {
    STRONG_BULLISH: "极强牛市 ↑↑", BULLISH: "看涨趋势 ↑",
    NEUTRAL: "中性偏区间 ↔", BEARISH: "看跌趋势 ↓",
    STRONG_BEARISH: "极强熊市 ↓↓",
}

# 默认参数（代码内硬编码保底，JSON
_DEFAULT_PARAMS: Dict[str, Any] = {
    'grid_levels': 10, 'grid_buffer_pct': 0.1,
    'grid_spacing_min': 0.003, 'grid_spacing_max': 0.02,
    'grid_refresh_period': 100,
    'pivot_window': 5, 'pivot_n': 3, 'pivot_lookback': 100,
    'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9,
    'rsi_period': 14, 'rsi_weight': 0.4,
    'rsi_zone_oversold': 35, 'rsi_zone_mid': 50, 'rsi_zone_overbought': 65,
    'rsi_extreme_buy': 75, 'rsi_extreme_sell': 25,
    'atr_period': 14,
    'trend_shift_strong_u': 0.20, 'trend_shift_strong_l': 0.10,
    'trend_shift_weak_u': 0.10, 'trend_shift_weak_l': 0.05,
    'base_position_pct': 0.1, 'max_positions': 5,
    'min_order_usdt': 100.0, 'min_trade_interval_pct': 0.0025,
    'stop_loss_pct': 0.05, 'trailing_stop': True,
    'trailing_stop_pct': 0.02, 'trailing_trigger_pct': 0.05,
    'black_swan_pct': 0.10, 'cooldown_minutes': 15,
    'cycle_reset_period': 5000, 'max_drawdown_reset': 0.30,
}

# 指标引擎重置标记 (修改这些参数需要重置指标)
RESET_PARAMS = {'macd_fast', 'macd_slow', 'macd_signal', 'rsi_period', 'atr_period'}

# ============================================================
# 2. 状态容器 (纯数据，无逻辑)
# ============================================================
@dataclass
class StrategyState:
    last_candle: Optional[Dict[str, float]] = None
    last_trade_ts: float = 0.0
    # 指标
    current_rsi: float = 50.0
    current_atr: float = 0.0
    macd_line: float = 0.0
    signal_line: float = 0.0
    histogram: float = 0.0
    prev_histogram: float = 0.0
    prev_macd_line: float = 0.0
    prev_signal_line: float = 0.0
    trend_strength: str = NEUTRAL
    current_regime: MarketRegime = MarketRegime.UNKNOWN
    # 网格
    grid_upper: Optional[float] = None
    grid_lower: Optional[float] = None
    grid_prices: List[float] = field(default_factory=list)
    grid_touch_count: int = 0
    last_grid_update: int = 0
    actual_levels: int = 10
    pivots: Dict[str, Any] = field(default_factory=dict)
    last_action: str = 'hold'
    # 风控
    conservative_mode: bool = False
    consecutive_conflict: int = 0
    black_swan_pause_until: float = 0.0

# ============================================================
# 3. O(1) 增量指标引擎
# ============================================================
class IncrementalIndicators:
    """流式增量计算: MACD / RSI / ATR，每 tick O(1)。"""
    def __init__(self, p: dict):
        self.p = p
        self.count = 0
        self.ema_fast = self.ema_slow = self.sig_val = self.prev_close = 0.0
        self.avg_gain = self.avg_loss = self.atr_val = 0.0
        self.fa = 2.0 / (p['macd_fast'] + 1)
        self.sa = 2.0 / (p['macd_slow'] + 1)
        self.ga = 2.0 / (p['macd_signal'] + 1)

    def update(self, d: MarketData, s: StrategyState):
        c, h, l = d.close, d.high, d.low
        self.count += 1
        if self.count == 1:
            self.ema_fast = self.ema_slow = self.prev_close = c
            return
        # MACD
        self.ema_fast += (c - self.ema_fast) * self.fa
        self.ema_slow += (c - self.ema_slow) * self.sa
        s.prev_macd_line, s.prev_signal_line = s.macd_line, s.signal_line
        s.macd_line = self.ema_fast - self.ema_slow
        self.sig_val += (s.macd_line - self.sig_val) * self.ga
        s.signal_line = self.sig_val
        s.prev_histogram = s.histogram
        s.histogram = s.macd_line - s.signal_line
        # RSI
        chg = c - self.prev_close
        gain, loss = max(chg, 0.0), max(-chg, 0.0)
        rp = self.p['rsi_period']
        if self.count <= rp:
            self.avg_gain += gain / rp
            self.avg_loss += loss / rp
        else:
            self.avg_gain = (self.avg_gain * (rp - 1) + gain) / rp
            self.avg_loss = (self.avg_loss * (rp - 1) + loss) / rp
        s.current_rsi = (100.0 - 100.0 / (1 + self.avg_gain / self.avg_loss)
                         if self.avg_loss > 1e-12
                         else (100.0 if self.avg_gain > 0 else 50.0))
        # ATR
        tr = max(h - l, abs(h - self.prev_close), abs(l - self.prev_close))
        ap = self.p['atr_period']
        if self.count <= ap:
            self.atr_val += tr / ap
        else:
            self.atr_val = (self.atr_val * (ap - 1) + tr) / ap
        s.current_atr = self.atr_val
        self.prev_close = c

    @property
    def warmup_done(self) -> bool:
        return self.count >= max(self.p['rsi_period'],
                                 self.p['macd_slow'] + self.p['macd_signal'])

# ============================================================
# 4-A. 风控引擎
# ============================================================
class RiskController:
    def __init__(self, p: dict, symbol: str):
        self.p, self.symbol = p, symbol
        self._peaks: Dict[str, float] = {}

    def check_black_swan(self, buf: deque, ts: float, s: StrategyState) -> bool:
        if ts < s.black_swan_pause_until: return True
        if len(buf) < 5: return False
        if buf[-5] > 0 and abs(buf[-1] - buf[-5]) / buf[-5] >= self.p['black_swan_pct']:
            s.black_swan_pause_until = ts + 1800
            return True
        return False

    def check_stop_loss(self, d: MarketData, ctx: StrategyContext, s: StrategyState) -> List[Signal]:
        sigs: List[Signal] = []
        cp = d.close
        for sym, pos in ctx.positions.items():
            if sym != self.symbol: continue
            if pos.size <= 0: continue
            
            # 使用 entry_price 兜底，防止重启后初始峰值为 0 导致立即止损
            pk = self._peaks[sym] = max(self._peaks.get(sym, pos.avg_price), cp)
            
            if pos.avg_price <= 0: continue
            pnl = (cp - pos.avg_price) / pos.avg_price
            
            # 移动止盈: 盈利 > trigger 且 MACD 柱状图收缩
            shrink = abs(s.histogram) < abs(s.prev_histogram) and abs(s.prev_histogram) > 1e-12
            if self.p['trailing_stop'] and pnl >= self.p['trailing_trigger_pct'] and shrink:
                tp = pk * (1 - self.p['trailing_stop_pct'])
                if cp <= tp:
                    sigs.append(self._sell(d, sym, pos.size, f"移动止盈 (Peak:${pk:.2f},PNL:{pnl*100:.1f}%)"))
                    self._peaks.pop(sym, None); continue
            
            # 常规止损 (基于移动峰值或固定均价)
            sl_pct = self.p['stop_loss_pct']
            sp = pk * (1 - self.p['trailing_stop_pct']) if self.p['trailing_stop'] and pnl > 0.01 else pos.avg_price * (1 - sl_pct)
            
            if cp <= sp:
                sigs.append(self._sell(d, sym, pos.size, f"止损(Price:${cp:.2f} <= Limit:${sp:.2f})"))
                self._peaks.pop(sym, None)
        return sigs

    def check_death_cross(self, d: MarketData, ctx: StrategyContext, s: StrategyState) -> List[Signal]:
        if not (s.prev_macd_line > s.prev_signal_line and s.macd_line < s.signal_line): return []
        # 方案A：只在零轴下方的绝对空头趋势中发生死叉才清仓，零轴上方的多头回撤不立刻清仓
        if s.macd_line >= 0: return []
        pos = ctx.positions.get(self.symbol)
        if pos and pos.size > 0:
            self._peaks.pop(self.symbol, None)
            return [self._sell(d, self.symbol, pos.size, f"MACD死叉清仓({s.macd_line:.4f})")]
        return []

    def check_anomaly(self, s: StrategyState, rsi_sig: float):
        bull = s.trend_strength in (STRONG_BULLISH, BULLISH)
        bear = s.trend_strength in (STRONG_BEARISH, BEARISH)
        conflict = (bull and rsi_sig < -0.5) or (bear and rsi_sig > 0.5)
        s.consecutive_conflict = s.consecutive_conflict + 1 if conflict else max(0, s.consecutive_conflict - 1)
        s.conservative_mode = s.consecutive_conflict >= 3

    def is_in_cooldown(self, ts: float, s: StrategyState) -> bool:
        return s.last_trade_ts > 0 and (ts - s.last_trade_ts) / 60 < self.p['cooldown_minutes']

    @staticmethod
    def _sell(d: MarketData, sym: str, size: float, reason: str) -> Signal:
        return Signal(timestamp=d.timestamp, symbol=sym, side=Side.SELL,
                      size=size, price=None, order_type=OrderType.MARKET,
                      reason=reason, meta={'size_in_quote': False})

# ============================================================
# 4-B. 网格引擎
# ============================================================
class GridEngine:
    def __init__(self, p: dict):
        self.p = p

    def find_pivots(self, highs: np.ndarray, lows: np.ndarray, times: Optional[List[float]] = None) -> Tuple[list, list]:
        w, n, lb = self.p['pivot_window'], self.p['pivot_n'], self.p['pivot_lookback']
        if len(highs) < w + 1: return [], []
        end = len(highs) - 1
        ph, pl = [], []  # pivot highs, pivot lows
        for i in range(end, max(w, end - lb), -1):
            if len(pl) < n and lows[i] <= float(np.min(lows[max(0, i-w):i])):
                ok, tp = self._check_pivot(lows, i, end, w, is_low=True)
                if ok and (not pl or abs(lows[i] - pl[-1]['price']) > lows[i] * 0.001):
                    p_data = {'price': float(lows[i]), 'index': i, 'type': tp}
                    if times and i < len(times): p_data['time'] = times[i]
                    pl.append(p_data)
            if len(ph) < n and highs[i] >= float(np.max(highs[max(0, i-w):i])):
                ok, tp = self._check_pivot(highs, i, end, w, is_low=False)
                if ok and (not ph or abs(highs[i] - ph[-1]['price']) > highs[i] * 0.001):
                    p_data = {'price': float(highs[i]), 'index': i, 'type': tp}
                    if times and i < len(times): p_data['time'] = times[i]
                    ph.append(p_data)
            if len(ph) >= n and len(pl) >= n: break
        return ph, pl

    @staticmethod
    def _check_pivot(arr, i, end, w, is_low) -> Tuple[bool, str]:
        cmp = np.min if is_low else np.max
        op = (lambda a, b: a <= b) if is_low else (lambda a, b: a >= b)
        strict = (lambda a, b: a < b) if is_low else (lambda a, b: a > b)
        if i > end - w:
            return (op(arr[i], float(cmp(arr[i+1:end+1]))) if i < end else True), 'realtime'
        return strict(arr[i], float(cmp(arr[i+1:i+w+1]))), 'confirmed'

    def calculate(self, highs: np.ndarray, lows: np.ndarray,
                  price: float, s: StrategyState,
                  rsi_sig: float, times: Optional[List[float]] = None) -> Tuple[float, float, dict]:
        ph, pl = self.find_pivots(highs, lows, times)
        if not ph or not pl:
            lb = min(self.p['grid_refresh_period'], len(highs))
            upper, lower = float(np.max(highs[-lb:])), float(np.min(lows[-lb:]))
        else:
            upper = max(p['price'] for p in ph)
            lower = min(p['price'] for p in pl)
        rng = upper - lower if upper > lower else upper * 0.01
        # ATR 自适应间距
        atr_sp = s.current_atr / price if s.current_atr > 0 and price > 0 else 0
        spacing = np.clip(atr_sp, self.p['grid_spacing_min'], self.p['grid_spacing_max'])
        
        # 强制最小网格跨度，防止 Pivot 找到的极震荡区间导致网格过度密集
        min_rng = price * spacing * (self.p['grid_levels'] - 1)
        if rng < min_rng:
            mid = (upper + lower) / 2
            upper = mid + min_rng / 2
            lower = mid - min_rng / 2
            rng = min_rng
            
        # 根据动态扩充后实际跨度和间距计算合理的动态刻度数
        dyn_num = max(3, int(rng / (price * spacing)) + 1)
        
        buf = rng * self.p['grid_buffer_pct']
        upper += buf; lower -= buf
        # MACD 趋势偏移
        p = self.p
        ts = s.trend_strength
        if ts == STRONG_BULLISH:
            upper += (upper - price) * p['trend_shift_strong_u']
            lower += (price - lower) * p['trend_shift_strong_l']
        elif ts == BULLISH:
            upper += (upper - price) * p['trend_shift_weak_u']
            lower += (price - lower) * p['trend_shift_weak_l']
        elif ts == BEARISH:
            upper -= (upper - price) * p['trend_shift_weak_l']
            lower -= (price - lower) * p['trend_shift_weak_u']
        elif ts == STRONG_BEARISH:
            upper -= (upper - price) * p['trend_shift_strong_l']
            lower -= (price - lower) * p['trend_shift_strong_u']
        # RSI 微调
        if self.p['rsi_weight'] > 0:
            shift = rng * rsi_sig * self.p['rsi_weight'] * 0.2
            upper += shift; lower += shift
        return upper, lower, {'pivots_high': ph, 'pivots_low': pl,
                              'atr_spacing': float(spacing), 'dynamic_grid_num': dyn_num}

# ============================================================
# 4-C. 双指标矩阵
# ============================================================
_DUAL_MATRIX = {
    (STRONG_BULLISH, 'os'): (5,'heavy_buy'), (STRONG_BULLISH, 'wk'): (4,'buy'),
    (STRONG_BULLISH, 'nt'): (3,'light_buy'), (STRONG_BULLISH, 'ob'): (2,'hold'),
    (BULLISH, 'os'): (4,'buy'),   (BULLISH, 'wk'): (3,'buy'),
    (BULLISH, 'nt'): (2,'light_buy'), (BULLISH, 'ob'): (1,'hold'),
    (NEUTRAL, 'os'): (3,'light_buy'), (NEUTRAL, 'wk'): (2,'hold'),
    (NEUTRAL, 'nt'): (1,'hold'),  (NEUTRAL, 'ob'): (1,'reduce'),
    (BEARISH, 'os'): (2,'light_buy'), (BEARISH, 'wk'): (1,'stop'),
    (BEARISH, 'nt'): (0,'stop'),  (BEARISH, 'ob'): (2,'sell'),
    (STRONG_BEARISH, 'os'): (1,'hold'), (STRONG_BEARISH, 'wk'): (0,'stop'),
    (STRONG_BEARISH, 'nt'): (0,'stop'), (STRONG_BEARISH, 'ob'): (3,'sell'),
}

def dual_evaluate(trend: str, rsi: float, p: dict) -> Tuple[int, str]:
    zones = [('os', p['rsi_zone_oversold']), ('wk', p['rsi_zone_mid']),
             ('nt', p['rsi_zone_overbought'])]
    z = 'ob'
    for code, thr in zones:
        if rsi < thr: z = code; break
    return _DUAL_MATRIX.get((trend, z), (0, 'hold'))

# ============================================================
# 5. 策略主类
# ============================================================
class GridRSIStrategyV5_2(BaseStrategy):
    """动态网格 RSI 策略 V5.2 — 高性能解耦 + JSON 热加载"""

    def __init__(self, symbol: str = "BTC-USDT",
                 config_path: Optional[str] = None, **overrides):
        super().__init__(name="GridRSI_V5.2")
        self.symbol = symbol

        # 三层优先级: 默认值 < JSON 文件 < 代码传参
        self._config_path = Path(config_path) if config_path else None
        self._last_config_mtime: float = 0.0
        self._tick_since_check: int = 0
        self.params: Dict[str, Any] = {**_DEFAULT_PARAMS}
        self.params_path = self._config_path # 兼容性属性
        self._apply_config_file()
        self.params.update({k: v for k, v in overrides.items() if k in _DEFAULT_PARAMS})

        # 元数据加载
        self.param_metadata: Dict[str, Any] = {}
        self._load_param_metadata()

        # 组件实例化
        self.state = StrategyState()
        self.indicators = IncrementalIndicators(self.params)
        self.risk_ctrl = RiskController(self.params, self.symbol)
        self.grid_engine = GridEngine(self.params)

        # deque 缓冲
        buf = max(self.params['macd_slow'] + self.params['macd_signal'],
                  self.params['rsi_period'], self.params['atr_period']) * 3 + 100
        self._close_buf: deque = deque(maxlen=buf)
        self._high_buf:  deque = deque(maxlen=buf)
        self._low_buf:   deque = deque(maxlen=buf)
        self._data_buffer: deque = deque(maxlen=buf) # 兼容性: 存储 MarketData 对象
        self._current_prices: Dict[str, float] = {}
        self._equity_history: deque = deque(maxlen=5000)

    # ── 配置热加载 ──
    def _apply_config_file(self):
        if not self._config_path or not self._config_path.exists():
            return
        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 更新参数
            self.params.update({k: v for k, v in data.items() if k in _DEFAULT_PARAMS or k == 'symbol'})
            # 如果配置中有 symbol，同步更新策略实例的 symbol 属性
            if 'symbol' in data:
                self.symbol = data['symbol']
            self._last_config_mtime = self._config_path.stat().st_mtime
        except Exception as e:
            print(f"[V5.2] 配置加载失败: {e}")

    def _load_param_metadata(self):
        """加载参数说明元数据 (从 JSON)"""
        if not self.params_path: return
        meta_path = self.params_path.with_name(self.params_path.stem.replace('_default', '') + '_meta.json')
        if not meta_path.exists():
            # 兜底：尝试固定名称
            meta_path = self.params_path.parent / "grid_v52_meta.json"
            
        if meta_path.exists():
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    self.param_metadata = json.load(f)
                    print(f"[V5.2] 成功加载参数元数据说明: {meta_path.name}")
            except Exception as e:
                print(f"[V5.2] 加载参数元数据失败: {e}")

    def _maybe_reload_params(self):
        if not self._config_path: return
        reload_flag = self._config_path.with_suffix('.reload')
        need_reload = False
        # 主动 Push: Agent 创建了 .reload 文件
        if reload_flag.exists():
            need_reload = True
            try: reload_flag.unlink()
            except: pass
        # 被动轮询: 每 100 tick
        if not need_reload:
            self._tick_since_check += 1
            if self._tick_since_check >= 100:
                self._tick_since_check = 0
                try:
                    mt = self._config_path.stat().st_mtime
                    if mt > self._last_config_mtime:
                        need_reload = True
                except: pass
        if need_reload:
            # 备份旧的核心参数用于对此
            old = {k: self.params.get(k) for k in RESET_PARAMS}
            self._apply_config_file()
            # 如果引擎相关参数变了，重建指标引擎
            if any(self.params.get(k) != old.get(k) for k in RESET_PARAMS):
                self.indicators = IncrementalIndicators(self.params)
                print(f"[V5.2] 核心指标参数变更，指标引擎已重建")
            # 同步组件引用
            self.risk_ctrl.p = self.params
            self.grid_engine.p = self.params
            cfg_name = self._config_path.name if self._config_path else "Unknown"
            print(f"[V5.2] 参数已热加载 ({cfg_name})")

    # ── 初始化 ──
    def initialize(self):
        super().initialize()
        n = len(self._close_buf)
        self.state = StrategyState()
        self.indicators = IncrementalIndicators(self.params)
        self.risk_ctrl = RiskController(self.params, self.symbol)
        self._equity_history.clear()
        self._data_buffer.clear() # 也要清理数据缓冲
        print(f"[V5.2] 逻辑重置 (缓冲保留:{n}根)")

    def _update_buffer(self, data: MarketData):
        """核心状态更新 (O(1) 增量更新，不生成信号)"""
        self._close_buf.append(data.close)
        self._high_buf.append(data.high)
        self._low_buf.append(data.low)
        self._data_buffer.append(data) # 记录全量数据对象
        self._current_prices[self.symbol] = data.close
        self.indicators.update(data, self.state)

    def _get_dataframe(self):
        """兼容性方法: 将 deque 转换为 DataFrame"""
        import pandas as pd
        if not self._data_buffer: return pd.DataFrame()
        recs = []
        for d in self._data_buffer:
            recs.append({
                'timestamp': d.timestamp, 'open': d.open, 'high': d.high,
                'low': d.low, 'close': d.close, 'volume': d.volume
            })
        df = pd.DataFrame(recs)
        df.set_index('timestamp', inplace=True)
        return df

    def _calculate_dynamic_grid(self, df=None, **kwargs):
        """兼容性接口: 包装 GridEngine 的 calculate 方法"""
        # 如果提供了 df，优先使用 df
        if df is not None:
            h, l, c = df['high'].values, df['low'].values, df['close'].values[-1]
        else:
            h, l, c = np.array(self._high_buf), np.array(self._low_buf), self._close_buf[-1] if self._close_buf else 0
        
        # 为了满足 LiveEngine 对返回值 (upper, lower, meta) 的解构需求
        # 注意: GridEngine.calculate 需要 rsi_sig 参与平衡，预热时传 0
        up, lo, meta = self.grid_engine.calculate(h, l, c, self.state, 0.0)
        return up, lo, meta

    # ── 趋势判别 ──
    def _update_trend(self):
        h, ph = self.state.histogram, self.state.prev_histogram
        exp = abs(h) > abs(ph) if abs(ph) > 1e-12 else False
        if abs(h) < 1e-9:
            self.state.trend_strength = NEUTRAL
        elif self.state.macd_line > self.state.signal_line and h > 0:
            self.state.trend_strength = STRONG_BULLISH if exp else BULLISH
        elif self.state.macd_line < self.state.signal_line and h < 0:
            self.state.trend_strength = STRONG_BEARISH if exp else BEARISH
        else:
            self.state.trend_strength = NEUTRAL
        self.state.current_regime = _TREND_TO_REGIME.get(self.state.trend_strength, MarketRegime.RANGING)

    # ── RSI 信号 ──
    def _rsi_signal(self) -> Tuple[float, float, float]:
        p = self.params
        os, ob = p['rsi_zone_oversold'], p['rsi_zone_overbought']
        # 自适应阈值
        if len(self._close_buf) >= 20:
            c = np.array(self._close_buf)
            vol = float(np.std(np.diff(c) / c[:-1])) * np.sqrt(1440)
            vf = np.clip(vol / 0.5, 0.5, 2.0)
            os = np.clip(p['rsi_zone_oversold'] / vf, 20, 40)
            ob = np.clip(100 - (100 - p['rsi_zone_overbought']) / vf, 60, 80)
        rsi = self.state.current_rsi
        mid = p['rsi_zone_mid']
        if rsi <= os:   sig = 1.0
        elif rsi >= ob: sig = -1.0
        elif rsi < mid: sig = (mid - rsi) / (mid - os) * 0.5
        else:           sig = (mid - rsi) / (ob - mid) * 0.5
        return sig, float(os), float(ob)

    # ── 仓位计算 ──
    def _calc_size(self, ctx: StrategyContext, rsi_sig: float, is_buy: bool) -> float:
        n = max(1, len(self.state.grid_prices))
        sz = ctx.total_value / n * (1 + _TREND_BOOST.get(self.state.trend_strength, 0))
        sz *= 1 - abs(self.state.current_rsi - 50) / 100  # RSI 偏离折扣
        if is_buy and self.state.macd_line < 0: sz *= 0.5
        if self.state.conservative_mode: sz *= 0.5
        return min(max(sz, self.params['min_order_usdt']), ctx.cash * 0.95)

    def _pos_layers(self, ctx: StrategyContext, cp: float) -> int:
        pos = ctx.positions.get(self.symbol)
        if not pos or pos.size <= 0: return 0
        sz_per_layer = self._calc_size(ctx, 0, True) # USDT 价值
        # 修正单位错误: 将 BTC 数量 * 当前价格 换算回 USDT 再计算层数
        pos_val = pos.size * cp
        return max(1, int(round(pos_val / sz_per_layer)))

    # ── 周期重置 ──
    def _check_reset(self, ctx: StrategyContext) -> Tuple[bool, str]:
        if len(self._close_buf) - self.state.last_grid_update >= self.params['cycle_reset_period']:
            return True, "强制重置周期"
        if self._equity_history:
            pk = max(self._equity_history)
            if pk > 0:
                dd = (self._equity_history[-1] - pk) / pk
                if dd <= -self.params['max_drawdown_reset']:
                    return True, f"最大回撤({dd:.2%})"
        return False, ""

    # ── 网格交易信号 ──
    def _grid_orders(self, d: MarketData, ctx: StrategyContext,
                     action: str, strength: int, rsi_sig: float) -> List[Signal]:
        sigs: List[Signal] = []
        p, s = self.params, self.state
        cp, ch, cl = d.close, d.high, d.low
        if not s.grid_prices or not s.last_candle: return sigs

        # 最小间距
        min_iv = p['min_trade_interval_pct']
        gip = min_iv
        if s.grid_upper and s.grid_lower and s.actual_levels > 1 and cp > 0:
            gi = abs(s.grid_upper - s.grid_lower) / (s.actual_levels - 1)
            gip = np.clip((gi / cp) * 0.8, min_iv, 0.02)

        lh, ll = s.last_candle['high'], s.last_candle['low']

        # 买入
        for gp in s.grid_prices:
            if ll > gp and cl <= gp:
                if action not in ('heavy_buy', 'buy', 'light_buy'): continue
                if self._pos_layers(ctx, cp) >= p['max_positions']: continue
                if s.current_rsi >= p['rsi_extreme_buy']: continue
                pos = ctx.positions.get(self.symbol)
                if pos and pos.size > 0 and cp > pos.avg_price * (1 - gip): continue
                sz = self._calc_size(ctx, rsi_sig, True)
                if sz > ctx.cash * 0.95: continue
                if action == 'light_buy': sz = max(sz * 0.5, p['min_order_usdt'])
                sigs.append(Signal(
                    timestamp=d.timestamp, symbol=self.symbol, side=Side.BUY,
                    size=sz, price=None, order_type=OrderType.MARKET,
                    confidence=abs(rsi_sig),
                    reason=f"网格买入@{gp:.2f}(RSI:{s.current_rsi:.1f} {s.trend_strength} ★{strength})",
                    meta={'size_in_quote': True}))
                break

        # 卖出
        for gp in s.grid_prices:
            if lh < gp and ch >= gp:
                pos = ctx.positions.get(self.symbol)
                if not pos or pos.size <= 0: continue
                profitable = pos.avg_price < cp * (1 - gip)
                if action in ('sell', 'reduce') or profitable:
                    if s.current_rsi <= p['rsi_extreme_sell']: continue
                    layers = self._pos_layers(ctx, cp)
                    sz = min(pos.size, pos.size / max(1, layers))
                    if action == 'reduce': sz *= 0.5
                    sigs.append(Signal(
                        timestamp=d.timestamp, symbol=self.symbol, side=Side.SELL,
                        size=sz, price=None, order_type=OrderType.MARKET,
                        confidence=abs(rsi_sig),
                        reason=f"网格卖出@{gp:.2f}(RSI:{s.current_rsi:.1f} {s.trend_strength} ★{strength})",
                        meta={'size_in_quote': False}))
                    break
        return sigs

    # ══════════════════════════════════════════════
    # on_data 主循环
    # ══════════════════════════════════════════════
    def on_data(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        signals: List[Signal] = []
        try: ts = data.timestamp.timestamp()
        except: ts = _time.time()

        # 0. 热加载检查
        self._maybe_reload_params()

        # 1 & 2. 缓冲与指标更新 (复用兼容性方法)
        self._update_buffer(data)

        # 检查预热是否完成 (IncrementalIndicators 的逻辑)
        if not self.indicators.warmup_done:
            self.state.last_candle = {'open': data.open, 'high': data.high, 'low': data.low, 'close': data.close}
            return []

        # 3. 趋势
        self._update_trend()

        # 4. RSI
        rsi_sig, oversold, overbought = self._rsi_signal()

        # 5. 网格
        h_arr, l_arr = np.array(self._high_buf), np.array(self._low_buf)
        t_arr = [d.timestamp.isoformat() if hasattr(d.timestamp, 'isoformat') else d.timestamp for d in self._data_buffer]
        upper, lower, meta = self.grid_engine.calculate(h_arr, l_arr, data.close, self.state, rsi_sig, t_arr)
        dyn = meta.get('dynamic_grid_num', self.params['grid_levels'])
        al = max(3, min(dyn, self.params['grid_levels'] * 3))
        self.state.grid_upper, self.state.grid_lower = upper, lower
        self.state.grid_prices = np.linspace(lower, upper, al).tolist()
        self.state.last_grid_update = len(self._close_buf)
        self.state.pivots = meta
        self.state.actual_levels = al

        # 6. 风控
        self.risk_ctrl.check_anomaly(self.state, rsi_sig)
        if self.risk_ctrl.check_black_swan(self._close_buf, ts, self.state):
            for sym, pos in context.positions.items():
                if sym == self.symbol and pos.size > 0:
                    signals.append(RiskController._sell(data, sym, pos.size, "黑天鹅紧急止损"))
            self.state.last_candle = {'open': data.open, 'high': data.high, 'low': data.low, 'close': data.close}
            return signals

        ok, reason = self._check_reset(context)
        if ok:
            for sym, pos in context.positions.items():
                if sym == self.symbol and pos.size > 0:
                    signals.append(RiskController._sell(data, sym, pos.size, f"周期重置:{reason}"))
            self.state.grid_upper = self.state.grid_lower = None
            self.state.last_grid_update = len(self._close_buf)
            self.state.conservative_mode = False; self.state.consecutive_conflict = 0

        signals.extend(self.risk_ctrl.check_stop_loss(data, context, self.state))
        signals.extend(self.risk_ctrl.check_death_cross(data, context, self.state))

        # 7. 矩阵 + 网格触发
        strength, action = dual_evaluate(self.state.trend_strength, self.state.current_rsi, self.params)
        self.state.last_action = action
        if not self.risk_ctrl.is_in_cooldown(ts, self.state):
            signals.extend(self._grid_orders(data, context, action, strength, rsi_sig))

        self.state.last_candle = {'open': data.open, 'high': data.high, 'low': data.low, 'close': data.close}
        return signals

    def on_fill(self, fill: FillEvent):
        if fill.side == Side.BUY: self.state.grid_touch_count += 1
        try: self.state.last_trade_ts = fill.timestamp.timestamp()
        except: self.state.last_trade_ts = _time.time()

    # ── 状态报告 ──
    def get_status(self, context: Optional[StrategyContext] = None) -> Dict[str, Any]:
        s, p = self.state, self.params
        rsi_sig, os_v, ob_v = self._rsi_signal()
        strength, action = dual_evaluate(s.trend_strength, s.current_rsi, p)
        # 信号文字
        _ACT_TEXT = {
            'heavy_buy': ('buy', lambda st, rs: f"买入信号 ★{st} ({rs:+.2f})"),
            'buy':       ('buy', lambda st, rs: f"买入信号 ★{st} ({rs:+.2f})"),
            'light_buy': ('buy', lambda st, rs: f"轻仓买入 ★{st} ({rs:+.2f})"),
            'sell':      ('sell', lambda st, rs: f"卖出信号 ★{st} ({rs:+.2f})"),
            'reduce':    ('sell', lambda st, rs: f"卖出信号 ★{st} ({rs:+.2f})"),
            'stop':      ('sell', lambda st, rs: "停止交易"),
        }
        color, fmt = _ACT_TEXT.get(action, ('neutral', lambda st, rs: "观望"))
        cp = self._current_prices.get(self.symbol, 0)
        in_grid = ""
        if s.grid_lower is not None and s.grid_upper is not None and cp > 0:
            in_grid = "低于网格" if cp < s.grid_lower else ("高于网格" if cp > s.grid_upper else "网格内")
        pos_count = self._pos_layers(context, cp) if context and self.symbol in context.positions else 0
        pos_obj = context.positions.get(self.symbol) if context else None
        
        return {
            'grid_upper': s.grid_upper or 0, 'grid_lower': s.grid_lower or 0,
            'grid_count': len(s.grid_prices), 'grid_lines': s.grid_prices,
            'max_positions': p['max_positions'], 'position_count': pos_count,
            'position_size': pos_obj.size if pos_obj else 0.0,
            'position_avg_price': pos_obj.avg_price if pos_obj else 0.0,
            'position_unrealized_pnl': pos_obj.unrealized_pnl if pos_obj else 0.0,
            'current_rsi': s.current_rsi, 'rsi_oversold': os_v, 'rsi_overbought': ob_v,
            'rsi_signal': rsi_sig,
            'market_regime': s.current_regime.value,
            'signal_text': fmt(strength, rsi_sig), 'signal_color': color,
            'action_intent': s.last_action, 'in_grid': in_grid,
            'trade_executed': False, 'grid_touch_count': s.grid_touch_count,
            'pivots': s.pivots, 'params': {**p, 'symbol': self.symbol},
            'macd': s.macd_line, 'macdsignal': s.signal_line, 'macdhist': s.histogram,
            'macd_trend': _TREND_LABELS.get(s.trend_strength, "未知"),
            'trend_strength': s.trend_strength, 'current_atr': s.current_atr,
            'dual_strength': strength, 'dual_action': action,
            'conservative_mode': s.conservative_mode,
            'param_metadata': getattr(self, 'param_metadata', {}),
        }
