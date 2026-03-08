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
# V6.4 最终版：战神 (War-Ender / Final Eagle)
# ============================================================

class GridMTFStrategyV6_4(BaseStrategy):
    """
    V6.4-WarEnder 战神版
    终极进化逻辑：
    1. 趋势动量加成：MACD 强劲时显著放大单笔买入权重。
    2. 全局高位止损保护 (Global Drawdown Shield)：若资产从历史峰值跌超 15%，触发深度静默（30天）。
    3. RSI 分步止盈：RSI > 75 卖出 50%，RSI > 85 全卖。
    4. 集成 V6.1 动态 ATR。
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
        
        # 6.4 核心状态
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

        # 增量指标
        rsi, atr, atr_ma = self.indicators.update_5m(data, commit=False)
        macd, sig, hist = self.indicators.update_15m_macd(data.close, commit=False)
        
        self.state.current_rsi = rsi
        self.state.atr = atr
        self.state.atr_ma = atr_ma
        self.state.macd = macd
        self.state.macdsignal = sig
        self.state.macdhist = hist
        
        # 1. 检测全局深度静默
        if self.shutdown_until and data.timestamp < self.shutdown_until:
            return []
        elif self.shutdown_until:
            self.shutdown_until = None # 恢复

        # 2. 检测常规熔断
        if self._check_halt(data): return []
        
        # 3. 网格维护
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
        
        # 维护峰值资产 (High-Water Mark)
        if total_val > self.peak_equity:
            self.peak_equity = total_val
            
        mdd_from_peak = (self.peak_equity - total_val) / self.peak_equity if self.peak_equity > 0 else 0
        
        # 核心进化：全局大风险盾牌 (Global Shield)
        # 当 MDD > 15% 时，说明市场进入单边急跌或逻辑完全失效，深度静默
        if mdd_from_peak > 0.15:
            self.shutdown_until = data.timestamp + timedelta(days=30)
            if pos_size > 0:
                # 立即清仓保命
                signals.append(Signal(data.timestamp, self.symbol, Side.SELL, pos_size, reason="Global DD Shield (Emergency Exit)"))
            return signals

        is_bullish = self.state.macdhist > 0
        self.state.macdhist_prev = getattr(self.state, 'macdhist_prev', self.state.macdhist)
        hist_growth = self.state.macdhist - self.state.macdhist_prev
        self.state.macdhist_prev = self.state.macdhist

        # 1. 卖出逻辑 (RSI 分步止盈)
        if pos_size > 0:
            if self.state.current_rsi > 85: # 极度过热，全部止盈
                signals.append(Signal(data.timestamp, self.symbol, Side.SELL, pos_size, reason="Overheat TP (85)"))
            elif self.state.current_rsi > 75: # 过热，止盈一半
                # 至少保留基础持仓以便捕捉后续涨幅
                signals.append(Signal(data.timestamp, self.symbol, Side.SELL, pos_size * 0.5, reason="Overheat TP (75)"))

        # 2. 买入逻辑 (动量加成网格)
        if not signals and is_bullish:
            if self.state.current_rsi < self.params.get('rsi_buy_threshold', 30):
                idx = -1
                for i in range(len(self.state.grid_lines) - 1):
                    if self.state.grid_lines[i] <= data.close < self.state.grid_lines[i+1]:
                        idx = i; break
                
                if idx != -1 and idx < 2:
                    # 动态系数：波动率缩减 + 动量加成
                    vol_factor = np.clip(self.state.atr_ma / (self.state.atr + 1e-9), 0.6, 1.2)
                    # 动量加成：MACD 柱状图越大，说明趋势越强，买得更多
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
        from strategies.grid_mtf_6_0 import GridMTFStrategyV6_0
        res = GridMTFStrategyV6_0.get_status(self, context)
        res['is_shutdown'] = self.shutdown_until is not None
        res['mdd_from_peak'] = round((self.peak_equity - (context.total_value if context else 0)) / (self.peak_equity or 1), 4)
        return res
