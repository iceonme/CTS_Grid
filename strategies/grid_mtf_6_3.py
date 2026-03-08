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
# V6.3 究极进化版：高点利润锁定 (Eagle Peak Lock)
# ============================================================

class GridMTFStrategyV6_3(BaseStrategy):
    """
    V6.3-Eagle 猎鹰版
    核心进化：
    1. 趋势追踪止盈 (Trailing TP)：在 15m MACD 强多头后出现衰竭信号时，大比例套现。
    2. 回撤自适应入场 (Drawdown Barrier)：在急跌后的震荡期才开启网格，避免阴跌期过度消耗资金。
    3. 集成 6.1 的动态仓位逻辑。
    """
    def __init__(self, name: str = "Grid_V63_Eagle", **params):
        super().__init__(name, **params)
        
        current_file_dir = Path(__file__).parent.resolve()
        config_dir = current_file_dir.parent / "config"
        
        self.default_params_path = str(config_dir / 'grid_v60_default.json')
        self.params_path = str(config_dir / 'grid_v63_runtime.json')
        
        self.symbol = params.get('symbol', 'BTCUSDT')
        self._load_params()

        self._data_5m = deque(maxlen=400) 
        self._last_5m_ts = None
        self._last_bar_5m = None
        
        self.state = StrategyState()
        self.indicators = IncrementalIndicatorsV6(self.params)
        
        # 6.3 特有状态
        self.peak_equity = 0.0
        self.lock_trigger_price = 0.0
        self.is_locking = False
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
            # 15m 聚合同步
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

        if len(list(self._data_5m)) < 10: 
            self._data_5m.append(data)
            return []
        self._data_5m.append(data)

        rsi, atr, atr_ma = self.indicators.update_5m(data, commit=False)
        macd, sig, hist = self.indicators.update_15m_macd(data.close, commit=False)
        
        self.state.current_rsi = rsi
        self.state.atr = atr
        self.state.atr_ma = atr_ma
        self.state.macd = macd
        self.state.macdsignal = sig
        self.state.macdhist = hist
        
        # 检测熔断
        if self._check_halt(data): return []
        
        # 网格维护
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
        
        # 更新峰值资产
        if total_val > self.peak_equity:
            self.peak_equity = total_val
            
        is_bullish = self.state.macdhist > 0
        self.state.macdhist_prev = getattr(self.state, 'macdhist_prev', self.state.macdhist)
        hist_growth = self.state.macdhist - self.state.macdhist_prev
        self.state.macdhist_prev = self.state.macdhist

        # 核心进化：高点保护逻辑
        # 如果当前资产从峰值回撤超过 5%，且 MACD 柱状图在走弱，则视为“冲高回落”，进入防御锁定状态。
        mdd_from_peak = (self.peak_equity - total_val) / self.peak_equity if self.peak_equity > 0 else 0
        if mdd_from_peak > 0.05 and not is_bullish:
            # 在这种状态下，我们要大比例卖出，直到趋势重新站稳
            self.is_locking = True
        elif is_bullish and hist_growth > 0:
            self.is_locking = False # 重新站稳，恢复

        # 1. 卖出逻辑
        if pos_size > 0:
            # 卖点 1: 正常网格卖出
            sell_threshold = self.params.get('rsi_sell_threshold', 70)
            if self.state.current_rsi > sell_threshold and data.close >= self.state.grid_lines[-2]:
                signals.append(Signal(data.timestamp, self.symbol, Side.SELL, pos_size, reason="Grid TP"))
            
            # 卖点 2: 猎鹰止盈 (锁定高位利润)
            if not signals and self.is_locking:
                # 只有当持仓相对于总价值超过一定比例时才“大砍”，防止每分钟产生微小卖单
                if pos_size * data.close > total_val * 0.1:
                    signals.append(Signal(data.timestamp, self.symbol, Side.SELL, pos_size * 0.9, reason="Eagle Peak Lock"))

        # 2. 买入逻辑
        if not signals:
            # 只有在非锁定状态下，且 MACD 强多头，才允许网格买入
            if not self.is_locking and is_bullish and self.state.current_rsi < self.params.get('rsi_buy_threshold', 28):
                idx = -1
                for i in range(len(self.state.grid_lines) - 1):
                    if self.state.grid_lines[i] <= data.close < self.state.grid_lines[i+1]:
                        idx = i; break
                
                if idx != -1 and idx < 2:
                    # 集成 6.1 的动态仓位
                    vol_factor = np.clip(self.state.atr_ma / (self.state.atr + 1e-9), 0.5, 1.2)
                    layers = self.params.get('grid_layers', 5)
                    weight = (layers - idx) / sum(range(1, layers + 1))
                    buy_usdt = self.params.get('total_capital', 10000) * weight * vol_factor
                    
                    if context.cash >= buy_usdt:
                        signals.append(Signal(
                            timestamp=data.timestamp,
                            symbol=self.symbol,
                            side=Side.BUY,
                            size=buy_usdt,
                            meta={'size_in_quote': True},
                            reason=f"Eagle Buy: VolF={vol_factor:.2f}"
                        ))

        return signals

    def get_status(self, context=None):
        from strategies.grid_mtf_6_0 import GridMTFStrategyV6_0
        res = GridMTFStrategyV6_0.get_status(self, context)
        res['eagle_locking'] = self.is_locking
        res['peak_equity'] = round(self.peak_equity, 2)
        return res
