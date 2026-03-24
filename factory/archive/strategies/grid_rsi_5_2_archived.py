"""
鍔ㄦ€佺綉鏍?RSI 绛栫暐 V5.2 (Refactored) 鈥?楂樻€ц兘瑙ｈ€︽灦鏋?

鏍稿績鏀硅繘 (鐩歌緝 V5.1):
  1. 鏋舵瀯瑙ｈ€? IncrementalIndicators / RiskController / GridEngine / DualSignalMatrix
  2. 鎬ц兘闈╁懡: 鍘?Pandas, O(1) 澧為噺鎸囨爣, deque 鍐呭瓨浼樺寲
  3. 澶栭儴JSON閰嶇疆: 35 鍙傛暟鍙澶栭儴 Agent 鐑洿鏂?
  4. 鍙屾ā寮忕儹鍔犺浇: 瀹氭湡杞 + .reload 鏍囪鏂囦欢涓诲姩 Push
"""

from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path
import json, time as _time
import numpy as np
from collections import deque

from console.core import (
    Signal, MarketData, StrategyContext, FillEvent,
    Side, OrderType, MarketRegime
)
from .base import BaseStrategy

# ============================================================
# 1. 甯搁噺
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
    STRONG_BULLISH: "鏋佸己鐗涘競 鈫戔啈", BULLISH: "鐪嬫定瓒嬪娍 鈫?,
    NEUTRAL: "涓€у亸鍖洪棿 鈫?, BEARISH: "鐪嬭穼瓒嬪娍 鈫?,
    STRONG_BEARISH: "鏋佸己鐔婂競 鈫撯啌",
}

# 榛樿鍙傛暟锛堜唬鐮佸唴纭紪鐮佷繚搴曪紝JSON
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

# 鎸囨爣寮曟搸閲嶇疆鏍囪 (淇敼杩欎簺鍙傛暟闇€瑕侀噸缃寚鏍?
RESET_PARAMS = {'macd_fast', 'macd_slow', 'macd_signal', 'rsi_period', 'atr_period'}

# ============================================================
# 2. 鐘舵€佸鍣?(绾暟鎹紝鏃犻€昏緫)
# ============================================================
@dataclass
class StrategyState:
    last_candle: Optional[Dict[str, float]] = None
    last_trade_ts: float = 0.0
    # 鎸囨爣
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
    # 缃戞牸
    grid_upper: Optional[float] = None
    grid_lower: Optional[float] = None
    grid_prices: List[float] = field(default_factory=list)
    grid_touch_count: int = 0
    last_grid_update: int = 0
    actual_levels: int = 10
    pivots: Dict[str, Any] = field(default_factory=dict)
    last_action: str = 'hold'
    # 椋庢帶
    conservative_mode: bool = False
    consecutive_conflict: int = 0
    black_swan_pause_until: float = 0.0

