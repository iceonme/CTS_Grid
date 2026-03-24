from datetime import datetime
from typing import List, Dict, Optional, Any
from collections import deque
from console.core import MarketData

# ============================================================
# V6.0指标计算引擎
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
        self.count_macd = 0
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
        if self.count_macd == 0:
            if commit:
                self.ema_f = self.ema_s = close
                self.count_macd += 1
            return 0.0, 0.0, 0.0

        f = close * self.alpha_f + self.ema_f * (1 - self.alpha_f)
        s = close * self.alpha_s + self.ema_s * (1 - self.alpha_s)
        macd = f - s
        
        if self.count_macd == 1:
            sig = macd
        else:
            sig = macd * self.alpha_sig + self.ema_sig * (1 - self.alpha_sig)
            
        hist = macd - sig

        if commit:
            self.ema_f, self.ema_s, self.ema_sig = f, s, sig
            self.count_macd += 1
            
        return macd, sig, hist


class GridCalculator:
    @staticmethod
    def calculate_grid(price_data: List[MarketData], period_hours: int = 6, vol_threshold: float = 0.012) -> Dict:
        if len(price_data) < 10: return None
        segment_size = max(1, len(price_data) // 5)
        highs, lows = [], []
        
        for i in range(5):
            segment = price_data[i*segment_size : (i+1)*segment_size]
            if not segment: continue
            highs.append(max([c.high for c in segment]))
            lows.append(min([c.low for c in segment]))
        
        if len(highs) >= 5:
            highs.sort(); lows.sort()
            highs = highs[1:4]; lows = lows[1:4]
            
        base_top = sum(highs) / len(highs)
        base_bottom = sum(lows) / len(lows)
        volatility = (base_top - base_bottom) / base_bottom if base_bottom > 0 else 0
        n_layers = 7 if volatility > vol_threshold else 5
        
        layers = []
        step = (base_top - base_bottom) / n_layers if n_layers > 0 else 0
        mid_price = (base_top + base_bottom) / 2
        entity_half = n_layers // 2
        
        for idx in range(-(entity_half + 2), (entity_half + 2) + 1):
            l_bottom = mid_price + (idx - 0.5) * step
            l_top = mid_price + (idx + 0.5) * step
            l_type = "BUFFER" if idx == 0 else "ENTITY" if abs(idx) <= entity_half else "VIRTUAL"
            layers.append({
                "index": idx, "bottom": l_bottom, "top": l_top,
                "mid": (l_bottom + l_top) / 2, "type": l_type,
                "locked": False, "position": 0.0
            })
        
        return {
            "base_top": base_top, "base_bottom": base_bottom,
            "volatility": volatility, "n_layers": n_layers, "layers": layers,
            "mid_price": mid_price, "created_at": datetime.now(), "period_used": period_hours
        }

class CircuitBreaker:
    def __init__(self, observation_period: int = 3600):
        self.status = "NORMAL"
        self.observation_start = None
        self.observation_period = observation_period
    
    def check(self, price: float, virtual_grid: Dict) -> str:
        if not virtual_grid: return "NORMAL"
        if self.status == "NORMAL":
            if price > virtual_grid["top_2"]:
                self.status = "OBSERVING_UP"; self.observation_start = datetime.now()
                return "OBSERVING_UP"
            elif price < virtual_grid["bottom_2"]:
                self.status = "OBSERVING_DOWN"; self.observation_start = datetime.now()
                return "OBSERVING_DOWN"
            return "NORMAL"
        elif self.status in ["OBSERVING_UP", "OBSERVING_DOWN"]:
            if not self.observation_start:
                self.status = "NORMAL"; return "NORMAL"
            elapsed = (datetime.now() - self.observation_start).total_seconds()
            if virtual_grid["bottom_2"] <= price <= virtual_grid["top_2"]:
                self.status = "NORMAL"; self.observation_start = None
                return "NORMAL"
            if elapsed >= self.observation_period:
                res = "REBUILD_UP" if self.status == "OBSERVING_UP" else "REBUILD_DOWN"
                self.status = "NORMAL"; self.observation_start = None
                return res
            return self.status
        return "NORMAL"
