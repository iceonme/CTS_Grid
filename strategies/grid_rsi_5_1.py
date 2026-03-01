"""
动态网格 RSI 策略 V5.1 — MACD+RSI 双指标确认系统

核心改进（相较 V4.0 / 原始隔离原型）:
  1. MACD(12,26,9) 定方向 → 5 级趋势分类
  2. RSI(14) 找入场 → 阈值 65/35（加密货币高波动适配）
  3. 双指标确认矩阵 → 仅趋势+动量一致时才开仓
  4. ATR 自适应网格间距 (0.3%~2.0%)
  5. 趋势强度系数 + RSI 偏离折扣的动态仓位
  6. 多层风控: RSI>75 禁买 / MACD<0 减仓 / 冷却期 / 黑天鹅检测
  7. 移动止盈: MACD 柱状图收缩 + RSI 顶背离触发
"""

from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass, field
import time as _time
import pandas as pd
import numpy as np

from core import (
    Signal, MarketData, StrategyContext, FillEvent,
    Side, OrderType, MarketRegime
)
from .base import BaseStrategy


# ── 趋势强度枚举 ────────────────────────────────────────────
STRONG_BULLISH = "STRONG_BULLISH"
BULLISH        = "BULLISH"
NEUTRAL        = "NEUTRAL"
BEARISH        = "BEARISH"
STRONG_BEARISH = "STRONG_BEARISH"

# 趋势强度 → MarketRegime 映射
_TREND_TO_REGIME = {
    STRONG_BULLISH: MarketRegime.TRENDING_UP,
    BULLISH:        MarketRegime.TRENDING_UP,
    NEUTRAL:        MarketRegime.RANGING,
    BEARISH:        MarketRegime.TRENDING_DOWN,
    STRONG_BEARISH: MarketRegime.TRENDING_DOWN,
}

# 趋势强度 → 仓位系数
_TREND_BOOST = {
    STRONG_BULLISH: 0.3,
    BULLISH:        0.1,
    NEUTRAL:        0.0,
    BEARISH:       -0.2,
    STRONG_BEARISH:-0.4,
}


@dataclass
class GridStateV5_1:
    """策略运行时状态（不含账户真相）"""
    grid_upper: Optional[float] = None
    grid_lower: Optional[float] = None
    grid_prices: List[float] = field(default_factory=list)
    last_grid_update: int = 0
    current_rsi: float = 50.0
    current_adx: float = 0.0
    current_regime: MarketRegime = MarketRegime.UNKNOWN
    last_candle: Optional[Dict[str, float]] = None

    # MACD 指标
    macd_line: float = 0.0
    signal_line: float = 0.0
    histogram: float = 0.0
    prev_histogram: float = 0.0        # 上一周期柱状图，用于收缩/扩大判断
    trend_strength: str = NEUTRAL       # 5 级趋势

    # ATR
    current_atr: float = 0.0

    # 风控
    last_trade_ts: float = 0.0          # 上次交易的 epoch 秒
    consecutive_conflict: int = 0       # MACD/RSI 信号连续冲突次数
    conservative_mode: bool = False     # 保守模式
    black_swan_pause_until: float = 0.0 # 黑天鹅暂停截止时间 (epoch秒)
    prev_macd_line: float = 0.0         # 上一周期 MACD 线，用于死叉判断
    prev_signal_line: float = 0.0       # 上一周期信号线

    # 统计
    grid_touch_count: int = 0
    actual_levels: int = 10             # V5.1 新增：记录当前生成的网格数量
    pivots: Dict[str, Any] = field(default_factory=dict) # V5.1 新增：存储波段点历史


