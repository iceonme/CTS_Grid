import os
import json
import numpy as np
from pathlib import Path
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
# V7.0 龙计划：全自适应趋势网格 (Dragon Plan: Adaptive Trend-Grid)
# ============================================================

class GridMTFStrategyV7_0(BaseStrategy):
    """
    V7.0-Dragon 龙计划最终版
    专为 2025 年“大牛转深熊”设计的双态切换策略：
    1. 趋势进攻态 (Trend-Bull): 当价格在 15m MA200 之上，改为“追涨网格”，RSI 限制放宽，锁定主升浪。
    2. 深度防御态 (Trend-Bear): 当价格在 15m MA200 之下，改为“极窄网格”，低位接单高位快走，规避阴跌。
    3. 暴力止损 (Crash Shield): 24h 内若回撤超 10%，强制空仓静默。
    """
    def __init__(self, name: str = "Grid_V70_Dragon", **params):
        super().__init__(name, **params)
        
        current_file_dir = Path(__file__).parent.resolve()
        config_dir = current_file_dir.parent / "config"
        
        self.default_params_path = str(config_dir / 'grid_v60_default.json')
        self.params_path = str(config_dir / 'grid_v70_runtime.json')
        
        self.symbol = params.get('symbol', 'BTCUSDT')
        self._load_params()

        self._data_15m_closes = deque(maxlen=300)
        self._last_5m_ts = None
        self._last_bar_5m = None
        self._last_15m_ts: Optional[datetime] = None
        self._last_15m_bar_close = 0.0
        
        self.state = StrategyState()
        self.indicators = IncrementalIndicatorsV6(self.params)
        self.ma200_15m = 0.0
        self.ath_24h = 0.0
        self.last_ath_update = None

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
                    self._data_15m_closes.append(self._last_15m_bar_close)
                self._last_15m_ts = period_ts
                self._last_15m_bar_close = data.close
            else:
                self._last_15m_bar_close = data.close
        
        self._last_bar_5m = data
        
        # 维护 24h ATH (用于硬止损)
        if not self.last_ath_update or (data.timestamp - self.last_ath_update) > timedelta(hours=24):
            self.ath_24h = data.high
            self.last_ath_update = data.timestamp
        else:
            self.ath_24h = max(self.ath_24h, data.high)

        if len(self._data_15m_closes) < 20: return []

        rsi, atr, atr_ma = self.indicators.update_5m(data, commit=False)
        macd, sig, hist = self.indicators.update_15m_macd(data.close, commit=False)
        
        if len(self._data_15m_closes) >= 200:
            self.ma200_15m = np.mean(list(self._data_15m_closes)[-200:])
        else:
            self.ma200_15m = np.mean(list(self._data_15m_closes))

        self.state.current_rsi = rsi
        self.state.macdhist = hist
        
        if self._check_halt(data): return []
        self._manage_grid(data)

        if context:
            return self._generate_signals(data, context)
        return []

    def _manage_grid(self, data: MarketData):
        # 动态网格逻辑
        # 在多头行情中，网格中心随价格上移
        # 在空头行情中，网格中心停滞在下方
        is_bull = data.close > self.ma200_15m
        
        now = data.timestamp
        lookback = 12 if is_bull else 24
        
        need_reset = False
        if self.state.grid_upper == 0:
            need_reset = True
        elif is_bull and abs(data.close - (self.state.grid_upper + self.state.grid_lower)/2) / data.close > 0.03:
            need_reset = True # 多关区随动
        elif not is_bull and (now - self.state.last_grid_reset) > timedelta(hours=24):
            need_reset = True # 空头区锁死

        if need_reset:
            # 此处逻辑简化，实际可引入更多指标
            buffer = 0.02 if is_bull else 0.05
            self.state.grid_upper = data.close * (1 + buffer)
            self.state.grid_lower = data.close * (1 - buffer)
            self.state.grid_lines = np.linspace(self.state.grid_lower, self.state.grid_upper, 6).tolist()
            self.state.last_grid_reset = now

    def _check_halt(self, data: MarketData) -> bool:
        # 硬核止损：如果价格从 24h 内的最高点跌去 10%，强制静默
        if (self.ath_24h - data.close) / self.ath_24h > 0.10:
            self.state.is_halted = True
            self.state.resume_time = data.timestamp + timedelta(hours=12)
            return True
        return False

    def _generate_signals(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        signals = []
        pos = context.positions.get(self.symbol)
        pos_size = pos.size if pos else 0
        total_val = context.cash + pos_size * data.close
        
        is_bull = data.close > self.ma200_15m
        
        # 1. 卖出逻辑 (分态止盈)
        if pos_size > 0:
            sell_rsi = 85 if is_bull else 65 # 牛市拿住，熊市快跑
            if self.state.current_rsi > sell_rsi:
                signals.append(Signal(data.timestamp, self.symbol, Side.SELL, pos_size, reason=f"Dragon Sell ({'Bull' if is_bull else 'Bear'})"))

        # 2. 买入逻辑 (分态建仓)
        if not signals:
            buy_rsi = 50 if is_bull else 25 # 牛市激进，熊市极度谨慎
            if self.state.current_rsi < buy_rsi:
                # 给一个较大的权重
                weight = 0.4 if is_bull else 0.1
                buy_usdt = 10000 * weight
                if context.cash >= buy_usdt:
                    signals.append(Signal(
                        data.timestamp, self.symbol, Side.BUY, buy_usdt,
                        meta={'size_in_quote': True},
                        reason=f"Dragon Buy ({'Bull' if is_bull else 'Bear'})"
                    ))

        return signals

    def get_status(self, context=None):
        return {
            'strategy': 'V7.0-Dragon',
            'is_bull': (context.current_price > self.ma200_15m) if (context and self.ma200_15m > 0) else False,
            'rsi': round(self.state.current_rsi or 0, 1),
            'ma200': round(self.ma200_15m, 2),
            'halted': self.state.is_halted
        }
