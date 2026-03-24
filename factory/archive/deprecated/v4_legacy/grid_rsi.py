"""
鍔ㄦ€佺綉鏍?RSI 绛栫暐 V4.0
瀵归綈鍘熷绠楁硶璇箟锛屽苟閫傞厤 OKX 瀹炴椂鎵ц
"""

from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass, field
import pandas as pd
import numpy as np

from collections import deque
from console.core import (
    Signal, MarketData, StrategyContext, FillEvent,
    Side, OrderType, MarketRegime
)
from cartridges.strategies.base import BaseStrategy


# ============================================================
# 楂樻€ц兘澧為噺鎸囨爣寮曟搸 (閫傞厤 V4.0 閫昏緫)
# ============================================================

class IncrementalIndicatorsV4:
    def __init__(self, p: dict):
        self.p = p
        self.count = 0
        self.prev_close = 0.0
        self.prev_high = 0.0
        self.prev_low = 0.0

        # RSI (SMA based as in V4.0 original)
        self.rsi_period = p.get('rsi_period', 14)
        self.gain_deque = deque(maxlen=self.rsi_period)
        self.loss_deque = deque(maxlen=self.rsi_period)
        self.gain_sum = 0.0
        self.loss_sum = 0.0

        # ADX (SMA based)
        self.adx_period = p.get('adx_period', 14)
        self.tr_deque = deque(maxlen=self.adx_period)
        self.pdm_deque = deque(maxlen=self.adx_period)
        self.mdm_deque = deque(maxlen=self.adx_period)
        self.dx_deque = deque(maxlen=self.adx_period)
        self.tr_sum = 0.0
        self.pdm_sum = 0.0
        self.mdm_sum = 0.0
        self.dx_sum = 0.0

        # MA
        self.ma_period = p.get('ma_period', 50)
        self.ma_deque = deque(maxlen=self.ma_period)
        self.ma_sum = 0.0

        # Volatility (Std of Pct Returns)
        # V4.0 鍘熺増鏄绠楀叏閲忕殑 std锛岃繖閲岀敤 100 鏍圭嚎閲囨牱浠ヤ繚璇佹€ц兘
        self.ret_deque = deque(maxlen=100)

    def update(self, d: MarketData, commit: bool = True):
        c, h, l = d.close, d.high, d.low
        if self.count == 0:
            if commit:
                self.prev_close, self.prev_high, self.prev_low = c, h, l
                self.count += 1
            return 50.0, 0.0, c, 0.0

        # 1. RSI 澧為噺
        diff = c - self.prev_close
        gain = max(diff, 0); loss = max(-diff, 0)
        
        def get_sma_preview(dq, cur_sum, val, p):
            count = len(dq)
            if count == 0: return val
            s = cur_sum + val - (dq[0] if count == p else 0)
            return s / (count if count < p else p)

        rsi_gain_avg = get_sma_preview(self.gain_deque, self.gain_sum, gain, self.rsi_period)
        rsi_loss_avg = get_sma_preview(self.loss_deque, self.loss_sum, loss, self.rsi_period)
        rs = rsi_gain_avg / rsi_loss_avg if rsi_loss_avg > 1e-9 else 100.0
        rsi = 100.0 - (100.0 / (1.0 + rs)) if rsi_loss_avg > 1e-9 else 100.0

        # 2. ADX 澧為噺
        tr = max(h - l, abs(h - self.prev_close), abs(l - self.prev_close))
        up = h - self.prev_high; dn = self.prev_low - l
        pdm = up if (up > dn and up > 0) else 0
        mdm = dn if (dn > up and dn > 0) else 0

        avg_tr = get_sma_preview(self.tr_deque, self.tr_sum, tr, self.adx_period)
        avg_pdm = get_sma_preview(self.pdm_deque, self.pdm_sum, pdm, self.adx_period)
        avg_mdm = get_sma_preview(self.mdm_deque, self.mdm_sum, mdm, self.adx_period)

        di_p = 100 * (avg_pdm / avg_tr) if avg_tr > 1e-9 else 0
        di_m = 100 * (avg_mdm / avg_tr) if avg_tr > 1e-9 else 0
        dx = 100 * abs(di_p - di_m) / (di_p + di_m) if (di_p + di_m) > 1e-9 else 0
        adx = get_sma_preview(self.dx_deque, self.dx_sum, dx, self.adx_period)

        # 3. MA & Vol
        ma = get_sma_preview(self.ma_deque, self.ma_sum, c, self.ma_period)
        
        ret = (c - self.prev_close) / self.prev_close if self.prev_close > 0 else 0
        # 娉㈠姩鐜囦及绠?
        tmp_rets = list(self.ret_deque) + [ret]
        vol = float(np.std(tmp_rets)) * 37.947 # sqrt(1440) approx

        if commit:
            self.count += 1
            if len(self.gain_deque) == self.rsi_period: self.gain_sum -= self.gain_deque.popleft()
            self.gain_deque.append(gain); self.gain_sum += gain
            if len(self.loss_deque) == self.rsi_period: self.loss_sum -= self.loss_deque.popleft()
            self.loss_deque.append(loss); self.loss_sum += loss

            if len(self.tr_deque) == self.adx_period: self.tr_sum -= self.tr_deque.popleft()
            self.tr_deque.append(tr); self.tr_sum += tr
            if len(self.pdm_deque) == self.adx_period: self.pdm_sum -= self.pdm_deque.popleft()
            self.pdm_deque.append(pdm); self.pdm_sum += pdm
            if len(self.mdm_deque) == self.adx_period: self.mdm_sum -= self.mdm_deque.popleft()
            self.mdm_deque.append(mdm); self.mdm_sum += mdm
            if len(self.dx_deque) == self.adx_period: self.dx_sum -= self.dx_deque.popleft()
            self.dx_deque.append(dx); self.dx_sum += dx

            if len(self.ma_deque) == self.ma_period: self.ma_sum -= self.ma_deque.popleft()
            self.ma_deque.append(c); self.ma_sum += c
            
            self.ret_deque.append(ret)
            self.prev_close, self.prev_high, self.prev_low = c, h, l

        return rsi, adx, ma, vol