# ============================================================
# 3. O(1) 澧為噺鎸囨爣寮曟搸
# ============================================================
class IncrementalIndicators:
    """娴佸紡澧為噺璁＄畻: MACD / RSI / ATR锛屾瘡 tick O(1)銆?""
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
# 4-A. 椋庢帶寮曟搸
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
            
            # 浣跨敤 entry_price 鍏滃簳锛岄槻姝㈤噸鍚悗鍒濆宄板€间负 0 瀵艰嚧绔嬪嵆姝㈡崯
            pk = self._peaks[sym] = max(self._peaks.get(sym, pos.avg_price), cp)
            
            if pos.avg_price <= 0: continue
            pnl = (cp - pos.avg_price) / pos.avg_price
            
            # 绉诲姩姝㈢泩: 鐩堝埄 > trigger 涓?MACD 鏌辩姸鍥炬敹缂?
            shrink = abs(s.histogram) < abs(s.prev_histogram) and abs(s.prev_histogram) > 1e-12
            if self.p['trailing_stop'] and pnl >= self.p['trailing_trigger_pct'] and shrink:
                tp = pk * (1 - self.p['trailing_stop_pct'])
                if cp <= tp:
                    sigs.append(self._sell(d, sym, pos.size, f"绉诲姩姝㈢泩 (Peak:${pk:.2f},PNL:{pnl*100:.1f}%)"))
                    self._peaks.pop(sym, None); continue
            
            # 甯歌姝㈡崯 (鍩轰簬绉诲姩宄板€兼垨鍥哄畾鍧囦环)
            sl_pct = self.p['stop_loss_pct']
            sp = pk * (1 - self.p['trailing_stop_pct']) if self.p['trailing_stop'] and pnl > 0.01 else pos.avg_price * (1 - sl_pct)
            
            if cp <= sp:
                sigs.append(self._sell(d, sym, pos.size, f"姝㈡崯(Price:${cp:.2f} <= Limit:${sp:.2f})"))
                self._peaks.pop(sym, None)
        return sigs

    def check_death_cross(self, d: MarketData, ctx: StrategyContext, s: StrategyState) -> List[Signal]:
        if not (s.prev_macd_line > s.prev_signal_line and s.macd_line < s.signal_line): return []
        # 鏂规A锛氬彧鍦ㄩ浂杞翠笅鏂圭殑缁濆绌哄ご瓒嬪娍涓彂鐢熸鍙夋墠娓呬粨锛岄浂杞翠笂鏂圭殑澶氬ご鍥炴挙涓嶇珛鍒绘竻浠?
        if s.macd_line >= 0: return []
        
        # 澧炲姞 RSI 淇濇姢锛氬鏋滃綋鍓嶅浜庤秴鍗栧尯鍩?(鎴栨帴杩戣秴鍗?锛屽垯涓嶆墽琛岃秼鍔挎竻浠擄紝闃叉鈥滅涔扮鍗栤€?
        # 鐞嗙敱锛氱綉鏍肩瓥鐣ュ湪瓒呭崠鍖烘槸涔板叆鎸佷粨鏈燂紝姝ゆ椂鍗充究 MACD 姝诲弶涔熷涓轰綆浣嶉渿鑽′俊鍙?
        rsi_limit = self.p['rsi_zone_oversold'] + 5
        if s.current_rsi < rsi_limit:
            return []
        pos = ctx.positions.get(self.symbol)
        if pos and pos.size > 0:
            self._peaks.pop(self.symbol, None)
            return [self._sell(d, self.symbol, pos.size, f"MACD姝诲弶娓呬粨({s.macd_line:.4f})")]
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
# 4-B. 缃戞牸寮曟搸
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
            # 鏀拺浣嶆悳绱? i 蹇呴』鏄?[i-w, min(i+w, end)] 鑼冨洿鍐呯殑鏈€灏忓€?
            win_start = max(0, i - w)
            win_end = min(end, i + w)
            
            if lows[i] <= float(np.min(lows[win_start:win_end+1])):
                tp = 'confirmed' if i <= end - w else 'realtime'
                p_data = {'price': float(lows[i]), 'index': i, 'type': tp}
                if times and i < len(times): p_data['time'] = times[i]
                pl.append(p_data)
                    
            if highs[i] >= float(np.max(highs[win_start:win_end+1])):
                tp = 'confirmed' if i <= end - w else 'realtime'
                p_data = {'price': float(highs[i]), 'index': i, 'type': tp}
                if times and i < len(times): p_data['time'] = times[i]
                ph.append(p_data)
        # 1. 璁＄畻姣忎釜鍊欓€夌偣鐨勬樉钁楀害 (Prominence)
        # 鏄捐憲搴﹀畾涔夛細鐐逛綅浠锋牸涓庡眬閮ㄧ獥鍙?[i-w, i+w] 鍐呭潎鍊肩殑鍋忓樊
        for p in ph:
            idx = p['index']
            win = highs[max(0, idx-w):min(end, idx+w)+1]
            p['prominence'] = abs(p['price'] - np.mean(win))
            
        for p in pl:
            idx = p['index']
            win = lows[max(0, idx-w):min(end, idx+w)+1]
            p['prominence'] = abs(p['price'] - np.mean(win))

        # 2. 鍚屼竴娉㈡绔炰簤鍘婚噸 (濡傛灉涓や釜鐐归棿璺?< w锛岃涓哄悓涓€涓尝娈典簨浠讹紝浠呯暀鏈€鏄捐憲鐨?
        def filter_cluster(pivots):
            if not pivots: return []
            # 鍏堟寜鏄捐憲搴﹂檷搴忔帓
            sorted_p = sorted(pivots, key=lambda x: x['prominence'], reverse=True)
            kept = []
            for p in sorted_p:
                # 濡傛灉杩欎釜鐐硅窛绂诲凡閫変腑鐨勭偣澶繎锛堝湪鍚屼竴涓垽瀹氱獥鍙ｅ唴锛夛紝鍒欒垗寮?
                if not any(abs(p['index'] - k['index']) < w for k in kept):
                    kept.append(p)
            return kept

        ph_clean = filter_cluster(ph)
        pl_clean = filter_cluster(pl)

        # 3. 鏈€缁堥€夋嫈锛氭寜鏄捐憲搴﹀彇鍓?n 鍚?
        final_ph = sorted(ph_clean, key=lambda x: x['prominence'], reverse=True)[:n]
        final_pl = sorted(pl_clean, key=lambda x: x['prominence'], reverse=True)[:n]
        
        # 4. 鏈€鍚庢寜绱㈠紩(鏃堕棿)閲嶆柊鎺掑洖鍗囧簭锛屾柟渚垮墠绔粯鍥?
        final_ph.sort(key=lambda x: x['index'])
        final_pl.sort(key=lambda x: x['index'])
        
        return final_ph, final_pl

    def calculate(self, highs: np.ndarray, lows: np.ndarray,
                  price: float, s: StrategyState,
                  rsi_sig: float, times: Optional[List[float]] = None) -> Tuple[float, float, dict]:
        ph, pl = self.find_pivots(highs, lows, times)
        lb = min(self.p['pivot_lookback'], len(highs))
        
        # 1. 鍩虹杈圭晫锛氬懆鏈熷唴鐨勫叏灞€鏈€楂?鏈€浣?(浣滀负淇濆簳锛岀‘淇濅笉浼氭紡鎺夋樉钁楁瀬鍊?
        abs_upper = float(np.max(highs[-lb:]))
        abs_lower = float(np.min(lows[-lb:]))
        
        if not ph or not pl:
            upper, lower = abs_upper, abs_lower
        else:
            # 2. 缁撳悎 Pivot 鐐逛綅锛氶€夊彇 Pivot 鍒楄〃涓殑鏈€鏋佺鍊?
            p_upper = max(p['price'] for p in ph)
            p_lower = min(p['price'] for p in pl)
            
            # 3. 缁煎悎鍐崇瓥锛氬彇 Pivot 鏋佸€煎拰鍏ㄥ眬鏋佸€间腑鏇存瀬绔殑閭ｄ釜
            upper = max(p_upper, abs_upper)
            lower = min(p_lower, abs_lower)
            
        rng = upper - lower if upper > lower else upper * 0.01
        # ATR 鑷€傚簲闂磋窛
        atr_sp = s.current_atr / price if s.current_atr > 0 and price > 0 else 0
        spacing = np.clip(atr_sp, self.p['grid_spacing_min'], self.p['grid_spacing_max'])
        
        # 寮哄埗鏈€灏忕綉鏍艰法搴︼紝闃叉鏋佺獎鍖洪棿瀵艰嚧缃戞牸杩囧害瀵嗛泦
        min_rng = price * spacing * (self.p['grid_levels'] - 1)
        if rng < min_rng:
            mid = (upper + lower) / 2
            upper = mid + min_rng / 2
            lower = mid - min_rng / 2
            rng = min_rng
            
        # 鏍规嵁鍔ㄦ€佹墿鍏呭悗瀹為檯璺ㄥ害鍜岄棿璺濊绠楀悎鐞嗙殑鍔ㄦ€佸埢搴︽暟
        dyn_num = max(3, int(rng / (price * spacing)) + 1)
        
        buf = rng * self.p['grid_buffer_pct']
        upper += buf; lower -= buf
        # MACD 瓒嬪娍鍋忕Щ
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
        # RSI 寰皟
        if self.p['rsi_weight'] > 0:
            shift = rng * rsi_sig * self.p['rsi_weight'] * 0.2
            upper += shift; lower += shift
        return upper, lower, {'pivots_high': ph, 'pivots_low': pl,
                              'atr_spacing': float(spacing), 'dynamic_grid_num': dyn_num}

# ============================================================
# 4-C. 鍙屾寚鏍囩煩闃?
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
# 5. 绛栫暐涓荤被
# ============================================================
class GridRSIStrategyV5_2(BaseStrategy):
    """鍔ㄦ€佺綉鏍?RSI 绛栫暐 V5.2 鈥?楂樻€ц兘瑙ｈ€?+ JSON 鐑姞杞?""

    def __init__(self, symbol: str = "BTC-USDT",
                 config_path: Optional[str] = None, **overrides):
        super().__init__(name="GridRSI_V5.2")
        self.symbol = symbol

        # 涓夊眰浼樺厛绾? 榛樿鍊?< JSON 鏂囦欢 < 浠ｇ爜浼犲弬
        self._config_path = Path(config_path) if config_path else None
        self._last_config_mtime: float = 0.0
        self._tick_since_check: int = 0
        self.params: Dict[str, Any] = {**_DEFAULT_PARAMS}
        self.params_path = self._config_path # 鍏煎鎬у睘鎬?
        self._apply_config_file()
        self.params.update({k: v for k, v in overrides.items() if k in _DEFAULT_PARAMS})

        # 鍏冩暟鎹姞杞?
        self.param_metadata: Dict[str, Any] = {}
        self._load_param_metadata()

        # 缁勪欢瀹炰緥鍖?
        self.state = StrategyState()
        self.indicators = IncrementalIndicators(self.params)
        self.risk_ctrl = RiskController(self.params, self.symbol)
        self.grid_engine = GridEngine(self.params)

        # deque 缂撳啿
        buf = max(self.params['macd_slow'] + self.params['macd_signal'],
                  self.params['rsi_period'], self.params['atr_period']) * 3 + 100
        self._close_buf: deque = deque(maxlen=buf)
        self._high_buf:  deque = deque(maxlen=buf)
        self._low_buf:   deque = deque(maxlen=buf)
        self._data_buffer: deque = deque(maxlen=buf) # 鍏煎鎬? 瀛樺偍 MarketData 瀵硅薄
        self._current_prices: Dict[str, float] = {}
        self._equity_history: deque = deque(maxlen=5000)

    # 鈹€鈹€ 閰嶇疆鐑姞杞?鈹€鈹€
    def _apply_config_file(self):
        if not self._config_path or not self._config_path.exists():
            return
        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 鏇存柊鍙傛暟
            self.params.update({k: v for k, v in data.items() if k in _DEFAULT_PARAMS or k == 'symbol'})
            # 濡傛灉閰嶇疆涓湁 symbol锛屽悓姝ユ洿鏂扮瓥鐣ュ疄渚嬬殑 symbol 灞炴€?
            if 'symbol' in data:
                self.symbol = data['symbol']
            self._last_config_mtime = self._config_path.stat().st_mtime
        except Exception as e:
            print(f"[V5.2] 閰嶇疆鍔犺浇澶辫触: {e}")

    def _load_param_metadata(self):
        """鍔犺浇鍙傛暟璇存槑鍏冩暟鎹?(浠?JSON)"""
        if not self.params_path: return
        meta_path = self.params_path.with_name(self.params_path.stem.replace('_default', '') + '_meta.json')
        if not meta_path.exists():
            # 鍏滃簳锛氬皾璇曞浐瀹氬悕绉?
            meta_path = self.params_path.parent / "grid_v52_meta.json"
            
        if meta_path.exists():
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    self.param_metadata = json.load(f)
                    print(f"[V5.2] 鎴愬姛鍔犺浇鍙傛暟鍏冩暟鎹鏄? {meta_path.name}")
            except Exception as e:
                print(f"[V5.2] 鍔犺浇鍙傛暟鍏冩暟鎹け璐? {e}")

    def _maybe_reload_params(self):
        if not self._config_path: return
        reload_flag = self._config_path.with_suffix('.reload')
        need_reload = False
        # 涓诲姩 Push: Agent 鍒涘缓浜?.reload 鏂囦欢
        if reload_flag.exists():
            need_reload = True
            try: reload_flag.unlink()
            except: pass
        # 琚姩杞: 姣?100 tick
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
            # 澶囦唤鏃х殑鏍稿績鍙傛暟鐢ㄤ簬瀵规
            old = {k: self.params.get(k) for k in RESET_PARAMS}
            self._apply_config_file()
            self._load_param_metadata() # 鍚屾鍔犺浇鍏冩暟鎹鏄?
            # 濡傛灉寮曟搸鐩稿叧鍙傛暟鍙樹簡锛岄噸寤烘寚鏍囧紩鎿?
            if any(self.params.get(k) != old.get(k) for k in RESET_PARAMS):
                self.indicators = IncrementalIndicators(self.params)
                print(f"[V5.2] 鏍稿績鎸囨爣鍙傛暟鍙樻洿锛屾寚鏍囧紩鎿庡凡閲嶅缓")
            # 鍚屾缁勪欢寮曠敤
            self.risk_ctrl.p = self.params
            self.grid_engine.p = self.params
            cfg_name = self._config_path.name if self._config_path else "Unknown"
            print(f"[V5.2] 鍙傛暟鍙婂厓鏁版嵁宸茬儹鍔犺浇 ({cfg_name})")

    # 鈹€鈹€ 鍒濆鍖?鈹€鈹€
    def initialize(self):
        super().initialize()
        n = len(self._close_buf)
        self.state = StrategyState()
        self.indicators = IncrementalIndicators(self.params)
        self.risk_ctrl = RiskController(self.params, self.symbol)
        self._equity_history.clear()
        self._data_buffer.clear() # 涔熻娓呯悊鏁版嵁缂撳啿
        print(f"[V5.2] 閫昏緫閲嶇疆 (缂撳啿淇濈暀:{n}鏍?")

    def _update_buffer(self, data: MarketData):
        """鏍稿績鐘舵€佹洿鏂?(O(1) 澧為噺鏇存柊锛屼笉鐢熸垚淇″彿)"""
        self._close_buf.append(data.close)
        self._high_buf.append(data.high)
        self._low_buf.append(data.low)
        self._data_buffer.append(data) # 璁板綍鍏ㄩ噺鏁版嵁瀵硅薄
        self._current_prices[self.symbol] = data.close
        self.indicators.update(data, self.state)

    def _get_dataframe(self):
        """鍏煎鎬ф柟娉? 灏?deque 杞崲涓?DataFrame"""
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
        """鍏煎鎬ф帴鍙? 鍖呰 GridEngine 鐨?calculate 鏂规硶"""
        # 濡傛灉鎻愪緵浜?df锛屼紭鍏堜娇鐢?df
        if df is not None:
            h, l, c = df['high'].values, df['low'].values, df['close'].values[-1]
        else:
            h, l, c = np.array(self._high_buf), np.array(self._low_buf), self._close_buf[-1] if self._close_buf else 0
        
        # 涓轰簡婊¤冻 LiveEngine 瀵硅繑鍥炲€?(upper, lower, meta) 鐨勮В鏋勯渶姹?
        # 娉ㄦ剰: GridEngine.calculate 闇€瑕?rsi_sig 鍙備笌骞宠　锛岄鐑椂浼?0
        up, lo, meta = self.grid_engine.calculate(h, l, c, self.state, 0.0)
        return up, lo, meta

    # 鈹€鈹€ 瓒嬪娍鍒ゅ埆 鈹€鈹€
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

    # 鈹€鈹€ RSI 淇″彿 鈹€鈹€
    def _rsi_signal(self) -> Tuple[float, float, float]:
        p = self.params
        os, ob = p['rsi_zone_oversold'], p['rsi_zone_overbought']
        # 鑷€傚簲闃堝€?
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

    # 鈹€鈹€ 浠撲綅璁＄畻 鈹€鈹€
    def _calc_size(self, ctx: StrategyContext, rsi_sig: float, is_buy: bool) -> float:
        n = max(1, len(self.state.grid_prices))
        sz = ctx.total_value / n * (1 + _TREND_BOOST.get(self.state.trend_strength, 0))
        sz *= 1 - abs(self.state.current_rsi - 50) / 100  # RSI 鍋忕鎶樻墸
        if is_buy and self.state.macd_line < 0: sz *= 0.5
        if self.state.conservative_mode: sz *= 0.5
        return min(max(sz, self.params['min_order_usdt']), ctx.cash * 0.95)

    def _pos_layers(self, ctx: StrategyContext, cp: float) -> int:
        pos = ctx.positions.get(self.symbol)
        if not pos or pos.size <= 0: return 0
        sz_per_layer = self._calc_size(ctx, 0, True) # USDT 浠峰€?
        # 淇鍗曚綅閿欒: 灏?BTC 鏁伴噺 * 褰撳墠浠锋牸 鎹㈢畻鍥?USDT 鍐嶈绠楀眰鏁?
        pos_val = pos.size * cp
        return max(1, int(round(pos_val / sz_per_layer)))

    # 鈹€鈹€ 鍛ㄦ湡閲嶇疆 鈹€鈹€
    def _check_reset(self, ctx: StrategyContext) -> Tuple[bool, str]:
        if len(self._close_buf) - self.state.last_grid_update >= self.params['cycle_reset_period']:
            return True, "寮哄埗閲嶇疆鍛ㄦ湡"
        if self._equity_history:
            pk = max(self._equity_history)
            if pk > 0:
                dd = (self._equity_history[-1] - pk) / pk
                if dd <= -self.params['max_drawdown_reset']:
                    return True, f"鏈€澶у洖鎾?{dd:.2%})"
        return False, ""

    # 鈹€鈹€ 缃戞牸浜ゆ槗淇″彿 鈹€鈹€
    def _grid_orders(self, d: MarketData, ctx: StrategyContext,
                     action: str, strength: int, rsi_sig: float) -> List[Signal]:
        sigs: List[Signal] = []
        p, s = self.params, self.state
        cp, ch, cl = d.close, d.high, d.low
        if not s.grid_prices or not s.last_candle: return sigs

        # 鏈€灏忛棿璺?
        min_iv = p['min_trade_interval_pct']
        gip = min_iv
        if s.grid_upper and s.grid_lower and s.actual_levels > 1 and cp > 0:
            gi = abs(s.grid_upper - s.grid_lower) / (s.actual_levels - 1)
            gip = np.clip((gi / cp) * 0.8, min_iv, 0.02)

        lh, ll = s.last_candle['high'], s.last_candle['low']

        # 涔板叆
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
                    reason=f"缃戞牸涔板叆@{gp:.2f}(RSI:{s.current_rsi:.1f} {s.trend_strength} 鈽厈strength})",
                    meta={'size_in_quote': True}))
                break

        # 鍗栧嚭
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
                        reason=f"缃戞牸鍗栧嚭@{gp:.2f}(RSI:{s.current_rsi:.1f} {s.trend_strength} 鈽厈strength})",
                        meta={'size_in_quote': False}))
                    break
        return sigs

    # 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲
    # on_data 涓诲惊鐜?
    # 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲
    def on_data(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        signals: List[Signal] = []
        try: ts = data.timestamp.timestamp()
        except: ts = _time.time()

        # 0. 鐑姞杞芥鏌?
        self._maybe_reload_params()

        # 1 & 2. 缂撳啿涓庢寚鏍囨洿鏂?(澶嶇敤鍏煎鎬ф柟娉?
        self._update_buffer(data)

        # 妫€鏌ラ鐑槸鍚﹀畬鎴?(IncrementalIndicators 鐨勯€昏緫)
        if not self.indicators.warmup_done:
            self.state.last_candle = {'open': data.open, 'high': data.high, 'low': data.low, 'close': data.close}
            return []

        # 3. 瓒嬪娍
        self._update_trend()

        # 4. RSI
        rsi_sig, oversold, overbought = self._rsi_signal()

        # 5. 缃戞牸
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

        # 6. 椋庢帶
        self.risk_ctrl.check_anomaly(self.state, rsi_sig)
        if self.risk_ctrl.check_black_swan(self._close_buf, ts, self.state):
            for sym, pos in context.positions.items():
                if sym == self.symbol and pos.size > 0:
                    signals.append(RiskController._sell(data, sym, pos.size, "榛戝ぉ楣呯揣鎬ユ鎹?))
            self.state.last_candle = {'open': data.open, 'high': data.high, 'low': data.low, 'close': data.close}
            return signals

        ok, reason = self._check_reset(context)
        if ok:
            for sym, pos in context.positions.items():
                if sym == self.symbol and pos.size > 0:
                    signals.append(RiskController._sell(data, sym, pos.size, f"鍛ㄦ湡閲嶇疆:{reason}"))
            self.state.grid_upper = self.state.grid_lower = None
            self.state.last_grid_update = len(self._close_buf)
            self.state.conservative_mode = False; self.state.consecutive_conflict = 0

        signals.extend(self.risk_ctrl.check_stop_loss(data, context, self.state))
        signals.extend(self.risk_ctrl.check_death_cross(data, context, self.state))

        # 7. 鐭╅樀 + 缃戞牸瑙﹀彂
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

    # 鈹€鈹€ 鐘舵€佹姤鍛?鈹€鈹€
    def get_status(self, context: Optional[StrategyContext] = None) -> Dict[str, Any]:
        # 纭繚 Dashboard 鑾峰彇鐨勬槸鏈€鏂扮殑鍙傛暟鍊?
        self._maybe_reload_params()
        s, p = self.state, self.params
        rsi_sig, os_v, ob_v = self._rsi_signal()
        strength, action = dual_evaluate(s.trend_strength, s.current_rsi, p)
        # 淇″彿鏂囧瓧
        _ACT_TEXT = {
            'heavy_buy': ('buy', lambda st, rs: f"涔板叆淇″彿 鈽厈st} ({rs:+.2f})"),
            'buy':       ('buy', lambda st, rs: f"涔板叆淇″彿 鈽厈st} ({rs:+.2f})"),
            'light_buy': ('buy', lambda st, rs: f"杞讳粨涔板叆 鈽厈st} ({rs:+.2f})"),
            'sell':      ('sell', lambda st, rs: f"鍗栧嚭淇″彿 鈽厈st} ({rs:+.2f})"),
            'reduce':    ('sell', lambda st, rs: f"鍗栧嚭淇″彿 鈽厈st} ({rs:+.2f})"),
            'stop':      ('sell', lambda st, rs: "鍋滄浜ゆ槗"),
        }
        color, fmt = _ACT_TEXT.get(action, ('neutral', lambda st, rs: "瑙傛湜"))
        cp = self._current_prices.get(self.symbol, 0)
        in_grid = ""
        if s.grid_lower is not None and s.grid_upper is not None and cp > 0:
            in_grid = "浣庝簬缃戞牸" if cp < s.grid_lower else ("楂樹簬缃戞牸" if cp > s.grid_upper else "缃戞牸鍐?)
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
            'macd_trend': _TREND_LABELS.get(s.trend_strength, "鏈煡"),
            'trend_strength': s.trend_strength, 'current_atr': s.current_atr,
            'dual_strength': strength, 'dual_action': action,
            'conservative_mode': s.conservative_mode,
            'param_metadata': getattr(self, 'param_metadata', {}),
        }
