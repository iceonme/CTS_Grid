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
from cartridges.strategies.grid_mtf_6_0 import IncrementalIndicatorsV6, StrategyState

# ============================================================
# V6.4 鏈€缁堢増锛氭垬绁?(War-Ender / Final Eagle)
# ============================================================

class GridMTFStrategyV6_4(BaseStrategy):
    """
    V6.4-WarEnder 鎴樼鐗?
    缁堟瀬杩涘寲閫昏緫锛?
    1. 瓒嬪娍鍔ㄩ噺鍔犳垚锛歁ACD 寮哄姴鏃舵樉钁楁斁澶у崟绗斾拱鍏ユ潈閲嶃€?
    2. 鍏ㄥ眬楂樹綅姝㈡崯淇濇姢 (Global Drawdown Shield)锛氳嫢璧勪骇浠庡巻鍙插嘲鍊艰穼瓒?15%锛岃Е鍙戞繁搴﹂潤榛橈紙30澶╋級銆?
    3. RSI 鍒嗘姝㈢泩锛歊SI > 75 鍗栧嚭 50%锛孯SI > 85 鍏ㄥ崠銆?
    4. 闆嗘垚 V6.1 鍔ㄦ€?ATR銆?
    """
    def __init__(self, name: str = "Grid_V64_WarEnder", **params):
        super().__init__(name, **params)
        
        current_file_dir = Path(__file__).parent.resolve()
        config_dir = current_file_dir.parent / "config"
        
        self.default_params_path = str(config_dir / 'grid_v60_default.json')
        self.params_path = str(config_dir / 'grid_v64_runtime.json')
        
        self.symbol = params.get('symbol', 'BTCUSDT')
        self._load_params()

        self._data_5m = deque(maxlen=500) 
        self._last_5m_ts = None
        self._last_bar_5m = None
        
        self.state = StrategyState()
        self.indicators = IncrementalIndicatorsV6(self.params)
        
        # 6.4 鏍稿績鐘舵€?
        self.peak_equity = 0.0
        self.shutdown_until = None
        self._last_15m_ts: Optional[datetime] = None
        self._last_15m_bar_close = 0.0

    def _load_params(self):
        if os.path.exists(self.default_params_path):
            with open(self.default_params_path, 'r', encoding='utf-8') as f:
                self.params.update(json.load(f))
        if os.path.exists(self.params_path):
            with open(self.params_path, 'r', encoding='utf-8') as f:
                self.params.update(json.load(f))

    def on_data(self, data: MarketData, context: Optional[StrategyContext]) -> List[Signal]:
        is_new_bar = (not self._last_5m_ts) or (data.timestamp > self._last_5m_ts)
        if is_new_bar:
            if self._last_bar_5m:
                self.indicators.update_5m(self._last_bar_5m, commit=True)
            self._last_5m_ts = data.timestamp
            ts = data.timestamp
            period_ts = ts.replace(minute=(ts.minute // 15) * 15, second=0, microsecond=0)
            if self._last_15m_ts is None or period_ts > self._last_15m_ts:
                if self._last_15m_ts is not None:
                    self.indicators.update_15m_macd(self._last_15m_bar_close, commit=True)
                self._last_15m_ts = period_ts
                self._last_15m_bar_close = data.close
            else:
                self._last_15m_bar_close = data.close
        self._last_bar_5m = data

        if len(self._data_5m) < 40: 
            self._data_5m.append(data)
            return []
        self._data_5m.append(data)

        # 澧為噺鎸囨爣
        rsi, atr, atr_ma = self.indicators.update_5m(data, commit=False)
        macd, sig, hist = self.indicators.update_15m_macd(data.close, commit=False)
        
        self.state.current_rsi = rsi
        self.state.atr = atr
        self.state.atr_ma = atr_ma
        self.state.macd = macd
        self.state.macdsignal = sig
        self.state.macdhist = hist
        
        # 1. 妫€娴嬪叏灞€娣卞害闈欓粯
        if self.shutdown_until and data.timestamp < self.shutdown_until:
            return []
        elif self.shutdown_until:
            self.shutdown_until = None # 鎭㈠

        # 2. 妫€娴嬪父瑙勭啍鏂?
        if self._check_halt(data): return []
        
        # 3. 缃戞牸缁存姢
        self._manage_grid(data)

        if context:
            return self._generate_signals(data, context)
        return []

    def _manage_grid(self, data: MarketData):
        now = data.timestamp
        lookback = self.params.get('grid_lookback_hours', 6)
        need_reset = False
        if self.state.grid_upper == 0:
            need_reset = True
        elif self.state.last_grid_reset and (now - self.state.last_grid_reset) > timedelta(hours=lookback):
            need_reset = True
        elif abs(data.close - (self.state.grid_upper + self.state.grid_lower)/2) / ((self.state.grid_upper + self.state.grid_lower)/2) > self.params.get('grid_readjust', 0.05):
            need_reset = True

        if need_reset:
            bars = list(self._data_5m)[-int(lookback * 12):]
            if not bars: return
            high = max(b.high for b in bars)
            low = min(b.low for b in bars)
            buffer = self.params.get('grid_buffer', 0.02)
            self.state.grid_upper = high * (1 + buffer)
            self.state.grid_lower = low * (1 - buffer)
            layers = self.params.get('grid_layers', 5)
            self.state.grid_lines = np.linspace(self.state.grid_lower, self.state.grid_upper, layers + 1).tolist()
            self.state.last_grid_reset = now

    def _check_halt(self, data: MarketData) -> bool:
        if self.state.is_halted:
            if self.state.resume_time and data.timestamp >= self.state.resume_time:
                self.state.is_halted = False
            else: return True
        if self.state.atr > self.state.atr_ma * self.params.get('atr_blackswan_mult', 3.0):
            self.state.is_halted = True
            self.state.resume_time = data.timestamp + timedelta(minutes=self.params.get('atr_cooldown_min', 30))
            return True
        return False

    def _generate_signals(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        signals = []
        pos = context.positions.get(self.symbol)
        pos_size = pos.size if pos else 0
        total_val = context.cash + pos_size * data.close
        
        # 缁存姢宄板€艰祫浜?(High-Water Mark)
        if total_val > self.peak_equity:
            self.peak_equity = total_val
            
        mdd_from_peak = (self.peak_equity - total_val) / self.peak_equity if self.peak_equity > 0 else 0
        
        # 鏍稿績杩涘寲锛氬叏灞€澶ч闄╃浘鐗?(Global Shield)
        # 褰?MDD > 15% 鏃讹紝璇存槑甯傚満杩涘叆鍗曡竟鎬ヨ穼鎴栭€昏緫瀹屽叏澶辨晥锛屾繁搴﹂潤榛?
        if mdd_from_peak > 0.15:
            self.shutdown_until = data.timestamp + timedelta(days=30)
            if pos_size > 0:
                # 绔嬪嵆娓呬粨淇濆懡
                signals.append(Signal(data.timestamp, self.symbol, Side.SELL, pos_size, reason="Global DD Shield (Emergency Exit)"))
            return signals

        is_bullish = self.state.macdhist > 0
        self.state.macdhist_prev = getattr(self.state, 'macdhist_prev', self.state.macdhist)
        hist_growth = self.state.macdhist - self.state.macdhist_prev
        self.state.macdhist_prev = self.state.macdhist

        # 1. 鍗栧嚭閫昏緫 (RSI 鍒嗘姝㈢泩)
        if pos_size > 0:
            if self.state.current_rsi > 85: # 鏋佸害杩囩儹锛屽叏閮ㄦ鐩?
                signals.append(Signal(data.timestamp, self.symbol, Side.SELL, pos_size, reason="Overheat TP (85)"))
            elif self.state.current_rsi > 75: # 杩囩儹锛屾鐩堜竴鍗?
                # 鑷冲皯淇濈暀鍩虹鎸佷粨浠ヤ究鎹曟崏鍚庣画娑ㄥ箙
                signals.append(Signal(data.timestamp, self.symbol, Side.SELL, pos_size * 0.5, reason="Overheat TP (75)"))

        # 2. 涔板叆閫昏緫 (鍔ㄩ噺鍔犳垚缃戞牸)
        if not signals and is_bullish:
            if self.state.current_rsi < self.params.get('rsi_buy_threshold', 30):
                idx = -1
                for i in range(len(self.state.grid_lines) - 1):
                    if self.state.grid_lines[i] <= data.close < self.state.grid_lines[i+1]:
                        idx = i; break
                
                if idx != -1 and idx < 2:
                    # 鍔ㄦ€佺郴鏁帮細娉㈠姩鐜囩缉鍑?+ 鍔ㄩ噺鍔犳垚
                    vol_factor = np.clip(self.state.atr_ma / (self.state.atr + 1e-9), 0.6, 1.2)
                    # 鍔ㄩ噺鍔犳垚锛歁ACD 鏌辩姸鍥捐秺澶э紝璇存槑瓒嬪娍瓒婂己锛屼拱寰楁洿澶?
                    momentum_factor = np.clip(1.0 + (self.state.macdhist * 10), 1.0, 1.5)
                    
                    layers = self.params.get('grid_layers', 5)
                    weight = (layers - idx) / sum(range(1, layers + 1))
                    buy_usdt = self.params.get('total_capital', 10000) * weight * vol_factor * momentum_factor
                    
                    if context.cash >= buy_usdt:
                        signals.append(Signal(
                            timestamp=data.timestamp,
                            symbol=self.symbol,
                            side=Side.BUY,
                            size=buy_usdt,
                            meta={'size_in_quote': True},
                            reason=f"WarEnder Buy: VolF={vol_factor:.1f} MomF={momentum_factor:.1f}"
                        ))

        return signals

    def get_status(self, context=None):
        from cartridges.strategies.grid_mtf_6_0 import GridMTFStrategyV6_0
        res = GridMTFStrategyV6_0.get_status(self, context)
        res['is_shutdown'] = self.shutdown_until is not None
        res['mdd_from_peak'] = round((self.peak_equity - (context.total_value if context else 0)) / (self.peak_equity or 1), 4)
        return res
