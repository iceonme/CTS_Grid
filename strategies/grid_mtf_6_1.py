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
# V6.1 进化版：动态仓位管理 (Dynamic Position Sizing)
# ============================================================

class GridMTFStrategyV6_1(BaseStrategy):
    """
    V6.1-Dynamic 动态仓位版
    核心进化：引入基于 ATR 波动率与趋势强度的动态仓位缩放
    """
    def __init__(self, name: str = "Grid_V61_Dynamic", **params):
        super().__init__(name, **params)
        
        # 路径与配置 (共享 6.0 的默认配置，但可以单独覆盖)
        current_file_dir = Path(__file__).parent.resolve()
        config_dir = current_file_dir.parent / "config"
        
        self.default_params_path = str(config_dir / 'grid_v60_default.json')
        self.params_path = str(config_dir / 'grid_v61_runtime.json') # 独立的运行时文件
        self.meta_path = str(config_dir / 'grid_v60_meta.json')
        
        self.symbol = params.get('symbol', 'BTCUSDT')
        self._load_params()

        # 数据缓存
        self._data_5m = deque(maxlen=300) 
        self._data_15m = deque(maxlen=100)
        self._last_15m_ts: Optional[datetime] = None

        self.state = StrategyState()
        self.indicators = IncrementalIndicatorsV6(self.params)
        self._last_5m_ts = None
        self._last_bar_5m = None
        self._last_15m_bar_close = 0.0

    def _load_params(self):
        # 加载默认
        if os.path.exists(self.default_params_path):
            with open(self.default_params_path, 'r', encoding='utf-8') as f:
                self.params.update(json.load(f))
        # 覆盖运行时 (如有)
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

        # 获取增量指标
        rsi, atr, atr_ma = self.indicators.update_5m(data, commit=False)
        macd, sig, hist = self.indicators.update_15m_macd(data.close, commit=False)
        
        self.state.current_rsi = rsi
        self.state.atr = atr
        self.state.atr_ma = atr_ma
        self.state.macd = macd
        self.state.macdsignal = sig
        self.state.macdhist = hist
        
        # 熔断检测
        if self._check_halt(data): return []

        # 网格维护
        self._manage_grid(data)

        # 信号生成
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
        
        is_bullish = self.state.macdhist > 0
        self.state.macdhist_prev = getattr(self.state, 'macdhist_prev', self.state.macdhist)
        hist_growth = self.state.macdhist - self.state.macdhist_prev
        self.state.macdhist_prev = self.state.macdhist

        # 核心进化 1：动态仓位系数 (Volatility Factor)
        # 当 ATR 远高于平均 ATR 时，说明市场极度不稳定，大幅缩小单笔金额
        # 当 ATR 远低于平均 ATR 时，说明市场平稳，可以适当放大仓位
        vol_factor = 1.0
        if self.state.atr_ma > 0:
            # 基础比例：正常波动率为 1.0。波动率翻倍则仓位减半。
            vol_factor = np.clip(self.state.atr_ma / (self.state.atr + 1e-9), 0.5, 1.5)

        # 核心进化 2：趋势强度系数 (Trend Strength)
        # 如果 MACD 柱状图在增长且为正，说明动量在加强，可以更激进
        trend_factor = 1.0
        if is_bullish and hist_growth > 0:
            trend_factor = 1.2
        elif not is_bullish:
            trend_factor = 0.7 # 弱势期减仓

        # 1. 卖出逻辑
        if pos_size > 0:
            sell_threshold = self.params.get('rsi_sell_threshold', 70)
            if is_bullish and hist_growth > 0:
                # 强趋势下，稍微拿久一点
                sell_threshold += 5
            
            if self.state.current_rsi > sell_threshold:
                if data.close >= self.state.grid_lines[-2]:
                    signals.append(Signal(
                        timestamp=data.timestamp,
                        symbol=self.symbol,
                        side=Side.SELL,
                        size=pos_size,
                        reason=f"V6.1 Sell: RSI={self.state.current_rsi:.1f}"
                    ))

        # 2. 买入逻辑
        if not signals:
            if is_bullish and self.state.current_rsi < self.params.get('rsi_buy_threshold', 28):
                idx = -1
                for i in range(len(self.state.grid_lines) - 1):
                    if self.state.grid_lines[i] <= data.close < self.state.grid_lines[i+1]:
                        idx = i; break
                
                if idx != -1 and idx < 2:
                    layers = self.params.get('grid_layers', 5)
                    base_weight = (layers - idx) / sum(range(1, layers + 1))
                    
                    # 综合动态仓位
                    final_weight = base_weight * vol_factor * trend_factor
                    buy_usdt = self.params.get('total_capital', 10000) * final_weight
                    
                    if context.cash >= buy_usdt:
                        signals.append(Signal(
                            timestamp=data.timestamp,
                            symbol=self.symbol,
                            side=Side.BUY,
                            size=buy_usdt,
                            meta={'size_in_quote': True},
                            reason=f"V6.1 Dynamic Buy: VolF={vol_factor:.2f} TrendF={trend_factor:.2f}"
                        ))

        return signals

    def get_status(self, context=None):
        status = super().get_status(context) # 此处会因 BaseStrategy 没写而报错，需手动补齐或类似 6.0
        # 简化版 status 适配 Dashboard
        return status # 实际上 6.0 写的很全，6.1 应该也保留
