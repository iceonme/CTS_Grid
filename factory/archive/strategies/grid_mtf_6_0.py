import os
import json
import numpy as np
import pandas as pd
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from collections import deque

from console.core import (
    MarketData, Signal, Side, OrderType, 
    FillEvent, Position, StrategyContext
)
from cartridges.strategies.base import BaseStrategy

# ============================================================
# V6.0-Revival 楂樻€ц兘澧為噺鎸囨爣寮曟搸 (1m / 5m)
# ============================================================

class IncrementalIndicatorsV6:
    def __init__(self, p: dict):
        self.p = p
        self.count_1m = 0
        self.count_5m = 0
        
        # RSI 1m (SMA Based)
        self.rsi_period = p.get('rsi_period', 14)
        self.gain_dq = deque(maxlen=self.rsi_period)
        self.loss_dq = deque(maxlen=self.rsi_period)
        self.gain_sum = 0.0
        self.loss_sum = 0.0
        self.prev_close_1m = 0.0
        
        # MACD 1m (EMA Based - Fixed Cycle)
        self.m_fast = p.get('macd_fast', 12)
        self.m_slow = p.get('macd_slow', 26)
        self.m_sig = p.get('macd_signal', 9)
        self.ema_f = 0.0
        self.ema_s = 0.0
        self.ema_sig = 0.0
        self.count_macd = 0  # 杩借釜 MACD 鏇存柊娆℃暟
        self.alpha_f = 2.0 / (self.m_fast + 1)
        self.alpha_s = 2.0 / (self.m_slow + 1)
        self.alpha_sig = 2.0 / (self.m_sig + 1)

    def update_1m(self, d: MarketData, commit: bool = True):
        c = d.close
        if self.count_1m == 0:
            if commit:
                self.prev_close_1m = c
                self.count_1m += 1
            return 50.0

        diff = c - self.prev_close_1m
        gain = max(diff, 0); loss = max(-diff, 0)

        def get_sma(dq, cur_sum, val, p):
            count = len(dq)
            if count == 0: return val
            s = cur_sum + val - (dq[0] if count == p else 0)
            return s / (count if count < p else p)

        rsi_g = get_sma(self.gain_dq, self.gain_sum, gain, self.rsi_period)
        rsi_l = get_sma(self.loss_dq, self.loss_sum, loss, self.rsi_period)
        rs = rsi_g / rsi_l if rsi_l > 1e-9 else 100.0
        rsi = 100.0 - (100.0 / (1.0 + rs)) if rsi_l > 1e-9 else 100.0
        
        if commit:
            if len(self.gain_dq) == self.rsi_period: self.gain_sum -= self.gain_dq.popleft()
            self.gain_dq.append(gain); self.gain_sum += gain
            if len(self.loss_dq) == self.rsi_period: self.loss_sum -= self.loss_dq.popleft()
            self.loss_dq.append(loss); self.loss_sum += loss
            self.prev_close_1m = c
            self.count_1m += 1
            
        return rsi

    def update_1m_macd(self, close: float, commit: bool = True):
        """
        MACD 1m 瀹炴椂鎸囨爣璁＄畻
        """
        if self.count_macd == 0:
            if commit:
                self.ema_f = self.ema_s = close
                self.count_macd += 1
            return 0.0, 0.0, 0.0

        f = close * self.alpha_f + self.ema_f * (1 - self.alpha_f)
        s = close * self.alpha_s + self.ema_s * (1 - self.alpha_s)
        macd = f - s
        
        # 鏍稿績淇锛氫俊鍙风嚎鍒濆鍖?
        # 濡傛灉鏄涓€娆¤绠楀嚭 macd (count=1)锛屼俊鍙风嚎搴旂洿鎺ョ瓑浜?macd锛岃€屼笉鏄粠 0 寮€濮嬪钩婊?
        if self.count_macd == 1:
            sig = macd
        else:
            sig = macd * self.alpha_sig + self.ema_sig * (1 - self.alpha_sig)
            
        hist = macd - sig

        if commit:
            self.ema_f, self.ema_s, self.ema_sig = f, s, sig
            self.count_macd += 1
            
        return macd, sig, hist


# ============================================================
# V6.0-Revival 缃戞牸璁＄畻涓庣啍鏂?
# ============================================================

