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
from strategies.grid_mtf_6_0 import IncrementalIndicatorsV6, StrategyState

# ============================================================
# V6.2 进化版：趋势跟随增强版 (Trend-Follower / Grid Hybrid)
# ============================================================

class GridMTFStrategyV6_2(BaseStrategy):
    """
    V6.2-Hybrid 趋势/网格混合版
    核心进化：
    1. 趋势持仓锁定：在强牛市中保留“核心仓位”，不按网格全卖。
    2. 波动自适应网格深度：根据 ATR 动态拉伸网格上下界，避免单边行情过早穿仓。
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

        # 数据缓存
        self._data_5m = deque(maxlen=400) 
        self._data_15m = deque(maxlen=100)
        self._last_15m_ts: Optional[datetime] = None

        self.state = StrategyState()
        self.indicators = IncrementalIndicatorsV6(self.params)
        self._last_5m_ts = None
        self._last_bar_5m = None
        self._last_15m_bar_close = 0.0
        
        # 核心仓位管理
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
        
        # 核心进化：根据 ATR 调整 Buffer 深度
        # 波动大时网格加深（防穿），波动小时网格收窄（增频）
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

        # 1. 核心进化：在牛市中建立核心持仓 (Core Position)
        # 提高整体持仓底限，确保单边上涨时不踏空
        if is_bullish and hist_growth > 0:
            self.core_pos_ratio = 0.3 # 锁定 30% 总资金作为底仓仓位
        else:
            self.core_pos_ratio = 0.0 # 震荡或弱势不留底仓

        # 1. 卖出逻辑
        if pos_size > 0:
            # 只有当持仓超过“核心仓位”时，才允许网格卖出
            total_cap = self.params.get('total_capital', 10000)
            core_size = (total_cap * self.core_pos_ratio) / data.close
            
            if pos_size > core_size:
                sell_threshold = self.params.get('rsi_sell_threshold', 70)
                if self.state.current_rsi > sell_threshold:
                    if data.close >= self.state.grid_lines[-2]:
                        # 仅卖出超出核心仓位的部分
                        sell_size = pos_size - core_size
                        if sell_size > 0:
                            signals.append(Signal(
                                timestamp=data.timestamp,
                                symbol=self.symbol,
                                side=Side.SELL,
                                size=sell_size,
                                reason=f"V6.2 Hybrid Sell: RSI={self.state.current_rsi:.1f} (Keep Core)"
                            ))

        # 2. 买入逻辑
        if not signals:
            if is_bullish and self.state.current_rsi < self.params.get('rsi_buy_threshold', 28):
                idx = -1
                for i in range(len(self.state.grid_lines) - 1):
                    if self.state.grid_lines[i] <= data.close < self.state.grid_lines[i+1]:
                        idx = i; break
                
                if idx != -1 and idx < 3: # V6.2 允许在底部的三层买入
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
        # 复用 6.0 的显示逻辑
        from strategies.grid_mtf_6_0 import GridMTFStrategyV6_0
        return GridMTFStrategyV6_0.get_status(self, context)