@dataclass
class GridState:
    """绛栫暐杩愯鏃剁姸鎬侊紙涓嶅惈璐︽埛鐪熺浉锛?""
    grid_upper: Optional[float] = None
    grid_lower: Optional[float] = None
    grid_prices: List[float] = field(default_factory=list)
    last_grid_update: int = 0
    current_rsi: float = 50.0
    current_adx: float = 0.0
    current_regime: MarketRegime = MarketRegime.UNKNOWN
    last_candle: Optional[Dict[str, float]] = None

    # 缁熻
    grid_touch_count: int = 0


class GridRSIStrategy(BaseStrategy):
    """鍔ㄦ€佺綉鏍?RSI 绛栫暐 V4.0"""

    def __init__(self,
                 symbol: str = "BTC-USDT",
                 # 缃戞牸鍙傛暟
                 grid_levels: int = 10,
                 grid_refresh_period: int = 100,
                 grid_buffer_pct: float = 0.1,
                 # RSI 鍙傛暟
                 rsi_period: int = 14,
                 rsi_weight: float = 0.4,
                 rsi_oversold: float = 35,
                 rsi_overbought: float = 65,
                 rsi_extreme_buy: float = 70,
                 rsi_extreme_sell: float = 30,
                 adaptive_rsi: bool = True,
                 # 瓒嬪娍鍙傛暟
                 use_trend_filter: bool = True,
                 adx_period: int = 14,
                 adx_threshold: float = 25,
                 ma_period: int = 50,
                 # 浠撲綅鍙傛暟
                 base_position_pct: float = 0.1,
                 max_positions: int = 5,
                 use_kelly_sizing: bool = True,
                 kelly_fraction: float = 0.3,
                 max_position_multiplier: float = 2.0,
                 min_position_multiplier: float = 0.5,
                 # 姝㈡崯鍙傛暟
                 stop_loss_pct: float = 0.05,
                 trailing_stop: bool = True,
                 trailing_stop_pct: float = 0.03,
                 # 鍛ㄦ湡鍙傛暟
                 cycle_reset_period: int = 5000,
                 max_drawdown_reset: float = 0.30,
                 # 鏈€灏忎氦鏄撻噾棰?
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
            'min_trade_interval_pct': kwargs.get('min_trade_interval_pct', 0.0025), # 榛樿 0.25%
        }

        self.state = GridState()

        self.indicators = IncrementalIndicatorsV4(self.params)
        self._data_buffer: List[MarketData] = []
        self._max_buffer_size = 500 # 鍥哄畾缂撳啿鍖哄ぇ灏?
        self._last_bar_ts = None
        self._last_bar_data = None
        
        self._peak_prices: Dict[str, float] = {}
        self._current_prices: Dict[str, float] = {}
        self._equity_history: List[float] = []

    def initialize(self):
        """绛栫暐鍒濆鍖栵細淇濈暀琛屾儏缂撳啿鍖猴紝浠呴噸缃处鎴风浉鍏崇姸鎬?""
        super().initialize()
        
        self.state = GridState()
        self.indicators = IncrementalIndicatorsV4(self.params)
        self._last_bar_ts = None
        self._last_bar_data = None
        
        # 淇濈暀浠锋牸寮曠敤浠ョ淮鎸?UI 鍝嶅簲
        # self._peak_prices.clear() # 鑰冭檻鍒版鎹熼€昏緫锛岄噸缃椂搴斿綋娓呯┖宄板€间环鏍?
        
        # 娓呯┖鏉冪泭鍘嗗彶锛屽洜涓鸿处鎴峰凡缁忚祫閲戦噸缃?
        self._equity_history.clear()
        
        print(f"[Strategy:{self.name}] 宸叉墽琛岄€昏緫閲嶇疆 (琛屾儏缂撳啿鍖轰繚鐣? {len(self._data_buffer)} 鏍?")

    def _update_buffer(self, data: MarketData):
        if self._data_buffer and self._data_buffer[-1].timestamp == data.timestamp:
            # 鏇存柊褰撳墠鏍?K 绾?(瀹炴椂浠锋牸)
            self._data_buffer[-1] = data
        else:
            # 鍔犳柊 K 绾?
            self._data_buffer.append(data)
            if len(self._data_buffer) > self._max_buffer_size:
                self._data_buffer.pop(0)
            
            # [Arena 浼樺寲] 楂橀€熸ā寮忎笅澧炲姞绠€鍗曠殑闈為樆濉炶繘搴︿俊鎭?
            if len(self._data_buffer) % 5000 == 0:
                print(f"  > [4.0] 宸插鐞?{len(self._data_buffer)} 鏉℃暟鎹?..", flush=True)

    def _detect_market_regime(self, adx: float, ma: float, current_price: float) -> MarketRegime:
        if not self.params['use_trend_filter']:
            return MarketRegime.RANGING

        if adx > self.params['adx_threshold']:
            if current_price > ma * 1.02:
                return MarketRegime.TRENDING_UP
            if current_price < ma * 0.98:
                return MarketRegime.TRENDING_DOWN

        return MarketRegime.RANGING

    def _get_adaptive_rsi_thresholds(self, vol: float) -> Tuple[float, float]:
        if not self.params['adaptive_rsi']:
            return self.params['rsi_oversold'], self.params['rsi_overbought']

        vol_factor = min(max(vol / 0.5, 0.5), 2.0)

        base_oversold = self.params['rsi_oversold']
        base_overbought = self.params['rsi_overbought']

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

    def _find_pivot_points(self, window: int = 5, n: int = 3,
                           lookback: int = 100) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        瀵绘壘鏈€杩?of n 涓尝娈甸珮鐐瑰拰浣庣偣 (浼樺寲鐗? 鐩存帴鎿嶄綔 MarketData 鍒楄〃)
        """
        if len(self._data_buffer) < window + 2:
            return [], []

        data = self._data_buffer
        curr_idx = len(data) - 1
        
        pivot_highs = []
        pivot_lows = []

        # 浠庢渶鏂板線鍥炴壂
        for i in range(curr_idx - 1, max(window, curr_idx - lookback), -1):
            # 浣庣偣妫€娴?
            if len(pivot_lows) < n:
                if all(data[i].low <= data[i-j].low for j in range(1, window+1)) and \
                   all(data[i].low < data[i+j].low for j in range(1, min(window+1, curr_idx - i + 1))):
                    pivot_lows.append({'price': float(data[i].low), 'time': str(data[i].timestamp)})

            # 楂樼偣妫€娴?
            if len(pivot_highs) < n:
                if all(data[i].high >= data[i-j].high for j in range(1, window+1)) and \
                   all(data[i].high > data[i+j].high for j in range(1, min(window+1, curr_idx - i + 1))):
                    pivot_highs.append({'price': float(data[i].high), 'time': str(data[i].timestamp)})

            if len(pivot_highs) >= n and len(pivot_lows) >= n:
                break
                
        return pivot_highs, pivot_lows

    def _calculate_dynamic_grid(self) -> Tuple[float, float, Dict[str, Any]]:
        """
        璁＄畻鍔ㄦ€佺綉鏍煎尯闂?(浼樺寲鐗? 绉婚櫎 DF 渚濊禆)
        """
        # 1. 瀵绘壘娉㈡鐐?(Pivot Points)
        pivot_highs, pivot_lows = self._find_pivot_points(window=5, n=3)
        
        if not pivot_highs or not pivot_lows:
            # 鍥為€€鍒板熀鏈瀬鍊奸€昏緫
            lookback_data = self._data_buffer[-100:]
            upper = max(d.high for d in lookback_data)
            lower = min(d.low for d in lookback_data)
        else:
            upper = max(p['price'] for p in pivot_highs)
            lower = min(p['price'] for p in pivot_lows)

        range_size = upper - lower
        if range_size <= 0:
            range_size = upper * 0.01
            
        buffer = range_size * self.params['grid_buffer_pct']
        upper += buffer
        lower -= buffer

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
            return True, "杈惧埌寮哄埗閲嶇疆鍛ㄦ湡"

        if len(self._equity_history) > 0:
            recent_equity = self._equity_history[-1000:]
            peak = max(recent_equity)
            current = recent_equity[-1]
            if peak > 0:
                drawdown = (current - peak) / peak
                if drawdown <= -self.params['max_drawdown_reset']:
                    return True, f"瑙﹀彂鏈€澶у洖鎾ら檺鍒?({drawdown:.2%})"

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
                    reason=f"姝㈡崯瑙﹀彂 (姝㈡崯浠? ${stop_price:.2f})",
                    meta={'size_in_quote': False},
                ))
                self._peak_prices.pop(symbol, None)

        return signals

    def on_data(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        # 0. 缂撳啿鍖烘洿鏂颁笌鎸囨爣寮曟搸杩涗綅
        is_new_bar = (not self._last_bar_ts) or (data.timestamp > self._last_bar_ts)
        if is_new_bar:
            if self._last_bar_data:
                self.indicators.update(self._last_bar_data, commit=True)
            self._last_bar_ts = data.timestamp
            self._update_buffer(data)
        
        self._last_bar_data = data
        
        # 1. 姣忎竴鎷嶉兘杩涜鎸囨爣棰勮
        rsi, adx, ma, vol = self.indicators.update(data, commit=False)
        self.state.current_rsi = rsi
        self.state.current_adx = adx
        self.state.current_regime = self._detect_market_regime(adx, ma, data.close)

        if self.indicators.count < self.params['rsi_period']:
            return []

        signals: List[Signal] = []
        current_price = data.close
        current_high = data.high
        current_low = data.low

        self._equity_history.append(context.total_value)
        if len(self._equity_history) > 5000:
            self._equity_history = self._equity_history[-5000:]

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
                        reason=f"鍛ㄦ湡閲嶇疆: {reset_reason}",
                        meta={'size_in_quote': False},
                    ))
            self._reset_cycle(context)

        # 2. 璁＄畻鍔ㄦ€佺綉鏍艰竟鐣?
        upper, lower, meta = self._calculate_dynamic_grid()
        self.state.grid_upper = upper
        self.state.grid_lower = lower
        self.state.grid_prices = np.linspace(
            self.state.grid_lower,
            self.state.grid_upper,
            self.params['grid_levels']
        ).tolist()
        self.state.last_grid_update = self.indicators.count
        self.state.meta = meta 

        # 3. 姝㈡崯妫€娴?
        signals.extend(self._check_stop_loss(data, context))

        # 4. 浠撲綅閫昏緫
        oversold, overbought = self._get_adaptive_rsi_thresholds(vol)
        rsi_signal = self._get_rsi_signal(rsi, oversold, overbought)

        # 缃戞牸闂磋窛淇濇姢
        min_interval = self.params.get('min_trade_interval_pct', 0.0025)
        grid_interval_pct = min_interval
        if upper and lower and self.params['grid_levels'] > 1 and current_price > 0:
            grid_interval = abs(upper - lower) / (self.params['grid_levels'] - 1)
            grid_interval_pct = max(min_interval, (grid_interval / current_price) * 0.8)
            grid_interval_pct = min(0.02, grid_interval_pct)

        if self.state.grid_prices and self.state.last_candle:
            last_high = self.state.last_candle['high']
            last_low = self.state.last_candle['low']

            for grid_price in self.state.grid_prices:
                # 涔板叆閫昏緫
                if last_low > grid_price and current_low <= grid_price:
                    current_layers = self._estimate_position_layers(context, current_price)
                    if current_layers >= self.params['max_positions']:
                        continue
                    if rsi >= self.params['rsi_extreme_buy']:
                        continue

                    current_pos = context.positions.get(self.symbol)
                    if current_pos and current_pos.size > 0:
                        if current_price > current_pos.avg_price * (1 - grid_interval_pct):
                            continue

                    size = self._calculate_position_size(context, rsi_signal, is_buy=True)
                    if size < self.params['min_order_usdt']: size = self.params['min_order_usdt']
                    
                    if size <= context.cash * 0.95:
                        signals.append(Signal(
                            timestamp=data.timestamp, symbol=self.symbol, side=Side.BUY,
                            size=size, price=None, order_type=OrderType.MARKET,
                            confidence=abs(rsi_signal),
                            reason=f"缃戞牸涔板叆 @ {grid_price:.2f} (RSI: {rsi:.1f})",
                            meta={'size_in_quote': True},
                        ))
                    break

                # 鍗栧嚭閫昏緫
                if last_high < grid_price and current_high >= grid_price:
                    current_pos = context.positions.get(self.symbol)
                    if current_pos and current_pos.size > 0:
                        if current_price > current_pos.avg_price * (1 + grid_interval_pct):
                            if rsi <= self.params['rsi_extreme_sell']:
                                continue
                            current_layers = self._estimate_position_layers(context, current_price)
                            sell_size = min(current_pos.size, current_pos.size / max(1, current_layers))
                            signals.append(Signal(
                                timestamp=data.timestamp, symbol=self.symbol, side=Side.SELL,
                                size=sell_size, price=None, order_type=OrderType.MARKET,
                                confidence=abs(rsi_signal),
                                reason=f"缃戞牸鍗栧嚭 @ {grid_price:.2f} (RSI: {rsi:.1f})",
                                meta={'size_in_quote': False},
                            ))
                            break

        self.state.last_candle = {
            'open': data.open, 'high': data.high, 'low': data.low, 'close': data.close,
        }
        return signals

    def on_fill(self, fill: FillEvent):
        if fill.side == Side.BUY:
            self.state.grid_touch_count += 1

    def get_status(self, context: Optional[StrategyContext] = None) -> Dict[str, Any]:
        try:
            # 鑾峰彇褰撳墠棰勮鎸囨爣
            vol = 0.0 # 绠€鍖?
            oversold, overbought = self._get_adaptive_rsi_thresholds(0.1) # 榛樿
            rsi = self.state.current_rsi
            rsi_signal = self._get_rsi_signal(rsi, oversold, overbought)
        except Exception:
            oversold, overbought = self.params['rsi_oversold'], self.params['rsi_overbought']
            rsi_signal = 0.0

        signal_text = "瑙傛湜"
        signal_color = "neutral"
        if rsi_signal > 0.3:
            signal_text = f"涔板叆淇″彿 ({rsi_signal:+.2f})"
            signal_color = "buy"
        elif rsi_signal < -0.3:
            signal_text = f"鍗栧嚭淇″彿 ({rsi_signal:+.2f})"
            signal_color = "sell"

        in_grid = ""
        current_price = self._current_prices.get(self.symbol, 0) if hasattr(self, '_current_prices') else 0
        if self.state.grid_lower is not None and self.state.grid_upper is not None and current_price > 0:
            if current_price < self.state.grid_lower:
                in_grid = "浣庝簬缃戞牸"
            elif current_price > self.state.grid_upper:
                in_grid = "楂樹簬缃戞牸"
            else:
                in_grid = "缃戞牸鍐?

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