class GridRSIStrategyV5_1(BaseStrategy):
    """动态网格 RSI 策略 V5.1 — MACD+RSI 双指标确认"""

    def __init__(self,
                 symbol: str = "BTC-USDT",
                 # 网格参数
                 grid_levels: int = 10,
                 grid_refresh_period: int = 100,
                 grid_buffer_pct: float = 0.1,
                 # MACD 参数
                 macd_fast: int = 12,
                 macd_slow: int = 26,
                 macd_signal: int = 9,
                 # RSI 参数
                 rsi_period: int = 14,
                 rsi_weight: float = 0.4,
                 rsi_oversold: float = 35,
                 rsi_overbought: float = 65,
                 rsi_extreme_buy: float = 75,       # V5.1: RSI>75 禁止买入
                 rsi_extreme_sell: float = 25,       # V5.1: RSI<25 加仓信号
                 adaptive_rsi: bool = True,
                 # ATR 参数
                 atr_period: int = 14,
                 grid_spacing_min: float = 0.003,    # 最小间距 0.3%
                 grid_spacing_max: float = 0.02,     # 最大间距 2.0%
                 # 趋势参数 (保留旧字段以兼容)
                 use_trend_filter: bool = True,
                 adx_period: int = 14,
                 adx_threshold: float = 25,
                 ma_period: int = 50,
                 # 仓位参数
                 base_position_pct: float = 0.1,
                 max_positions: int = 5,
                 use_kelly_sizing: bool = False,     # V5.1 默认关闭 Kelly，改用趋势系数
                 kelly_fraction: float = 0.3,
                 max_position_multiplier: float = 2.0,
                 min_position_multiplier: float = 0.5,
                 # 止损参数
                 stop_loss_pct: float = 0.05,
                 trailing_stop: bool = True,
                 trailing_stop_pct: float = 0.02,    # V5.1: 2% 回撤止盈
                 trailing_trigger_pct: float = 0.05, # V5.1: 5% 盈利触发
                 # 风控参数
                 max_drawdown: float = 0.15,
                 daily_loss_limit: float = 0.05,
                 grid_loss_limit: float = 0.02,
                 cooldown_minutes: float = 15,       # V5.1: 冷却 15 分钟
                 black_swan_pct: float = 0.10,       # 5 分钟内 10% 波动
                 # 周期参数
                 cycle_reset_period: int = 5000,
                 max_drawdown_reset: float = 0.30,
                 # 最小交易金额
                 min_order_usdt: float = 100.0,
                 **kwargs):
        super().__init__(name="GridRSI_V5.1", **kwargs)

        self.symbol = symbol
        self.params = {
            'grid_levels': grid_levels,
            'grid_refresh_period': grid_refresh_period,
            'grid_buffer_pct': grid_buffer_pct,
            # MACD
            'macd_fast': macd_fast,
            'macd_slow': macd_slow,
            'macd_signal': macd_signal,
            # RSI
            'rsi_period': rsi_period,
            'rsi_weight': rsi_weight,
            'rsi_oversold': rsi_oversold,
            'rsi_overbought': rsi_overbought,
            'rsi_extreme_buy': rsi_extreme_buy,
            'rsi_extreme_sell': rsi_extreme_sell,
            'adaptive_rsi': adaptive_rsi,
            # ATR
            'atr_period': atr_period,
            'grid_spacing_min': grid_spacing_min,
            'grid_spacing_max': grid_spacing_max,
            # 趋势 (兼容旧参数)
            'use_trend_filter': use_trend_filter,
            'adx_period': adx_period,
            'adx_threshold': adx_threshold,
            'ma_period': ma_period,
            # 仓位
            'base_position_pct': base_position_pct,
            'max_positions': max_positions,
            'use_kelly_sizing': use_kelly_sizing,
            'kelly_fraction': kelly_fraction,
            'max_position_multiplier': max_position_multiplier,
            'min_position_multiplier': min_position_multiplier,
            # 止损/止盈
            'stop_loss_pct': stop_loss_pct,
            'trailing_stop': trailing_stop,
            'trailing_stop_pct': trailing_stop_pct,
            'trailing_trigger_pct': trailing_trigger_pct,
            # 风控
            'max_drawdown': max_drawdown,
            'daily_loss_limit': daily_loss_limit,
            'grid_loss_limit': grid_loss_limit,
            'cooldown_minutes': cooldown_minutes,
            'black_swan_pct': black_swan_pct,
            # 周期
            'cycle_reset_period': cycle_reset_period,
            'max_drawdown_reset': max_drawdown_reset,
            'min_order_usdt': min_order_usdt,
            'min_trade_interval_pct': kwargs.get('min_trade_interval_pct', 0.0025),
        }

        self.state = GridStateV5_1()

        self._data_buffer: List[MarketData] = []
        self._max_buffer_size = max(macd_slow + macd_signal, ma_period, rsi_period, adx_period, atr_period) * 3 + 100
        self._peak_prices: Dict[str, float] = {}
        self._current_prices: Dict[str, float] = {}
        self._equity_history: List[float] = []

    # ──────────────────────────────────────────────────────────
    # 初始化 & 数据缓冲
    # ──────────────────────────────────────────────────────────

    def initialize(self):
        """策略初始化：保留行情缓冲区，仅重置账户相关状态"""
        super().initialize()
        
        # 保留 self._data_buffer ！！！
        # 仅重置与当前交易周期相关的状态
        self.state = GridStateV5_1()
        
        # 保留 self._peak_prices 和 self._current_prices 以维持 UI 响应
        # 但清空权益历史，因为账户已经资金重置
        self._equity_history.clear()
        
        print(f"[Strategy:{self.name}] 已执行逻辑重置 (行情缓冲区保留: {len(self._data_buffer)} 根)")

    def _update_buffer(self, data: MarketData):
        self._current_prices[self.symbol] = data.close
        if self._data_buffer and self._data_buffer[-1].timestamp == data.timestamp:
            self._data_buffer[-1] = data
        else:
            self._data_buffer.append(data)
            if len(self._data_buffer) > self._max_buffer_size:
                self._data_buffer.pop(0)

    def _get_dataframe(self) -> pd.DataFrame:
        if len(self._data_buffer) < 2:
            return pd.DataFrame()

        data = {
            'open':   [d.open   for d in self._data_buffer],
            'high':   [d.high   for d in self._data_buffer],
            'low':    [d.low    for d in self._data_buffer],
            'close':  [d.close  for d in self._data_buffer],
            'volume': [d.volume for d in self._data_buffer],
        }
        index = [d.timestamp for d in self._data_buffer]
        return pd.DataFrame(data, index=index)

    # ──────────────────────────────────────────────────────────
    # 指标计算
    # ──────────────────────────────────────────────────────────

    def _calculate_rsi(self, prices: pd.Series) -> float:
        period = self.params['rsi_period']
        if len(prices) < period + 1:
            return 50.0

        delta = prices.diff()
        gain  = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss  = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs    = gain / loss.replace(0, np.nan)
        rsi   = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50.0

    def _calculate_macd(self, df: pd.DataFrame) -> Tuple[float, float, float]:
        """计算 MACD(fast, slow, signal)，返回 (macd_line, signal_line, histogram)."""
        fast   = self.params['macd_fast']
        slow   = self.params['macd_slow']
        signal = self.params['macd_signal']

        if len(df) < slow + signal:
            return 0.0, 0.0, 0.0

        close = df['close']
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line

        ml = macd_line.iloc[-1]
        sl = signal_line.iloc[-1]
        hi = histogram.iloc[-1]
        return (
            ml if not pd.isna(ml) else 0.0,
            sl if not pd.isna(sl) else 0.0,
            hi if not pd.isna(hi) else 0.0,
        )

    def _calculate_atr(self, df: pd.DataFrame) -> float:
        """计算 ATR(period)."""
        period = self.params['atr_period']
        if len(df) < period + 1:
            return 0.0

        high, low, close = df['high'], df['low'], df['close']
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low  - close.shift(1))
        tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        val = atr.iloc[-1]
        return val if not pd.isna(val) else 0.0

    def _calculate_adx(self, df: pd.DataFrame) -> float:
        """保留 ADX 计算用于 get_status() 辅助展示."""
        period = self.params['adx_period']
        if len(df) < period * 2:
            return 0.0

        high, low, close = df['high'], df['low'], df['close']
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low  - close.shift(1))
        tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        plus_dm  = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm   < 0] = 0
        minus_dm[minus_dm < 0] = 0

        atr      = tr.rolling(window=period).mean()
        plus_di  = 100 * (plus_dm.rolling(window=period).mean()  / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
        dx       = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
        adx      = dx.rolling(window=period).mean()
        return adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else 0.0

    # ──────────────────────────────────────────────────────────
    # 趋势判别 — MACD 驱动 (V5.1 核心变更)
    # ──────────────────────────────────────────────────────────

    def _determine_trend(self, macd_line: float, signal_line: float,
                         histogram: float, prev_histogram: float) -> str:
        """
        MACD 5 级趋势判别。

        返回: STRONG_BULLISH / BULLISH / NEUTRAL / BEARISH / STRONG_BEARISH
        """
        # 柱状图接近 0 → 盘整
        if abs(histogram) < 1e-9:
            return NEUTRAL

        hist_expanding = abs(histogram) > abs(prev_histogram) if abs(prev_histogram) > 1e-12 else False

        if macd_line > signal_line and histogram > 0:
            return STRONG_BULLISH if hist_expanding else BULLISH
        elif macd_line < signal_line and histogram < 0:
            return STRONG_BEARISH if hist_expanding else BEARISH

        return NEUTRAL

    def _detect_market_regime(self, df: pd.DataFrame) -> MarketRegime:
        """将 5 级趋势映射到 3 值 MarketRegime 枚举."""
        return _TREND_TO_REGIME.get(self.state.trend_strength, MarketRegime.RANGING)

    # ──────────────────────────────────────────────────────────
    # 双指标确认矩阵 (V5.1 核心)
    # ──────────────────────────────────────────────────────────

    def _get_dual_signal(self, trend: str, rsi: float) -> Tuple[int, str]:
        """
        双指标确认矩阵。

        返回 (strength 1~5, action)
          action: 'heavy_buy' / 'buy' / 'light_buy' / 'hold' / 'reduce' / 'sell' / 'stop'
        """
        # RSI 区间
        if rsi < 35:
            rsi_zone = 'oversold'
        elif rsi < 50:
            rsi_zone = 'weak'
        elif rsi < 65:
            rsi_zone = 'neutral'
        else:
            rsi_zone = 'overbought'

        # 查表: (trend, rsi_zone) → (星级, 动作)
        matrix = {
            (STRONG_BULLISH, 'oversold'):   (5, 'heavy_buy'),
            (STRONG_BULLISH, 'weak'):       (4, 'buy'),
            (STRONG_BULLISH, 'neutral'):    (3, 'light_buy'),
            (STRONG_BULLISH, 'overbought'): (2, 'hold'),

            (BULLISH, 'oversold'):   (4, 'buy'),
            (BULLISH, 'weak'):       (3, 'buy'),
            (BULLISH, 'neutral'):    (2, 'light_buy'),
            (BULLISH, 'overbought'): (1, 'hold'),

            (NEUTRAL, 'oversold'):   (3, 'light_buy'),
            (NEUTRAL, 'weak'):       (2, 'hold'),
            (NEUTRAL, 'neutral'):    (1, 'hold'),
            (NEUTRAL, 'overbought'): (1, 'reduce'),

            (BEARISH, 'oversold'):   (2, 'light_buy'),
            (BEARISH, 'weak'):       (1, 'stop'),
            (BEARISH, 'neutral'):    (0, 'stop'),
            (BEARISH, 'overbought'): (2, 'sell'),

            (STRONG_BEARISH, 'oversold'):   (1, 'hold'),
            (STRONG_BEARISH, 'weak'):       (0, 'stop'),
            (STRONG_BEARISH, 'neutral'):    (0, 'stop'),
            (STRONG_BEARISH, 'overbought'): (3, 'sell'),
        }
        return matrix.get((trend, rsi_zone), (0, 'hold'))

    # ──────────────────────────────────────────────────────────
    # RSI 自适应阈值 & 信号
    # ──────────────────────────────────────────────────────────

    def _get_adaptive_rsi_thresholds(self, df: pd.DataFrame) -> Tuple[float, float]:
        if not self.params['adaptive_rsi']:
            return self.params['rsi_oversold'], self.params['rsi_overbought']

        returns    = df['close'].pct_change().dropna()
        volatility = returns.std() * np.sqrt(1440)

        base_oversold  = self.params['rsi_oversold']
        base_overbought = self.params['rsi_overbought']
        vol_factor = min(max(volatility / 0.5, 0.5), 2.0)

        adjusted_oversold   = max(20, min(40, base_oversold  / vol_factor))
        adjusted_overbought = min(80, max(60, 100 - (100 - base_overbought) / vol_factor))
        return adjusted_oversold, adjusted_overbought

    def _get_rsi_signal(self, rsi: float, oversold: float, overbought: float) -> float:
        if rsi <= oversold:
            return 1.0
        if rsi >= overbought:
            return -1.0

        mid = 50
        if rsi < mid:
            return (mid - rsi) / (mid - oversold) * 0.5
        return (mid - rsi) / (overbought - mid) * 0.5

    # ──────────────────────────────────────────────────────────
    # Pivot Points（保留原逻辑）
    # ──────────────────────────────────────────────────────────

    def _find_pivot_points(self, df: pd.DataFrame, window: int = 5, n: int = 3,
                           lookback: int = 100) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        if len(df) < window + 1:
            return [], []

        highs    = df['high'].values
        lows     = df['low'].values
        times    = df.index
        curr_idx = len(df) - 1

        pivot_highs = []
        pivot_lows  = []

        for i in range(curr_idx, max(window, curr_idx - lookback), -1):
            if len(pivot_lows) < n:
                l_min = min(lows[i-window:i])
                if lows[i] <= l_min:
                    is_pivot = False
                    p_type   = 'unknown'
                    if i > curr_idx - window:
                        if i == curr_idx or lows[i] <= min(lows[i+1:curr_idx+1]):
                            is_pivot = True
                            p_type   = 'realtime'
                    else:
                        r_min = min(lows[i+1:i+window+1])
                        if lows[i] < r_min:
                            is_pivot = True
                            p_type   = 'confirmed'
                    if is_pivot:
                        if not pivot_lows or abs(lows[i] - pivot_lows[-1]['price']) > (lows[i] * 0.001):
                            pivot_lows.append({'price': float(lows[i]), 'time': str(times[i]), 'type': p_type})

            if len(pivot_highs) < n:
                l_max = max(highs[i-window:i])
                if highs[i] >= l_max:
                    is_pivot = False
                    p_type   = 'unknown'
                    if i > curr_idx - window:
                        if i == curr_idx or highs[i] >= max(highs[i+1:curr_idx+1]):
                            is_pivot = True
                            p_type   = 'realtime'
                    else:
                        r_max = max(highs[i+1:i+window+1])
                        if highs[i] > r_max:
                            is_pivot = True
                            p_type   = 'confirmed'
                    if is_pivot:
                        if not pivot_highs or abs(highs[i] - pivot_highs[-1]['price']) > (highs[i] * 0.001):
                            pivot_highs.append({'price': float(highs[i]), 'time': str(times[i]), 'type': p_type})

            if len(pivot_highs) >= n and len(pivot_lows) >= n:
                break

        return pivot_highs, pivot_lows

    # ──────────────────────────────────────────────────────────
    # 动态网格计算 — ATR 自适应 + MACD 趋势偏移 (V5.1)
    # ──────────────────────────────────────────────────────────

    def _calculate_dynamic_grid(self, df: pd.DataFrame,
                                current_price: float) -> Tuple[float, float, Dict[str, Any]]:
        pivot_highs, pivot_lows = self._find_pivot_points(df, window=5, n=3)

        if not pivot_highs or not pivot_lows:
            lookback = min(self.params['grid_refresh_period'], len(df))
            recent   = df.iloc[-lookback:]
            upper    = recent['high'].max()
            lower    = recent['low'].min()
        else:
            upper = max(p['price'] for p in pivot_highs)
            lower = min(p['price'] for p in pivot_lows)

        range_size = upper - lower
        if range_size <= 0:
            range_size = upper * 0.01

        # ATR 自适应网格间距
        atr = self.state.current_atr
        if atr > 0 and current_price > 0:
            atr_spacing = atr / current_price
            spacing = max(self.params['grid_spacing_min'],
                          min(self.params['grid_spacing_max'], atr_spacing))
        else:
            spacing = (self.params['grid_spacing_min'] + self.params['grid_spacing_max']) / 2

        # 根据 ATR 间距计算实际网格数
        dynamic_grid_num = max(3, int(0.30 / spacing))  # 覆盖约 30% 价格区间

        buffer = range_size * self.params['grid_buffer_pct']
        upper += buffer
        lower -= buffer

        # MACD 趋势偏移网格中心 (§5.1)
        # 增加/减少的是相对于当前价格的偏移量，避免网格飞出市场
        trend = self.state.trend_strength
        if trend == STRONG_BULLISH:
            upper += (upper - current_price) * 0.20
            lower += (current_price - lower) * 0.10
        elif trend == BULLISH:
            upper += (upper - current_price) * 0.10
            lower += (current_price - lower) * 0.05
        elif trend == BEARISH:
            upper -= (upper - current_price) * 0.05
            lower -= (current_price - lower) * 0.10
        elif trend == STRONG_BEARISH:
            upper -= (upper - current_price) * 0.10
            lower -= (current_price - lower) * 0.20

        # RSI 微调（保留原逻辑）
        rsi_signal = 0.0
        if self.params['rsi_weight'] > 0:
            oversold, overbought = self._get_adaptive_rsi_thresholds(df)
            rsi_signal = self._get_rsi_signal(self.state.current_rsi, oversold, overbought)
            shift  = range_size * rsi_signal * self.params['rsi_weight'] * 0.2
            upper += shift
            lower += shift

        return upper, lower, {
            'pivots_high': pivot_highs,
            'pivots_low': pivot_lows,
            'atr_spacing': spacing,
            'dynamic_grid_num': dynamic_grid_num,
        }

    # ──────────────────────────────────────────────────────────
    # 仓位计算 — 趋势强度系数 + RSI 偏离折扣 (V5.1)
    # ──────────────────────────────────────────────────────────

    def _calculate_position_size(self, context: StrategyContext,
                                 rsi_signal: float, is_buy: bool) -> float:
        grid_num = max(1, len(self.state.grid_prices))
        base_size = context.total_value / grid_num

        # 趋势强度系数
        trend_boost = _TREND_BOOST.get(self.state.trend_strength, 0.0)
        trend_adjusted = base_size * (1 + trend_boost)

        # RSI 偏离折扣: RSI 越偏离 50，折扣越大
        rsi_discount = 1 - abs(self.state.current_rsi - 50) / 100
        final_size = trend_adjusted * rsi_discount

        # MACD 零轴保护: MACD 线 < 0 时买入仓位减半
        if is_buy and self.state.macd_line < 0:
            final_size *= 0.5

        # 保守模式额外缩减
        if self.state.conservative_mode:
            final_size *= 0.5

        # 下限 & 上限
        final_size = max(final_size, self.params['min_order_usdt'])
        
        # 确保总额不超过可用资金的 95%
        max_allowed = context.cash * 0.95
        if final_size > max_allowed:
            final_size = max_allowed

        return final_size

    # ──────────────────────────────────────────────────────────
    # 仓位层数估算（保留）
    # ──────────────────────────────────────────────────────────

    def _estimate_position_layers(self, context: StrategyContext, current_price: float) -> int:
        current_pos = context.positions.get(self.symbol)
        if not current_pos or current_pos.size <= 0 or current_price <= 0:
            return 0

        position_notional = current_pos.size * current_price
        base_notional = max(
            context.total_value * self.params['base_position_pct'],
            self.params['min_order_usdt']
        )
        if base_notional <= 0:
            return 0
        return max(1, int(np.ceil(position_notional / base_notional)))

    # ──────────────────────────────────────────────────────────
    # 周期重置
    # ──────────────────────────────────────────────────────────

    def _should_reset_cycle(self, context: StrategyContext) -> Tuple[bool, str]:
        current_idx = len(self._data_buffer)
        if current_idx - self.state.last_grid_update >= self.params['cycle_reset_period']:
            return True, "达到强制重置周期"

        if len(self._equity_history) > 0:
            recent_equity = self._equity_history[-1000:]
            peak    = max(recent_equity)
            current = recent_equity[-1]
            if peak > 0:
                drawdown = (current - peak) / peak
                if drawdown <= -self.params['max_drawdown_reset']:
                    return True, f"触发最大回撤限制 ({drawdown:.2%})"

        return False, ""

    def _reset_cycle(self, context: StrategyContext):
        self.state.grid_upper = None
        self.state.grid_lower = None
        self.state.last_grid_update = len(self._data_buffer)
        self.state.conservative_mode = False
        self.state.consecutive_conflict = 0

    # ──────────────────────────────────────────────────────────
    # 风控: 止损 + 移动止盈 (V5.1 改进)
    # ──────────────────────────────────────────────────────────

    def _check_stop_loss(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        signals: List[Signal] = []
        current_price = data.close

        for symbol, pos in context.positions.items():
            if symbol != self.symbol:
                continue

            if symbol not in self._peak_prices:
                self._peak_prices[symbol] = pos.avg_price
            else:
                self._peak_prices[symbol] = max(self._peak_prices[symbol], current_price)

            peak = self._peak_prices[symbol]
            profit_pct = (peak - pos.avg_price) / pos.avg_price if pos.avg_price > 0 else 0

            # ── V5.1 移动止盈: 盈利>5% 且 MACD 柱状图收缩 ──
            hist_shrinking = (abs(self.state.histogram) < abs(self.state.prev_histogram)
                              and abs(self.state.prev_histogram) > 1e-12)

            if (self.params['trailing_stop']
                    and profit_pct >= self.params['trailing_trigger_pct']
                    and hist_shrinking):
                trailing_stop_price = peak * (1 - self.params['trailing_stop_pct'])
                if current_price <= trailing_stop_price:
                    signals.append(Signal(
                        timestamp=data.timestamp,
                        symbol=symbol,
                        side=Side.SELL,
                        size=pos.size,
                        price=None,
                        order_type=OrderType.MARKET,
                        reason=f"移动止盈 (Peak: ${peak:.2f}, MACD收缩)",
                        meta={'size_in_quote': False},
                    ))
                    self._peak_prices.pop(symbol, None)
                    continue

            # ── V5.1: RSI>75 且趋势转弱 → 减仓 50% ──
            if (self.state.current_rsi > 75
                    and self.state.trend_strength in (NEUTRAL, BEARISH, STRONG_BEARISH)
                    and pos.size > 0):
                sell_size = pos.size * 0.5
                signals.append(Signal(
                    timestamp=data.timestamp,
                    symbol=symbol,
                    side=Side.SELL,
                    size=sell_size,
                    price=None,
                    order_type=OrderType.MARKET,
                    reason=f"RSI 过热减仓 (RSI: {self.state.current_rsi:.1f})",
                    meta={'size_in_quote': False},
                ))
                continue

            # ── 常规止损 ──
            stop_price = (peak * (1 - self.params['trailing_stop_pct'])
                          if self.params['trailing_stop']
                          else pos.avg_price * (1 - self.params['stop_loss_pct']))

            if current_price <= stop_price:
                signals.append(Signal(
                    timestamp=data.timestamp,
                    symbol=symbol,
                    side=Side.SELL,
                    size=pos.size,
                    price=None,
                    order_type=OrderType.MARKET,
                    reason=f"止损触发 (止损价: ${stop_price:.2f})",
                    meta={'size_in_quote': False},
                ))
                self._peak_prices.pop(symbol, None)

        return signals

    # ──────────────────────────────────────────────────────────
    # 冷却期检查
    # ──────────────────────────────────────────────────────────

    def _is_in_cooldown(self, data: MarketData) -> bool:
        """检查是否在冷却期内."""
        if self.state.last_trade_ts <= 0:
            return False
        try:
            now_ts = data.timestamp.timestamp()
        except Exception:
            now_ts = _time.time()
        elapsed_min = (now_ts - self.state.last_trade_ts) / 60.0
        return elapsed_min < self.params['cooldown_minutes']

    # ──────────────────────────────────────────────────────────
    # 异常检测
    # ──────────────────────────────────────────────────────────

    def _check_anomaly(self, df: pd.DataFrame, rsi_signal: float) -> None:
        """检测 MACD/RSI 信号冲突，进入保守模式."""
        trend = self.state.trend_strength
        # 趋势看涨但 RSI 极度超买，或趋势看跌但 RSI 极度超卖 → 冲突
        bullish_trends = (STRONG_BULLISH, BULLISH)
        bearish_trends = (STRONG_BEARISH, BEARISH)

        conflict = False
        if trend in bullish_trends and rsi_signal < -0.5:
            conflict = True
        elif trend in bearish_trends and rsi_signal > 0.5:
            conflict = True

        if conflict:
            self.state.consecutive_conflict += 1
        else:
            self.state.consecutive_conflict = max(0, self.state.consecutive_conflict - 1)

        # 连续 3 次冲突 → 保守模式
        self.state.conservative_mode = self.state.consecutive_conflict >= 3

    def _check_black_swan(self, df: pd.DataFrame, data: MarketData) -> bool:
        """
        黑天鹅检测 (§6.3): 5 分钟内价格波动 > black_swan_pct → 紧急止损 + 暂停 30 分钟。
        返回 True 表示检测到黑天鹅。
        """
        try:
            now_ts = data.timestamp.timestamp()
        except Exception:
            now_ts = _time.time()

        # 如果在暂停期内，直接返回 True
        if now_ts < self.state.black_swan_pause_until:
            return True

        # 至少需要 5 根 K 线做判断
        if len(df) < 5:
            return False

        recent_close = df['close'].iloc[-5:]
        price_5m_ago = recent_close.iloc[0]
        price_now = recent_close.iloc[-1]

        if price_5m_ago > 0:
            change_pct = abs(price_now - price_5m_ago) / price_5m_ago
            if change_pct >= self.params['black_swan_pct']:
                # 暂停 30 分钟
                self.state.black_swan_pause_until = now_ts + 30 * 60
                return True

        return False

    def _check_macd_death_cross(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        """
        MACD 死叉清仓 (§5.3): MACD 死叉形成 → 清仓等待重新入场。
        死叉 = 上一周期 MACD > Signal，当前周期 MACD < Signal。
        """
        signals: List[Signal] = []

        prev_ml = self.state.prev_macd_line
        prev_sl = self.state.prev_signal_line
        curr_ml = self.state.macd_line
        curr_sl = self.state.signal_line

        # 死叉: 从上方穿到下方
        death_cross = (prev_ml > prev_sl) and (curr_ml < curr_sl)

        if not death_cross:
            return signals

        # 且趋势已偏空 (MACD 线在零轴下方或柱状图为负)
        if curr_ml >= 0 and self.state.histogram >= 0:
            return signals  # 死叉但整体仍偏多，暂不清仓

        current_pos = context.positions.get(self.symbol)
        if current_pos and current_pos.size > 0:
            signals.append(Signal(
                timestamp=data.timestamp,
                symbol=self.symbol,
                side=Side.SELL,
                size=current_pos.size,
                price=None,
                order_type=OrderType.MARKET,
                reason=f"MACD死叉清仓 (MACD:{curr_ml:.4f} Signal:{curr_sl:.4f})",
                meta={'size_in_quote': False},
            ))
            self._peak_prices.pop(self.symbol, None)

        return signals

    # ──────────────────────────────────────────────────────────
    # 主循环
    # ──────────────────────────────────────────────────────────

    def on_data(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        self._update_buffer(data)

        df = self._get_dataframe()
        if len(df) < self.params['rsi_period']:
            return []

        # ── 1. 更新指标与状态 ──
        # RSI
        self.state.current_rsi = self._calculate_rsi(df['close'])
        
        # MACD & Trend
        ml, sl, hi = self._calculate_macd(df)
        self.state.trend_strength = self._determine_trend(ml, sl, hi, self.state.prev_macd_line - self.state.prev_signal_line)
        self.state.macd_line = ml
        self.state.signal_line = sl
        self.state.histogram = hi
        self.state.prev_macd_line = ml
        self.state.prev_signal_line = sl
        self.state.prev_histogram = hi
        
        # ATR & ADX
        self.state.current_atr = self._calculate_atr(df)
        self.state.current_adx = self._calculate_adx(df)
        self.state.current_regime = self._detect_market_regime(df)
        
        # RSI 信号计算
        oversold, overbought = self._get_adaptive_rsi_thresholds(df)
        rsi_signal = self._get_rsi_signal(self.state.current_rsi, oversold, overbought)

        signals: List[Signal] = []
        current_idx   = len(self._data_buffer) - 1
        current_price = data.close
        current_high  = data.high
        current_low   = data.low
        self._current_prices[self.symbol] = current_price

        # ── 2. 动态网格计算 ──
        upper, lower, meta = self._calculate_dynamic_grid(df, current_price)
        dynamic_grid_num = meta.get('dynamic_grid_num', self.params['grid_levels'])
        actual_levels = max(3, min(dynamic_grid_num, self.params['grid_levels'] * 3))

        self.state.grid_upper  = upper
        self.state.grid_lower  = lower
        self.state.grid_prices = np.linspace(lower, upper, actual_levels).tolist()
        self.state.last_grid_update = current_idx
        self.state.meta = meta
        self.state.pivots = meta
        self.state.actual_levels = actual_levels # Store for trigger logic

        # ── 3. 风险与异常检测 ──
        self._check_anomaly(df, rsi_signal)

        if self._check_black_swan(df, data):
            for symbol, pos in context.positions.items():
                if symbol == self.symbol and pos.size > 0:
                    signals.append(Signal(
                        timestamp=data.timestamp,
                        symbol=symbol,
                        side=Side.SELL,
                        size=pos.size,
                        price=None,
                        order_type=OrderType.MARKET,
                        reason="黑天鹅紧急止损 (5分钟波动超限)",
                        meta={'size_in_quote': False},
                    ))
            return signals

        # ── 4. 周期重置 ──
        should_reset, reset_reason = self._should_reset_cycle(context)
        if should_reset:
            for symbol, pos in context.positions.items():
                if symbol == self.symbol and pos.size > 0:
                    signals.append(Signal(
                        timestamp=data.timestamp,
                        symbol=symbol,
                        side=Side.SELL,
                        size=pos.size,
                        price=None,
                        order_type=OrderType.MARKET,
                        reason=f"周期重置: {reset_reason}",
                        meta={'size_in_quote': False},
                    ))
            self._reset_cycle(context)

        # ── 止损/止盈检查 ──
        signals.extend(self._check_stop_loss(data, context))

        # ── MACD 死叉清仓 (§5.3) ──
        signals.extend(self._check_macd_death_cross(data, context))

        # ── 双指标确认 ──
        strength, action = self._get_dual_signal(self.state.trend_strength,
                                                  self.state.current_rsi)
        self.state.last_action = action  # 记录建议动作

        # 冷却期检查
        in_cooldown = self._is_in_cooldown(data)

        # ── 网格触发 ──
        min_interval     = self.params.get('min_trade_interval_pct', 0.0025)
        grid_interval_pct = min_interval
        if (self.state.grid_upper and self.state.grid_lower
                and actual_levels > 1 and current_price > 0):
            grid_interval = abs(self.state.grid_upper - self.state.grid_lower) / (actual_levels - 1)
            grid_interval_pct = max(min_interval, (grid_interval / current_price) * 0.8)
            grid_interval_pct = min(0.02, grid_interval_pct)

        if self.state.grid_prices and self.state.last_candle and not in_cooldown:
            last_high = self.state.last_candle['high']
            last_low  = self.state.last_candle['low']

            # ── 买入触发 ──
            for grid_price in self.state.grid_prices:
                if last_low > grid_price and current_low <= grid_price:
                    if action not in ('heavy_buy', 'buy', 'light_buy'):
                        continue

                    current_layers = self._estimate_position_layers(context, current_price)
                    if current_layers >= self.params['max_positions']:
                        continue

                    if self.state.current_rsi >= self.params['rsi_extreme_buy']:
                        continue

                    current_pos = context.positions.get(self.symbol)
                    if current_pos and current_pos.size > 0:
                        if current_price > current_pos.avg_price * (1 - grid_interval_pct):
                            continue

                    size = self._calculate_position_size(context, rsi_signal, is_buy=True)
                    if size < self.params['min_order_usdt']:
                        size = self.params['min_order_usdt']
                    if size > context.cash * 0.95:
                        continue

                    if action == 'light_buy':
                        size *= 0.5
                        size = max(size, self.params['min_order_usdt'])

                    signals.append(Signal(
                        timestamp=data.timestamp,
                        symbol=self.symbol,
                        side=Side.BUY,
                        size=size,
                        price=None,
                        order_type=OrderType.MARKET,
                        confidence=abs(rsi_signal),
                        reason=(f"网格买入 @ {grid_price:.2f} "
                                f"(RSI:{self.state.current_rsi:.1f} "
                                f"MACD:{self.state.trend_strength} ★{strength})"),
                        meta={'size_in_quote': True},
                    ))
                    break

            # ── 卖出触发 ──
            for grid_price in self.state.grid_prices:
                if last_high < grid_price and current_high >= grid_price:
                    current_pos = context.positions.get(self.symbol)
                    if not current_pos or current_pos.size <= 0:
                        continue

                    profitable = current_pos.avg_price < current_price * (1 - grid_interval_pct)

                    if action in ('sell', 'reduce') or profitable:
                        if self.state.current_rsi <= self.params['rsi_extreme_sell']:
                            continue

                        current_layers = self._estimate_position_layers(context, current_price)
                        sell_size = min(current_pos.size,
                                        current_pos.size / max(1, current_layers))

                        if action == 'reduce':
                            sell_size *= 0.5

                        signals.append(Signal(
                            timestamp=data.timestamp,
                            symbol=self.symbol,
                            side=Side.SELL,
                            size=sell_size,
                            price=None,
                            order_type=OrderType.MARKET,
                            confidence=abs(rsi_signal),
                            reason=(f"网格卖出 @ {grid_price:.2f} "
                                    f"(RSI:{self.state.current_rsi:.1f} "
                                    f"MACD:{self.state.trend_strength} ★{strength})"),
                            meta={'size_in_quote': False},
                        ))
                        break

        # ── 记录当前 K 线 ──
        self.state.last_candle = {
            'open':  data.open,
            'high':  data.high,
            'low':   data.low,
            'close': data.close,
        }

        return signals

    def on_fill(self, fill: FillEvent):
        if fill.side == Side.BUY:
            self.state.grid_touch_count += 1
        # 记录成交时间用于冷却期
        try:
            self.state.last_trade_ts = fill.timestamp.timestamp()
        except Exception:
            self.state.last_trade_ts = _time.time()

    # ──────────────────────────────────────────────────────────
    # 状态报告
    # ──────────────────────────────────────────────────────────

    def get_status(self, context: Optional[StrategyContext] = None) -> Dict[str, Any]:
        try:
            current_price = self._current_prices.get(self.symbol, 0)
            
            # 优先从 state 获取已预计算的网格
            upper = self.state.grid_upper or 0
            lower = self.state.grid_lower or 0
            grid_lines = self.state.grid_prices
            pivots = self.state.pivots
            
            # 指标与阈值
            df = self._get_dataframe()
            if len(df) > 0:
                oversold, overbought = self._get_adaptive_rsi_thresholds(df)
                rsi_signal = self._get_rsi_signal(self.state.current_rsi, oversold, overbought)
                atr_val = self.state.current_atr
            else:
                oversold, overbought = self.params['rsi_oversold'], self.params['rsi_overbought']
                rsi_signal = 0.0
                atr_val = 0.0
        except Exception:
            oversold, overbought = self.params['rsi_oversold'], self.params['rsi_overbought']
            rsi_signal = 0.0
            atr_val = 0.0
            upper, lower = 0, 0
            grid_lines = []
            pivots = {}

        # 双指标信号文本
        strength, action = self._get_dual_signal(self.state.trend_strength,
                                                  self.state.current_rsi)
        signal_text  = "观望"
        signal_color = "neutral"
        if action in ('heavy_buy', 'buy'):
            signal_text  = f"买入信号 ★{strength} ({rsi_signal:+.2f})"
            signal_color = "buy"
        elif action == 'light_buy':
            signal_text  = f"轻仓买入 ★{strength} ({rsi_signal:+.2f})"
            signal_color = "buy"
        elif action in ('sell', 'reduce'):
            signal_text  = f"卖出信号 ★{strength} ({rsi_signal:+.2f})"
            signal_color = "sell"
        elif action == 'stop':
            signal_text  = "停止交易"
            signal_color = "sell"

        in_grid       = ""
        current_price = self._current_prices.get(self.symbol, 0) if hasattr(self, '_current_prices') else 0
        if self.state.grid_lower is not None and self.state.grid_upper is not None and current_price > 0:
            if current_price < self.state.grid_lower:
                in_grid = "低于网格"
            elif current_price > self.state.grid_upper:
                in_grid = "高于网格"
            else:
                in_grid = "网格内"

        position_count = 0
        if context and self.symbol in context.positions:
            position_count = self._estimate_position_layers(context, current_price)

        params_snapshot = {k: v for k, v in self.params.items()}
        params_snapshot['symbol'] = self.symbol

        trend_labels = {
            STRONG_BULLISH: "极强牛市 ↑↑",
            BULLISH:        "看涨趋势 ↑",
            NEUTRAL:        "中性偏区间 ↔",
            BEARISH:        "看跌趋势 ↓",
            STRONG_BEARISH: "极强熊市 ↓↓"
        }

        return {
            'grid_upper':       upper if upper > 0 else (self.state.grid_upper or 0),
            'grid_lower':       lower if lower > 0 else (self.state.grid_lower or 0),
            'grid_count':       len(grid_lines) if grid_lines else len(self.state.grid_prices),
            'max_positions':    self.params['max_positions'],
            'position_count':   position_count,
            'current_rsi':      self.state.current_rsi,
            'rsi_oversold':     oversold,
            'rsi_overbought':   overbought,
            'rsi_signal':       rsi_signal,
            'current_adx':      self.state.current_adx,
            'market_regime':    self.state.current_regime.value,
            'signal_text':      signal_text,
            'signal_color':     signal_color,
            'action_intent':    getattr(self.state, 'last_action', 'hold'), # 透传给前端
            'in_grid':          in_grid,
            'trade_executed':   False,
            'grid_touch_count': self.state.grid_touch_count,
            'grid_lines':       grid_lines if grid_lines else self.state.grid_prices,
            'pivots':           pivots if pivots else self.state.pivots,
            'params':           params_snapshot,
            # V5.1 新增
            'macd':             self.state.macd_line,
            'macdsignal':       self.state.signal_line,
            'macdhist':         self.state.histogram,
            'macd_trend':       trend_labels.get(self.state.trend_strength, "未知"),
            'trend_strength':   self.state.trend_strength,
            'current_atr':      atr_val,
            'dual_strength':    strength,
            'dual_action':      action,
            'conservative_mode': self.state.conservative_mode,
        }
