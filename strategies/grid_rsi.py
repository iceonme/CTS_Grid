"""
动态网格 RSI 策略 V4.0
对齐原始算法语义，并适配 OKX 实时执行
"""

from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass, field
import pandas as pd
import numpy as np

from core import (
    Signal, MarketData, StrategyContext, FillEvent,
    Side, OrderType, MarketRegime
)
from .base import BaseStrategy


@dataclass
class GridState:
    """策略运行时状态（不含账户真相）"""
    grid_upper: Optional[float] = None
    grid_lower: Optional[float] = None
    grid_prices: List[float] = field(default_factory=list)
    last_grid_update: int = 0
    current_rsi: float = 50.0
    current_adx: float = 0.0
    current_regime: MarketRegime = MarketRegime.UNKNOWN
    last_candle: Optional[Dict[str, float]] = None

    # 统计
    grid_touch_count: int = 0


class GridRSIStrategy(BaseStrategy):
    """动态网格 RSI 策略 V4.0"""

    def __init__(self,
                 symbol: str = "BTC-USDT",
                 # 网格参数
                 grid_levels: int = 10,
                 grid_refresh_period: int = 100,
                 grid_buffer_pct: float = 0.1,
                 # RSI 参数
                 rsi_period: int = 14,
                 rsi_weight: float = 0.4,
                 rsi_oversold: float = 35,
                 rsi_overbought: float = 65,
                 rsi_extreme_buy: float = 70,
                 rsi_extreme_sell: float = 30,
                 adaptive_rsi: bool = True,
                 # 趋势参数
                 use_trend_filter: bool = True,
                 adx_period: int = 14,
                 adx_threshold: float = 25,
                 ma_period: int = 50,
                 # 仓位参数
                 base_position_pct: float = 0.1,
                 max_positions: int = 5,
                 use_kelly_sizing: bool = True,
                 kelly_fraction: float = 0.3,
                 max_position_multiplier: float = 2.0,
                 min_position_multiplier: float = 0.5,
                 # 止损参数
                 stop_loss_pct: float = 0.05,
                 trailing_stop: bool = True,
                 trailing_stop_pct: float = 0.03,
                 # 周期参数
                 cycle_reset_period: int = 5000,
                 max_drawdown_reset: float = 0.30,
                 # 最小交易金额
                 min_order_usdt: float = 100.0,
                 **kwargs):
        super().__init__(name="GridRSI_V4", **kwargs)

        self.symbol = symbol
        self.params = {
            'grid_levels': grid_levels,
            'grid_refresh_period': grid_refresh_period,
            'grid_buffer_pct': grid_buffer_pct,
            'rsi_period': rsi_period,
            'rsi_weight': rsi_weight,
            'rsi_oversold': rsi_oversold,
            'rsi_overbought': rsi_overbought,
            'rsi_extreme_buy': rsi_extreme_buy,
            'rsi_extreme_sell': rsi_extreme_sell,
            'adaptive_rsi': adaptive_rsi,
            'use_trend_filter': use_trend_filter,
            'adx_period': adx_period,
            'adx_threshold': adx_threshold,
            'ma_period': ma_period,
            'base_position_pct': base_position_pct,
            'max_positions': max_positions,
            'use_kelly_sizing': use_kelly_sizing,
            'kelly_fraction': kelly_fraction,
            'max_position_multiplier': max_position_multiplier,
            'min_position_multiplier': min_position_multiplier,
            'stop_loss_pct': stop_loss_pct,
            'trailing_stop': trailing_stop,
            'trailing_stop_pct': trailing_stop_pct,
            'cycle_reset_period': cycle_reset_period,
            'max_drawdown_reset': max_drawdown_reset,
            'min_order_usdt': min_order_usdt,
            'min_trade_interval_pct': kwargs.get('min_trade_interval_pct', 0.0025), # 默认 0.25%
        }

        self.state = GridState()

        self._data_buffer: List[MarketData] = []
        self._max_buffer_size = max(ma_period, rsi_period, adx_period) * 3 + 100
        self._peak_prices: Dict[str, float] = {}
        self._current_prices: Dict[str, float] = {}
        self._equity_history: List[float] = []

    def initialize(self):
        super().initialize()
        self._data_buffer.clear()
        self.state = GridState()
        self._peak_prices.clear()
        self._current_prices.clear()
        self._equity_history.clear()

    def _update_buffer(self, data: MarketData):
        if self._data_buffer and self._data_buffer[-1].timestamp == data.timestamp:
            # 更新当前根 K 线 (实时价格)
            self._data_buffer[-1] = data
        else:
            # 加新 K 线
            self._data_buffer.append(data)
            if len(self._data_buffer) > self._max_buffer_size:
                self._data_buffer.pop(0)

    def _get_dataframe(self) -> pd.DataFrame:
        if len(self._data_buffer) < 2:
            return pd.DataFrame()

        data = {
            'open': [d.open for d in self._data_buffer],
            'high': [d.high for d in self._data_buffer],
            'low': [d.low for d in self._data_buffer],
            'close': [d.close for d in self._data_buffer],
            'volume': [d.volume for d in self._data_buffer],
        }
        index = [d.timestamp for d in self._data_buffer]
        return pd.DataFrame(data, index=index)

    def _calculate_rsi(self, prices: pd.Series) -> float:
        period = self.params['rsi_period']
        if len(prices) < period + 1:
            return 50.0

        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50.0

    def _calculate_adx(self, df: pd.DataFrame) -> float:
        period = self.params['adx_period']
        if len(df) < period * 2:
            return 0.0

        high, low, close = df['high'], df['low'], df['close']
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0

        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
        adx = dx.rolling(window=period).mean()
        return adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else 0.0

    def _detect_market_regime(self, df: pd.DataFrame) -> MarketRegime:
        if not self.params['use_trend_filter'] or len(df) < self.params['ma_period']:
            return MarketRegime.RANGING

        adx = self.state.current_adx
        ma = df['close'].rolling(window=self.params['ma_period']).mean().iloc[-1]
        current_price = df['close'].iloc[-1]

        if adx > self.params['adx_threshold']:
            if current_price > ma * 1.02:
                return MarketRegime.TRENDING_UP
            if current_price < ma * 0.98:
                return MarketRegime.TRENDING_DOWN

        return MarketRegime.RANGING

    def _get_adaptive_rsi_thresholds(self, df: pd.DataFrame) -> Tuple[float, float]:
        if not self.params['adaptive_rsi']:
            return self.params['rsi_oversold'], self.params['rsi_overbought']

        returns = df['close'].pct_change().dropna()
        volatility = returns.std() * np.sqrt(1440)

        base_oversold = self.params['rsi_oversold']
        base_overbought = self.params['rsi_overbought']
        vol_factor = min(max(volatility / 0.5, 0.5), 2.0)

        adjusted_oversold = max(20, min(40, base_oversold / vol_factor))
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

    def _find_pivot_points(self, df: pd.DataFrame, window: int = 5, n: int = 3,
                           lookback: int = 100) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        寻找最近 of n 个波段高点和低点 (增强时效性逻辑)
        最新的点采用单侧确认，历史点采用双侧确认
        """
        if len(df) < window + 1:
            return [], []

        highs = df['high'].values
        lows = df['low'].values
        times = df.index
        
        pivot_highs = []
        pivot_lows = []

        # 1. 处理最新的实时点 (单侧确认：只需比左侧 window 根 K线高/低)
        curr_idx = len(df) - 1
        
        # 实时低点检测
        left_low_min = min(lows[max(0, curr_idx - window):curr_idx])
        if lows[curr_idx] <= left_low_min:
            pivot_lows.append({'price': float(lows[curr_idx]), 'time': str(times[curr_idx]), 'type': 'realtime'})

        # 实时高点检测
        left_high_max = max(highs[max(0, curr_idx - window):curr_idx])
        if highs[curr_idx] >= left_high_max:
            pivot_highs.append({'price': float(highs[curr_idx]), 'time': str(times[curr_idx]), 'type': 'realtime'})

        # 2. 寻找历史波段点 (双侧确认)
        search_end = curr_idx - window
        search_start = max(window, search_end - lookback)

        for i in range(search_end, search_start - 1, -1):
            # 高点双侧确认
            if len(pivot_highs) < n:
                l_max = max(highs[i-window:i])
                r_max = max(highs[i+1:i+window+1])
                if highs[i] > l_max and highs[i] > r_max:
                    # 避免与实时点或上一个点太近
                    if not pivot_highs or abs(highs[i] - pivot_highs[-1]['price']) > (highs[i] * 0.001):
                        pivot_highs.append({'price': float(highs[i]), 'time': str(times[i]), 'type': 'confirmed'})

            # 低点双侧确认
            if len(pivot_lows) < n:
                l_min = min(lows[i-window:i])
                r_min = min(lows[i+1:i+window+1])
                if lows[i] < l_min and lows[i] < r_min:
                    if not pivot_lows or abs(lows[i] - pivot_lows[-1]['price']) > (lows[i] * 0.001):
                        pivot_lows.append({'price': float(lows[i]), 'time': str(times[i]), 'type': 'confirmed'})
            
            if len(pivot_highs) >= n and len(pivot_lows) >= n:
                break
                
        return pivot_highs, pivot_lows

    def _calculate_dynamic_grid(self, df: pd.DataFrame) -> Tuple[float, float, Dict[str, Any]]:
        """
        计算动态网格区间 - 思路B: 3高3低逻辑
        """
        # 1. 寻找波段点 (Pivot Points)
        pivot_highs, pivot_lows = self._find_pivot_points(df, window=5, n=3)
        
        if not pivot_highs or not pivot_lows:
            # 回退到旧的 lookback 逻辑
            lookback = min(self.params['grid_refresh_period'], len(df))
            recent = df.iloc[-lookback:]
            upper = recent['high'].max()
            lower = recent['low'].min()
        else:
            # 使用3高3低的均值或极值
            # 为了更稳健，这里取均值以平滑异常波动，或取极值以确保全覆盖。
            # 这里采用：最高的高点和最低的低点来确定边界，更符合“防跑出”策略。
            upper = max(p['price'] for p in pivot_highs)
            lower = min(p['price'] for p in pivot_lows)

        range_size = upper - lower
        if range_size <= 0:
            range_size = upper * 0.01  # 防止零值
            
        buffer = range_size * self.params['grid_buffer_pct']

        upper += buffer
        lower -= buffer

        # 2. RSI 偏移逻辑保持不变
        rsi_signal = 0.0
        if self.params['rsi_weight'] > 0:
            oversold, overbought = self._get_adaptive_rsi_thresholds(df)
            rsi_signal = self._get_rsi_signal(self.state.current_rsi, oversold, overbought)
            # 偏移量通常在 2%-10% 范围，根据 rsi_weight 调整
            shift = range_size * rsi_signal * self.params['rsi_weight'] * 0.2
            upper += shift
            lower += shift

        return upper, lower, {'pivots_high': pivot_highs, 'pivots_low': pivot_lows}

    def _calculate_position_size(self, context: StrategyContext, rsi_signal: float, is_buy: bool) -> float:
        base_size = context.total_value * self.params['base_position_pct']

        regime_multiplier = 1.0
        regime = self.state.current_regime
        if regime == MarketRegime.TRENDING_UP and is_buy:
            regime_multiplier = 0.7
        elif regime == MarketRegime.TRENDING_DOWN and (not is_buy):
            regime_multiplier = 0.7

        if self.params['use_kelly_sizing']:
            if is_buy:
                win_prob = 0.5 + rsi_signal * 0.2
            else:
                win_prob = 0.5 - rsi_signal * 0.2
            win_prob = np.clip(win_prob, 0.3, 0.8)
            loss_prob = 1 - win_prob
            kelly_pct = (win_prob - loss_prob)
            kelly_pct = max(0, kelly_pct) * self.params['kelly_fraction']
            rsi_multiplier = 1 + kelly_pct
        else:
            if is_buy:
                rsi_multiplier = 1 + rsi_signal * 0.5
            else:
                rsi_multiplier = 1 - rsi_signal * 0.5
            rsi_multiplier = np.clip(
                rsi_multiplier,
                self.params['min_position_multiplier'],
                self.params['max_position_multiplier'],
            )

        final_size = base_size * regime_multiplier * rsi_multiplier
        return min(final_size, context.cash * 0.95)

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

    def _should_reset_cycle(self, context: StrategyContext) -> Tuple[bool, str]:
        current_idx = len(self._data_buffer)

        if current_idx - self.state.last_grid_update >= self.params['cycle_reset_period']:
            return True, "达到强制重置周期"

        if len(self._equity_history) > 0:
            recent_equity = self._equity_history[-1000:]
            peak = max(recent_equity)
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

            if self.params['trailing_stop']:
                stop_price = self._peak_prices[symbol] * (1 - self.params['trailing_stop_pct'])
            else:
                stop_price = pos.avg_price * (1 - self.params['stop_loss_pct'])

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

    def on_data(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        self._update_buffer(data)

        df = self._get_dataframe()
        if len(df) < self.params['rsi_period']:
            return []

        signals: List[Signal] = []
        current_idx = len(self._data_buffer)
        current_price = data.close
        current_high = data.high
        current_low = data.low

        self.state.current_rsi = self._calculate_rsi(df['close'])
        self.state.current_adx = self._calculate_adx(df)
        self.state.current_regime = self._detect_market_regime(df)

        self._equity_history.append(context.total_value)
        if len(self._equity_history) > 5000:
            self._equity_history = self._equity_history[-5000:]

        should_reset, reset_reason = self._should_reset_cycle(context)
        if should_reset:
            for symbol, pos in context.positions.items():
                if symbol == self.symbol:
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

        # 每分钟都进行检测 (思路B)，只要结构变化网格就会微调
        # 这里不再死锁 100 根线，而是根据结构点更新
        upper, lower, meta = self._calculate_dynamic_grid(df)
        self.state.grid_upper = upper
        self.state.grid_lower = lower
        self.state.grid_prices = np.linspace(
            self.state.grid_lower,
            self.state.grid_upper,
            self.params['grid_levels']
        ).tolist()
        self.state.last_grid_update = current_idx
        self.state.meta = meta  # 保存波段点信息用于汇报

        signals.extend(self._check_stop_loss(data, context))

        oversold, overbought = self._get_adaptive_rsi_thresholds(df)
        rsi_signal = self._get_rsi_signal(self.state.current_rsi, oversold, overbought)

        # 计算动态网格间距保护比例
        min_interval = self.params.get('min_trade_interval_pct', 0.0025)
        grid_interval_pct = min_interval
        if self.state.grid_upper and self.state.grid_lower and self.params['grid_levels'] > 1 and current_price > 0:
            grid_interval = abs(self.state.grid_upper - self.state.grid_lower) / (self.params['grid_levels'] - 1)
            # 取网格间距的 80% 作为保护距离，但不得低于设定的最小间隔 (如 0.25%)
            grid_interval_pct = max(min_interval, (grid_interval / current_price) * 0.8)
            grid_interval_pct = min(0.02, grid_interval_pct) # 最大上限放宽到 2%

        if self.state.grid_prices and self.state.last_candle:
            last_high = self.state.last_candle['high']
            last_low = self.state.last_candle['low']

            for grid_price in self.state.grid_prices:
                if last_low > grid_price and current_low <= grid_price:
                    current_layers = self._estimate_position_layers(context, current_price)
                    if current_layers >= self.params['max_positions']:
                        continue
                    if self.state.current_rsi >= self.params['rsi_extreme_buy']:
                        continue

                    # 间隔保护: 新加仓价格需低于持仓均价动态比例
                    current_pos = context.positions.get(self.symbol)
                    if current_pos and current_pos.size > 0:
                        if current_price > current_pos.avg_price * (1 - grid_interval_pct):
                            continue

                    size = self._calculate_position_size(context, rsi_signal, is_buy=True)
                    if size < self.params['min_order_usdt']:
                        size = self.params['min_order_usdt']
                    if size > context.cash * 0.95:
                        continue

                    signals.append(Signal(
                        timestamp=data.timestamp,
                        symbol=self.symbol,
                        side=Side.BUY,
                        size=size,
                        price=None,
                        order_type=OrderType.MARKET,
                        confidence=abs(rsi_signal),
                        reason=f"网格买入 @ {grid_price:.2f} (RSI: {self.state.current_rsi:.1f})",
                        meta={'size_in_quote': True},
                    ))
                    break

                if last_high < grid_price and current_high >= grid_price:
                    current_pos = context.positions.get(self.symbol)
                    if current_pos and current_pos.avg_price < current_price * (1 - grid_interval_pct):
                        if self.state.current_rsi <= self.params['rsi_extreme_sell']:
                            continue

                        current_layers = self._estimate_position_layers(context, current_price)
                        sell_size = min(current_pos.size, current_pos.size / max(1, current_layers))

                        signals.append(Signal(
                            timestamp=data.timestamp,
                            symbol=self.symbol,
                            side=Side.SELL,
                            size=sell_size,
                            price=None,
                            order_type=OrderType.MARKET,
                            confidence=abs(rsi_signal),
                            reason=f"网格卖出 @ {grid_price:.2f} (RSI: {self.state.current_rsi:.1f})",
                            meta={'size_in_quote': False},
                        ))
                        break

        self.state.last_candle = {
            'open': data.open,
            'high': data.high,
            'low': data.low,
            'close': data.close,
        }

        return signals

    def on_fill(self, fill: FillEvent):
        if fill.side == Side.BUY:
            self.state.grid_touch_count += 1

    def get_status(self, context: Optional[StrategyContext] = None) -> Dict[str, Any]:
        try:
            df = self._get_dataframe()
            if len(df) > 0:
                oversold, overbought = self._get_adaptive_rsi_thresholds(df)
                rsi_signal = self._get_rsi_signal(self.state.current_rsi, oversold, overbought)
            else:
                oversold, overbought = self.params['rsi_oversold'], self.params['rsi_overbought']
                rsi_signal = 0.0
        except Exception:
            oversold, overbought = self.params['rsi_oversold'], self.params['rsi_overbought']
            rsi_signal = 0.0

        signal_text = "观望"
        signal_color = "neutral"
        if rsi_signal > 0.3:
            signal_text = f"买入信号 ({rsi_signal:+.2f})"
            signal_color = "buy"
        elif rsi_signal < -0.3:
            signal_text = f"卖出信号 ({rsi_signal:+.2f})"
            signal_color = "sell"

        in_grid = ""
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


        params_snapshot = {
            'symbol': self.symbol,
            'grid_levels': self.params['grid_levels'],
            'grid_refresh_period': self.params['grid_refresh_period'],
            'grid_buffer_pct': self.params['grid_buffer_pct'],
            'rsi_period': self.params['rsi_period'],
            'rsi_weight': self.params['rsi_weight'],
            'rsi_oversold': self.params['rsi_oversold'],
            'rsi_overbought': self.params['rsi_overbought'],
            'rsi_extreme_buy': self.params['rsi_extreme_buy'],
            'rsi_extreme_sell': self.params['rsi_extreme_sell'],
            'adaptive_rsi': self.params['adaptive_rsi'],
            'use_trend_filter': self.params['use_trend_filter'],
            'adx_period': self.params['adx_period'],
            'adx_threshold': self.params['adx_threshold'],
            'ma_period': self.params['ma_period'],
            'base_position_pct': self.params['base_position_pct'],
            'max_positions': self.params['max_positions'],
            'use_kelly_sizing': self.params['use_kelly_sizing'],
            'kelly_fraction': self.params['kelly_fraction'],
            'stop_loss_pct': self.params['stop_loss_pct'],
            'trailing_stop': self.params['trailing_stop'],
            'trailing_stop_pct': self.params['trailing_stop_pct'],
            'cycle_reset_period': self.params['cycle_reset_period'],
            'max_drawdown_reset': self.params['max_drawdown_reset'],
            'min_order_usdt': self.params['min_order_usdt'],
            'min_trade_interval_pct': self.params.get('min_trade_interval_pct', 0.0025),
        }

        return {
            'grid_upper': self.state.grid_upper or 0,
            'grid_lower': self.state.grid_lower or 0,
            'grid_count': len(self.state.grid_prices),
            'max_positions': self.params['max_positions'],
            'position_count': position_count,
            'current_rsi': self.state.current_rsi,
            'rsi_oversold': oversold,
            'rsi_overbought': overbought,
            'rsi_signal': rsi_signal,
            'current_adx': self.state.current_adx,
            'market_regime': self.state.current_regime.value,
            'signal_text': signal_text,
            'signal_color': signal_color,
            'in_grid': in_grid,
            'trade_executed': False,
            'grid_touch_count': self.state.grid_touch_count,
            'pivots': getattr(self.state, 'meta', {}),
            'params': params_snapshot,
        }
