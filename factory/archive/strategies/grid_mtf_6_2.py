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
# V6.2 杩涘寲鐗堬細瓒嬪娍璺熼殢澧炲己鐗?(Trend-Follower / Grid Hybrid)
# ============================================================

class GridMTFStrategyV6_2(BaseStrategy):
    """
    V6.2-Hybrid 瓒嬪娍/缃戞牸娣峰悎鐗?
    鏍稿績杩涘寲锛?
    1. 瓒嬪娍鎸佷粨閿佸畾锛氬湪寮虹墰甯備腑淇濈暀鈥滄牳蹇冧粨浣嶁€濓紝涓嶆寜缃戞牸鍏ㄥ崠銆?
    2. 娉㈠姩鑷€傚簲缃戞牸娣卞害锛氭牴鎹?ATR 鍔ㄦ€佹媺浼哥綉鏍间笂涓嬬晫锛岄伩鍏嶅崟杈硅鎯呰繃鏃╃┛浠撱€?
    """
    def __init__(self, name: str = "Grid_V62_Hybrid", **params):
        super().__init__(name, **params)
        
        current_file_dir = Path(__file__).parent.resolve()
        config_dir = current_file_dir.parent / "config"
        
        self.default_params_path = str(config_dir / 'grid_v60_default.json')
        self.params_path = str(config_dir / 'grid_v62_runtime.json')
        self.meta_path = str(config_dir / 'grid_v60_meta.json')
        
        self.symbol = params.get('symbol', 'BTCUSDT')
        self._load_params()

        # 鏁版嵁缂撳瓨
        self._data_5m = deque(maxlen=400) 
        self._data_15m = deque(maxlen=100)
        self._last_15m_ts: Optional[datetime] = None

        self.state = StrategyState()
        self.indicators = IncrementalIndicatorsV6(self.params)
        self._last_5m_ts = None
        self._last_bar_5m = None
        self._last_15m_bar_close = 0.0
        
        # 鏍稿績浠撲綅绠＄悊
        self.core_pos_ratio = 0.0 # 0.0 - 0.5

    def _load_params(self):
        if os.path.exists(self.default_params_path):
            with open(self.default_params_path, 'r', encoding='utf-8') as f:
                self.params.update(json.load(f))
        if os.path.exists(self.params_path):
            with open(self.params_path, 'r', encoding='utf-8') as f:
                self.params.update(json.load(f))

    def initialize(self):
        super().initialize()
        self.state = StrategyState()
        self.indicators = IncrementalIndicatorsV6(self.params)
        self._last_5m_ts = None
        self._last_bar_5m = None
        self._data_5m.clear()
        self._data_15m.clear()
        self._last_15m_ts = None

    def on_data(self, data: MarketData, context: Optional[StrategyContext]) -> List[Signal]:
        is_new_bar = (not self._last_5m_ts) or (data.timestamp > self._last_5m_ts)
        if is_new_bar:
            if self._last_bar_5m:
                self.indicators.update_5m(self._last_bar_5m, commit=True)
            self._last_5m_ts = data.timestamp
            self._update_data(data)
        self._last_bar_5m = data

        if len(self._data_5m) < 30: return []

        rsi, atr, atr_ma = self.indicators.update_5m(data, commit=False)
        macd, sig, hist = self.indicators.update_15m_macd(data.close, commit=False)
        
        self.state.current_rsi = rsi
        self.state.atr = atr
        self.state.atr_ma = atr_ma
        self.state.macd = macd
        self.state.macdsignal = sig
        self.state.macdhist = hist
        
        if self._check_halt(data): return []
        self._manage_grid(data)

        if context:
            return self._generate_signals(data, context)
        return []

    def _update_data(self, data: MarketData):
        self._data_5m.append(data)
        ts = data.timestamp
        period_ts = ts.replace(minute=(ts.minute // 15) * 15, second=0, microsecond=0)
        
        if self._last_15m_ts is None or period_ts > self._last_15m_ts:
            if self._last_15m_ts is not None:
                self.indicators.update_15m_macd(self._last_15m_bar_close, commit=True)
            self._last_15m_ts = period_ts
            self._last_15m_bar_close = data.close
            self._data_15m.append({'timestamp': period_ts, 'close': data.close})
        else:
            self._last_15m_bar_close = data.close

    def _manage_grid(self, data: MarketData):
        now = data.timestamp
        lookback = self.params.get('grid_lookback_hours', 6)
        
        # 鏍稿績杩涘寲锛氭牴鎹?ATR 璋冩暣 Buffer 娣卞害
        # 娉㈠姩澶ф椂缃戞牸鍔犳繁锛堥槻绌匡級锛屾尝鍔ㄥ皬鏃剁綉鏍兼敹绐勶紙澧為锛?
        vol_scale = 1.0
        if self.state.atr_ma > 0:
            vol_scale = np.clip(self.state.atr / (self.state.atr_ma + 1e-9), 0.8, 1.5)
        
        base_buffer = self.params.get('grid_buffer', 0.02)
        dynamic_buffer = base_buffer * vol_scale

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
            
            self.state.grid_upper = high * (1 + dynamic_buffer)
            self.state.grid_lower = low * (1 - dynamic_buffer)
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
        
        is_bullish = self.state.macdhist > 0
        self.state.macdhist_prev = getattr(self.state, 'macdhist_prev', self.state.macdhist)
        hist_growth = self.state.macdhist - self.state.macdhist_prev
        self.state.macdhist_prev = self.state.macdhist

        # 1. 鏍稿績杩涘寲锛氬湪鐗涘競涓缓绔嬫牳蹇冩寔浠?(Core Position)
        # 鎻愰珮鏁翠綋鎸佷粨搴曢檺锛岀‘淇濆崟杈逛笂娑ㄦ椂涓嶈笍绌?
        if is_bullish and hist_growth > 0:
            self.core_pos_ratio = 0.3 # 閿佸畾 30% 鎬昏祫閲戜綔涓哄簳浠撲粨浣?
        else:
            self.core_pos_ratio = 0.0 # 闇囪崱鎴栧急鍔夸笉鐣欏簳浠?

        # 1. 鍗栧嚭閫昏緫
        if pos_size > 0:
            # 鍙湁褰撴寔浠撹秴杩団€滄牳蹇冧粨浣嶁€濇椂锛屾墠鍏佽缃戞牸鍗栧嚭
            total_cap = self.params.get('total_capital', 10000)
            core_size = (total_cap * self.core_pos_ratio) / data.close
            
            if pos_size > core_size:
                sell_threshold = self.params.get('rsi_sell_threshold', 70)
                if self.state.current_rsi > sell_threshold:
                    if data.close >= self.state.grid_lines[-2]:
                        # 浠呭崠鍑鸿秴鍑烘牳蹇冧粨浣嶇殑閮ㄥ垎
                        sell_size = pos_size - core_size
                        if sell_size > 0:
                            signals.append(Signal(
                                timestamp=data.timestamp,
                                symbol=self.symbol,
                                side=Side.SELL,
                                size=sell_size,
                                reason=f"V6.2 Hybrid Sell: RSI={self.state.current_rsi:.1f} (Keep Core)"
                            ))

        # 2. 涔板叆閫昏緫
        if not signals:
            if is_bullish and self.state.current_rsi < self.params.get('rsi_buy_threshold', 28):
                idx = -1
                for i in range(len(self.state.grid_lines) - 1):
                    if self.state.grid_lines[i] <= data.close < self.state.grid_lines[i+1]:
                        idx = i; break
                
                if idx != -1 and idx < 3: # V6.2 鍏佽鍦ㄥ簳閮ㄧ殑涓夊眰涔板叆
                    layers = self.params.get('grid_layers', 5)
                    weight = (layers - idx) / sum(range(1, layers + 1))
                    buy_usdt = self.params.get('total_capital', 10000) * weight
                    
                    if context.cash >= buy_usdt:
                        signals.append(Signal(
                            timestamp=data.timestamp,
                            symbol=self.symbol,
                            side=Side.BUY,
                            size=buy_usdt,
                            meta={'size_in_quote': True},
                            reason=f"V6.2 Hybrid Buy: Layer={idx}"
                        ))

        return signals

    def get_status(self, context=None):
        # 澶嶇敤 6.0 鐨勬樉绀洪€昏緫
        from cartridges.strategies.grid_mtf_6_0 import GridMTFStrategyV6_0
        return GridMTFStrategyV6_0.get_status(self, context)