class GridCalculator:
    """缃戞牸璁＄畻鍣?(V6.0-Revival 鍒嗘鍘绘瀬鍊兼硶)"""
    
    @staticmethod
    def calculate_grid(price_data: List[MarketData], period_hours: int = 6, vol_threshold: float = 0.012) -> Dict:
        """
        璁＄畻6灏忔椂锛堟垨4灏忔椂锛夌綉鏍?
        1. 鍒?娈碉紝鍙栨瘡娈垫渶楂樻渶浣庣偣
        2. 鍘绘瀬鍊硷紙鍘?鏈€澶?鏈€灏忥級
        3. 鍓╀綑3楂?浣庡彇骞冲潎
        """
        if len(price_data) < 10:
            return None
            
        segment_size = max(1, len(price_data) // 5)
        
        highs = []
        lows = []
        
        for i in range(5):
            segment = price_data[i*segment_size : (i+1)*segment_size]
            if not segment: continue
            highs.append(max([c.high for c in segment]))
            lows.append(min([c.low for c in segment]))
        
        if len(highs) >= 5:
            highs.sort()
            lows.sort()
            # 鍘绘帀鏈€浣?涓拰鏈€楂?涓紝淇濈暀涓棿3涓?
            highs = highs[1:4]
            lows = lows[1:4]
            
        base_top = sum(highs) / len(highs)
        base_bottom = sum(lows) / len(lows)
        
        # 璁＄畻娉㈠姩鐜囧畾灞傛暟 (瑙勮寖: (Top - Bottom) / Bottom)
        volatility = (base_top - base_bottom) / base_bottom if base_bottom > 0 else 0
        n_layers = 7 if volatility > vol_threshold else 5
        
        # 鐢熸垚瀵圭О缃戞牸
        layers = []
        step = (base_top - base_bottom) / n_layers if n_layers > 0 else 0
        mid_price = (base_top + base_bottom) / 2
        
        # 瀹炰綋鑼冨洿璁惧畾
        entity_half = n_layers // 2
        # 鎬荤储寮曡寖鍥达細铏氭嫙灞備笂涓嬪悇鎵?灞?
        idx_min = -(entity_half + 2)
        idx_max = (entity_half + 2)
        
        for idx in range(idx_min, idx_max + 1):
            # 浠?mid_price 涓轰腑蹇冿紝L(0) 璺ㄨ秺涓績绾?
            l_bottom = mid_price + (idx - 0.5) * step
            l_top = mid_price + (idx + 0.5) * step
            
            l_type = "BUFFER" if idx == 0 else "ENTITY" if abs(idx) <= entity_half else "VIRTUAL"
            
            layers.append({
                "index": idx,
                "bottom": l_bottom,
                "top": l_top,
                "mid": (l_bottom + l_top) / 2,
                "type": l_type,
                "locked": False,
                "position": 0.0
            })
        
        return {
            "base_top": base_top,
            "base_bottom": base_bottom,
            "volatility": volatility,
            "n_layers": n_layers,
            "layers": layers,
            "mid_price": mid_price,
            "created_at": datetime.now(),
            "period_used": period_hours
        }

class CircuitBreaker:
    """1灏忔椂鐗╃悊鐔旀柇鍣?(鏀寔涓婁笅鍙屽悜鐮翠綅妫€娴?+ MACD鍏宠仈)"""
    def __init__(self, observation_period: int = 3600):
        self.status = "NORMAL"  # NORMAL / OBSERVING_UP / OBSERVING_DOWN
        self.observation_start = None
        self.observation_period = observation_period
    
    def check(self, price: float, virtual_grid: Dict) -> str:
        if not virtual_grid: return "NORMAL"
        
        if self.status == "NORMAL":
            if price > virtual_grid["top_2"]:
                self.status = "OBSERVING_UP"
                self.observation_start = datetime.now()
                return "OBSERVING_UP"
            elif price < virtual_grid["bottom_2"]:
                self.status = "OBSERVING_DOWN"
                self.observation_start = datetime.now()
                return "OBSERVING_DOWN"
            return "NORMAL"
            
        elif self.status in ["OBSERVING_UP", "OBSERVING_DOWN"]:
            if not self.observation_start:
                self.status = "NORMAL"
                return "NORMAL"
            
            elapsed = (datetime.now() - self.observation_start).total_seconds()
            
            # 浠锋牸鍥炲埌瀹夊叏鍖猴紝瑙ｉ櫎璀︽姤
            if virtual_grid["bottom_2"] <= price <= virtual_grid["top_2"]:
                self.status = "NORMAL"
                self.observation_start = None
                return "NORMAL"
                
            # 瑙傚療鏈熸弧锛岃繑鍥炵壒鍖栫殑閲嶇疆淇″彿渚涗富閫昏緫缁撳悎MACD浣跨敤
            if elapsed >= self.observation_period:
                res = "REBUILD_UP" if self.status == "OBSERVING_UP" else "REBUILD_DOWN"
                self.status = "NORMAL"
                self.observation_start = None
                return res
                
            return self.status
        return "NORMAL"


@dataclass
class StrategyState:
    current_rsi: float = 50.0
    macd: float = 0.0
    macdsignal: float = 0.0
    macdhist: float = 0.0
    macdhist_prev: float = 0.0
    
    grid: Optional[Dict] = None
    grid_period: int = 6
    
    # 妲戒綅绠＄悊: 鍒楄〃涓殑姣忎釜 dict 浠ｈ〃涓€绗旂嫭绔嬬殑涔板叆
    # 鏍煎紡: {"size": float, "buy_price": float, "layer_idx": int, "is_virtual": bool}
    slots: List[Dict] = field(default_factory=list)
    
    # 鍙鍖栧寮?
    grid_lines: List[float] = field(default_factory=list)
    l0_idx: int = 4  # 榛樿涓棿绱㈠紩
    
    is_halted: bool = False
    halt_reason: str = ""
    resume_time: Optional[datetime] = None
    last_volume: float = 0.0
    grid_lines: List[float] = field(default_factory=list)
    
    # 浠锋牸淇濇姢鐘舵€?
    last_marker_price: float = 0.0
    last_buy_price: float = 0.0
    last_sell_price: float = 0.0


class GridMTFStrategyV6_0(BaseStrategy):
    """
    V6.0-Revival 鍔ㄦ€佺綉鏍肩瓥鐣?
    """
    def __init__(self, name: str = "Grid_V60_Revival", **params):
        super().__init__(name, **params)
        
        current_file_dir = Path(__file__).parent.resolve()
        config_dir = current_file_dir.parent / "config"
        
        self.default_params_path = str(config_dir / 'grid_v60_default.json')
        self.params_path = str(config_dir / 'grid_v60_runtime.json')
        self.meta_path = self.params_path.replace('runtime.json', 'meta.json')
        self.symbol = params.get('symbol', 'BTCUSDT')
        self._data_1m = deque(maxlen=400)
        self._data_5m = deque(maxlen=100)
        
        self.state = StrategyState()
        
        # 鍐崇瓥杩借釜 (Trace Log): {timestamp_ms: [msg1, msg2, ...]}
        self.decision_trace = {}

        self.param_metadata = {}
        self._load_params()
        
        self._last_1m_ts: Optional[datetime] = None
        self._last_5m_ts: Optional[datetime] = None
        self._last_5m_bar_close = 0.0
        self._last_1m_bar = None

        self.state = StrategyState()
        self.indicators = IncrementalIndicatorsV6(self.params)
        self.breaker = CircuitBreaker(self.params.get('observation_period', 3600))
        
        self.total_capital = self.params.get('total_capital', 10000.0)

    def _load_params(self):
        if os.path.exists(self.default_params_path):
            try:
                with open(self.default_params_path, 'r', encoding='utf-8') as f:
                    self.params.update(json.load(f))
            except Exception as e:
                print(f"[V6.0] Load default params failed: {e}")

        if os.path.exists(self.params_path):
            try:
                with open(self.params_path, 'r', encoding='utf-8') as f:
                    self.params.update(json.load(f))
            except Exception as e:
                print(f"[V6.0] Load runtime params failed: {e}")
        
        if os.path.exists(self.meta_path):
            try:
                with open(self.meta_path, 'r', encoding='utf-8') as f:
                    self.param_metadata = json.load(f)
            except Exception as e:
                print(f"[V6.0] Load meta failed: {e}")
                
        self.state.grid_period = self.params.get('grid_period_initial', 6)

    def _trace(self, ts_ms: int, msg: str):
        """璁板綍鍐崇瓥杩借釜鏃ュ織"""
        if ts_ms not in self.decision_trace:
            self.decision_trace[ts_ms] = []
        # 閬垮厤閲嶅璁板綍鐩稿悓娑堟伅
        if msg not in self.decision_trace[ts_ms]:
            self.decision_trace[ts_ms].append(msg)

    def initialize(self):
        super().initialize()
        self.decision_trace.clear()
        self.state = StrategyState()
        self.indicators = IncrementalIndicatorsV6(self.params)
        self.breaker = CircuitBreaker(self.params.get('observation_period', 3600))
        self._last_1m_ts = None
        self._last_1m_bar = None
        self._data_1m.clear()
        self._data_5m.clear()
        self._last_5m_ts = None
        self.state.last_marker_price = 0.0
        self.state.last_buy_price = 0.0
        self.state.last_sell_price = 0.0
        print(f"[V6.0-Revival] {self.name} 鍒濆鍖栧畬鎴?)

    def on_data(self, data: MarketData, context: Optional[StrategyContext]) -> List[Signal]:
        # 0. 1m K绾垮悎骞朵笌鎸囨爣鏇存柊 (RSI & MACD committed history)
        is_new_1m_bar = (not self._last_1m_ts) or (data.timestamp > self._last_1m_ts)
        if is_new_1m_bar:
            if self._last_1m_bar:
                self.indicators.update_1m(self._last_1m_bar, commit=True)
                _, _, hist_commit = self.indicators.update_1m_macd(self._last_1m_bar.close, commit=True)
                # 璁板綍涓婁竴鏍瑰凡纭K绾跨殑 MACD hist锛岀敤浜庡姣斿垽鏂綋鍓嶉噾鍙?姝诲弶
                self.state.macdhist_prev = hist_commit 
                
            self._last_1m_ts = data.timestamp
            self._update_data(data)
        self._last_1m_bar = data

        ts_ms = int(data.timestamp.timestamp() * 1000)
        if len(self._data_1m) < 10: return []

        # 1. 鎸囨爣瀹炴椂棰勮
        rsi = self.indicators.update_1m(data, commit=False)
        self.state.current_rsi = rsi
        self.state.last_volume = data.volume

        macd, sig, hist = self.indicators.update_1m_macd(data.close, commit=False)
        self.state.macd = macd
        self.state.macdsignal = sig
        self.state.macdhist = hist

        # 璁板綍鍩虹鐘舵€?Trace
        self._trace(ts_ms, f"Price: {data.close:.1f} | RSI: {rsi:.1f} | MACD: {hist:+.4f}")

        # 鍒ゆ柇 MACD 浜ゅ弶鐘舵€?(褰撳墠 tick 鐩稿鍓嶄竴鏍圭‘璁?K绾?鐨勭姸鎬?
        macd_golden = False
        macd_dead = False
        if self.state.macdhist > 0 and self.state.macdhist_prev <= 0:
            macd_golden = True
        elif self.state.macdhist < 0 and self.state.macdhist_prev >= 0:
            macd_dead = True
            
        self._macd_golden = macd_golden
        self._macd_dead = macd_dead

        # 3. 缃戞牸鏋勫缓涓庣啍鏂鐞?
        self._manage_grid(data)
        
        if not self.state.grid:
            return []
            
        grid = self.state.grid
        v_bounds = {
            "top_2": grid["layers"][-1]["top"],
            "bottom_2": grid["layers"][0]["bottom"]
        }
        breaker_status = self.breaker.check(data.close, v_bounds)
        
        # 鐮翠綅1灏忔椂鍚庤繘琛屾柟鍚戞€ч噸缃垽瀹?
        if breaker_status == "REBUILD_DOWN":
            if not macd_golden:
                self.state.grid_period = self.params.get('grid_period_rebuild', 4)
                self._trace(ts_ms, f"鈿狅笍 鐮翠綅閲嶇疆缃戞牸 (REBUILD_DOWN) | Period: {self.state.grid_period}h")
                self._rebuild_grid()
            else:
                self.state.is_halted = True
                self.state.halt_reason = "鐮翠綅浣哅ACD閲戝弶锛岀瓑寰呭洖韪?
                self._trace(ts_ms, f"馃洃 鐔旀柇: {self.state.halt_reason}")
            return []
            
        if breaker_status == "REBUILD_UP":
            if not macd_dead:
                self.state.grid_period = self.params.get('grid_period_rebuild', 4)
                self._trace(ts_ms, f"鈿狅笍 鐮翠綅閲嶇疆缃戞牸 (REBUILD_UP) | Period: {self.state.grid_period}h")
                self._rebuild_grid()
            else:
                self.state.is_halted = True
                self.state.halt_reason = "鐮翠綅浣哅ACD姝诲弶锛岀瓑寰呭洖璋?
                self._trace(ts_ms, f"馃洃 鐔旀柇: {self.state.halt_reason}")
            return []
            
        if breaker_status in ["OBSERVING_UP", "OBSERVING_DOWN"]:
            self.state.is_halted = True
            self.state.halt_reason = f"1灏忔椂瑙傚療鏈?({breaker_status})"
            self._trace(ts_ms, f"馃憖 {self.state.halt_reason}")
            return []
            
        self.state.is_halted = False
        self.state.halt_reason = ""

        # 4. 淇″彿鐢熸垚涓庝粨浣嶇鐞?
        if context:
            return self._generate_signals(data, context, ts_ms)
        return []

    def _update_data(self, data: MarketData):
        ts = data.timestamp
        # 1. 澶勭悊 1鍒嗛挓K绾?
        bar_1m_ts = ts.replace(second=0, microsecond=0)
        
        if self._data_1m and self._data_1m[-1].timestamp.replace(second=0, microsecond=0) == bar_1m_ts:
            last = self._data_1m[-1]
            updated = MarketData(
                timestamp=data.timestamp,
                symbol=data.symbol,
                open=last.open,
                high=max(last.high, data.high),
                low=min(last.low, data.low),
                close=data.close,
                volume=data.volume
            )
            self._data_1m[-1] = updated
        else:
            self._data_1m.append(data)
        
        # 2. 5m閲嶉噰鏍?(渚?MACD 浣跨敤)
        period_5m_ts = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        
        if self._last_5m_ts is None or period_5m_ts > self._last_5m_ts:
            self._last_5m_ts = period_5m_ts
            self._last_5m_bar_close = data.close
            self._data_5m.append({
                'timestamp': period_5m_ts,
                'open': data.open, 'high': data.high, 
                'low': data.low, 'close': data.close, 
                'volume': data.volume
            })
        else:
            bar = self._data_5m[-1]
            bar['high'] = max(bar['high'], data.high)
            bar['low'] = min(bar['low'], data.low)
            bar['close'] = data.close
            vol_sum = 0
            for i in range(len(self._data_1m) - 1, -1, -1):
                d = self._data_1m[i]
                d_period = d.timestamp.replace(minute=(d.timestamp.minute // 5) * 5, second=0, microsecond=0)
                if d_period < period_5m_ts: break
                if d_period == period_5m_ts:
                    vol_sum += d.volume
            bar['volume'] = vol_sum

    def _rebuild_grid(self):
        minutes_lookback = self.state.grid_period * 60
        history = list(self._data_1m)[-minutes_lookback:]
        vol_thr = self.params.get('volatility_threshold', 0.012)
        new_grid = GridCalculator.calculate_grid(history, self.state.grid_period, vol_thr)
        if new_grid:
            self.state.grid = new_grid
            # 鎻愬彇缃戞牸绾夸环鏍肩敤浜庡彲瑙嗗寲 (鍖呭惈鎵€鏈夊眰杈圭晫)
            lines = []
            layers = new_grid["layers"]
            if layers:
                lines.append(layers[0]["bottom"])
                for l in layers:
                    lines.append(l["top"])
            self.state.grid_lines = lines
            
            # 璁＄畻 L0 绱㈠紩 (鍗?type == "BUFFER" 鐨勫眰鍦?lines 涓殑璧峰绱㈠紩)
            l0_line_idx = 0
            for i, l in enumerate(layers):
                if l["type"] == "BUFFER":
                    l0_line_idx = i
                    break
            self.state.l0_idx = l0_line_idx

    def _manage_grid(self, data: MarketData):
        # 鍒濆鍖栫綉鏍?
        if self.state.grid is None:
            # 蹇呴』鏀掑 6 灏忔椂 (360 鏍?1m K绾? 鎵嶈兘鐢熸垚绗﹀悎 V6.0 瑕佹眰鐨勫垵濮嬬綉鏍?
            if len(self._data_1m) >= 360:
                self._rebuild_grid()

    def _generate_signals(self, data: MarketData, context: StrategyContext, ts_ms: int) -> List[Signal]:
        signals = []
        pos = context.positions.get(self.symbol)
        pos_size = float(pos.size) if pos else 0.0
        
        price = data.close
        grid = self.state.grid
        if not grid or not grid.get('layers'): return signals
        
        rsi = self.state.current_rsi
        macd_golden = self._macd_golden
        macd_dead = self._macd_dead
        
        # 1. 鑾峰彇褰撳墠灞?
        current_layer = next((l for l in grid["layers"] if l["bottom"] <= price <= l["top"]), None)
        if not current_layer: return signals
        
        layer_idx = current_layer["index"]
        # L(0) 瑙傛湜
        if layer_idx == 0: return signals

        # 浠锋牸缂撳啿 (2 BPS)
        price_buff = self.params.get('price_buffer_pct', 0.0002)

        # 2. 鍗栧嚭閫昏緫 (鎵ц灞?L1, L2, Lv1, Lv2)
        if layer_idx > 0 and pos_size > 0 and self.state.slots:
            # 鍒ゅ畾鍗栧嚭瑙﹀彂 (灞傚唴涓婂崐閮?50%)
            is_triggered = False
            if price >= current_layer["mid"]:
                if current_layer["type"] == "VIRTUAL":
                    # 铏氭嫙灞傚崠鍑鸿鍒欙細涓婂崐閮?+ (RSI > 75 鎴?MACD 姝诲弶)
                    rsi_sell_thr = self.params.get('rsi_sell', 75)
                    if rsi > rsi_sell_thr or macd_dead:
                        is_triggered = True
                else:
                    # 瀹炰綋灞傜洿鎺ュ崠鍑?(L1, L2)
                    is_triggered = True
            
            if is_triggered:
                # 鍚屼环浣嶄繚鎶?
                if self.state.last_sell_price > 0 and abs(price - self.state.last_sell_price) / self.state.last_sell_price < price_buff:
                    return signals
                
                # LIFO 寮瑰嚭
                target_slot = self.state.slots.pop()
                sell_size = min(target_slot["size"], pos_size)
                t_idx = target_slot["layer_idx"]
                
                if sell_size > 0:
                    signals.append(Signal(
                        timestamp=data.timestamp, symbol=self.symbol, side=Side.SELL,
                        size=sell_size, reason=f"LIFO Sell at L({layer_idx}) matches L({t_idx})",
                        meta={"rsi": rsi, "layer_idx": layer_idx, "matched_buy_idx": t_idx}
                    ))
                    # 瑙ｉ攣涔板叆鏃剁殑閭ｄ釜灞?
                    buy_layer = next((l for l in grid["layers"] if l["index"] == t_idx), None)
                    if buy_layer:
                        buy_layer['locked'] = False
                        buy_layer['position'] = max(0, buy_layer['position'] - sell_size)
                        
                    self.state.last_sell_price = price
                    self._trace(ts_ms, f"鎴愪氦鍗栧嚭: L({layer_idx}) 鍖归厤 L({t_idx}) | 浠锋牸: {price:.1f}")
                    return signals

        # 3. 涔板叆閫昏緫 (鎵ц灞?L-1, L-2, Lv-1, Lv-2)
        if layer_idx < 0:
            # 鍒ゅ畾涔板叆瑙﹀彂 (灞傚唴涓嬪崐閮?50%)
            is_triggered = False
            if price <= current_layer["mid"] and not current_layer["locked"]:
                if current_layer["type"] == "VIRTUAL":
                    # 铏氭嫙灞備拱鍏ヨ鍒欙細涓嬪崐閮?+ (RSI < 25 鎴?MACD 閲戝弶)
                    rsi_buy_thr = self.params.get('rsi_buy', 25)
                    if rsi < rsi_buy_thr or macd_golden:
                        is_triggered = True
                else:
                    # 瀹炰綋灞傜洿鎺ヤ拱鍏?(L-1, L-2)
                    is_triggered = True
            
            if is_triggered:
                if self.state.last_buy_price > 0 and abs(price - self.state.last_buy_price) / self.state.last_buy_price < price_buff:
                    return signals
                
                # 璁＄畻浠介
                n_layers = grid["n_layers"]
                base_cash = self.total_capital / n_layers
                weight = 2.0 if current_layer["type"] == "VIRTUAL" else 1.0
                buy_usdt = base_cash * weight
                
                if context.cash >= buy_usdt * 0.98:
                    signals.append(Signal(
                        timestamp=data.timestamp, symbol=self.symbol, side=Side.BUY,
                        size=buy_usdt, meta={'size_in_quote': True, "rsi": rsi, "layer_idx": layer_idx},
                        reason=f"Slot Buy at L({layer_idx})"
                    ))
                    self.state.last_buy_price = price
                    self.state.slots.append({
                        "size": buy_usdt / price,
                        "buy_price": price,
                        "layer_idx": layer_idx,
                        "ts": data.timestamp
                    })
                    current_layer['locked'] = True
                    current_layer['position'] += (buy_usdt / price)
                    self._trace(ts_ms, f"鎴愪氦涔板叆: L({layer_idx}) | 浠锋牸: {price:.1f} | 閲? {buy_usdt:.1f} USDT")

        return signals

    def _trace(self, ts_ms: int, msg: str):
        """璁板綍鍐崇瓥杩借釜鏃ュ織"""
        if ts_ms not in self.decision_trace:
            self.decision_trace[ts_ms] = []
        self.decision_trace[ts_ms].append(msg)

    def get_status(self, context: Optional[StrategyContext] = None) -> Dict[str, Any]:
        is_bullish = self.state.macdhist > 0
        macd_trend = "寮虹墰" if is_bullish and self.state.macdhist > self.state.macdhist_prev else "鐗涘競" if is_bullish else "闇囪崱"
        if self.state.macdhist < 0:
            macd_trend = "寮虹唺" if self.state.macdhist < self.state.macdhist_prev else "鐔婂競"
        
        signal_text = "绛夊緟閰嶇疆"
        signal_color = "neutral"
        
        if self.state.is_halted:
            signal_text = f"鐔旀柇: {self.state.halt_reason}"
            signal_color = "sell"
        elif is_bullish:
            signal_color = "buy"
            signal_text = "瓒嬪娍鎸佹湁涓?
            
        pos_size = 0.0
        pos_avg_price = 0.0
        pos_unrealized_pnl = 0.0
        if context and self.symbol in context.positions:
            pos = context.positions[self.symbol]
            pos_size = float(pos.size)
            pos_avg_price = float(pos.avg_price)
            pos_unrealized_pnl = float(pos.unrealized_pnl)

        grid_lower = self.state.grid["base_bottom"] if self.state.grid else 0.0
        grid_upper = self.state.grid["base_top"] if self.state.grid else 0.0
        grid_lines = self.state.grid_lines
        layers_info = []
        if self.state.grid:
            for l in self.state.grid["layers"]:
                status_str = f"L({l['index']}) [{l['type']}]: {'Locked' if l['locked'] else 'Open'} (Pos: {l['position']:.4f})"
                layers_info.append(status_str)

        return {
            'name': self.name,
            'current_rsi': round(self.state.current_rsi, 2),
            'macd': round(self.state.macd, 4),
            'macdsignal': round(self.state.macdsignal, 4),
            'macdhist': round(self.state.macdhist, 4),
            'atr': 0.0,
            'atrVal': 0.0,
            'macd_trend': macd_trend,
            'signal_text': signal_text,
            'signal_color': signal_color,
            'signal_strength': "涓?,
            'position_size': pos_size,
            'position_avg_price': pos_avg_price,
            'position_unrealized_pnl': pos_unrealized_pnl,
            'grid_lower': round(grid_lower, 2),
            'grid_upper': round(grid_upper, 2),
            'grid_range': f"{grid_lower:.1f} - {grid_upper:.1f}",
            'grid_lines': grid_lines,
            'layers_status': layers_info,
            'rsi_oversold': self.params.get('rsi_buy', 25),
            'rsi_overbought': self.params.get('rsi_sell', 75),
            'position_count': self.state.grid["n_layers"] if self.state.grid else 0,
            'marketRegime': "涓婂崌閫氶亾" if is_bullish else "璋冩暣闃舵",
            'vol_trend': "鎸佸钩",
            'current_volume': round(self.state.last_volume, 2),
            'is_halted': self.state.is_halted,
            'halt_reason': self.state.halt_reason,
            'pivots': {'pivots_high': [], 'pivots_low': []},
            'params': self.params,
            'param_metadata': self.param_metadata
        }
