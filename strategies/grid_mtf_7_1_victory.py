import os
import json
import numpy as np
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
# V7.1 终极版：极致性能泛化版 (Victory / Turbo Dynamic)
# ============================================================

class GridMTFStrategyV7_1(BaseStrategy):
    """
    V7.1-Victory 终极泛化速度优化版
    优化点：
    1. 增量滑动均线计算 (Incremental Moving Average)，彻底消除 O(N) 的 list 转换开销。
    2. 参数本地缓存，减少 dict.get 调用。
    3. 群集浮盈追踪 + 6倍 ATR 动态止损因子。
    """
    def __init__(self, name: str = "Grid_V71_Victory", **params):
        super().__init__(name, **params)
        
        current_file_dir = Path(__file__).parent.resolve()
        config_dir = current_file_dir.parent / "config"
        
        self.default_params_path = str(config_dir / 'grid_v60_default.json')
        self.params_path = str(config_dir / 'grid_v71_runtime.json')
        
        self.symbol = params.get('symbol', 'BTCUSDT')
        self._load_params()
        
        # 缓存热点参数，极速化循环
        self._p_rsi_buy = self.params.get('rsi_buy_threshold', 35)
        self._p_rsi_sell = self.params.get('rsi_sell_threshold', 75)
        self._p_atr_sl_mult = self.params.get('atr_sl_mult', 6.0)
        self._p_cooldown_hrs = self.params.get('grid_buy_cooldown', 2)
        self._p_capital = self.params.get('total_capital', 10000)

        # 15m 价格数据与均线缓存
        self._dq_15m = deque(maxlen=200)
        self._sum_50 = 0.0
        self._sum_200 = 0.0
        
        self.ma50_15m = 0.0
        self.ma200_15m = 0.0
        
        self._last_5m_ts = None
        self._last_bar_5m = None
        self._last_15m_ts: Optional[datetime] = None
        self._last_15m_bar_close = 0.0
        
        self.state = StrategyState()
        self.indicators = IncrementalIndicatorsV6(self.params)
        
        self.cluster_peak_price = 0.0
        self.has_active_cluster = False

    def _load_params(self):
        if os.path.exists(self.default_params_path):
            with open(self.default_params_path, 'r', encoding='utf-8') as f:
                self.params.update(json.load(f))
        if os.path.exists(self.params_path):
            with open(self.params_path, 'r', encoding='utf-8') as f:
                self.params.update(json.load(f))

    def on_data(self, data: MarketData, context: Optional[StrategyContext]) -> List[Signal]:
        # 1. 时间轴推进
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
                    # 增量维护均线
                    val = self._last_15m_bar_close
                    if len(self._dq_15m) == 200:
                        old_200 = self._dq_15m[0]
                        old_50 = self._dq_15m[150] # 200-50 = 150
                        self._sum_200 += (val - old_200)
                        self._sum_50 += (val - old_50)
                    else:
                        self._sum_200 += val
                        if len(self._dq_15m) >= 150: # 还没到200的时候，ma50也要算
                            pass # 简化起见，等待窗口填满前均线设为当前价
                        self._sum_50 = sum(list(self._dq_15m)[-49:]) + val if len(self._dq_15m) >= 49 else val*50
                    
                    self._dq_15m.append(val)
                    self.ma200_15m = self._sum_200 / len(self._dq_15m)
                    self.ma50_15m = self._sum_50 / 50 if len(self._dq_15m) >= 50 else val
                
                self._last_15m_ts = period_ts
                self._last_15m_bar_close = data.close
            else:
                self._last_15m_bar_close = data.close
        
        self._last_bar_5m = data

        if len(self._dq_15m) < 50: return []

        # 2. 获取实时增量指标
        rsi, atr, atr_ma = self.indicators.update_5m(data, commit=False)
        macd, sig, hist = self.indicators.update_15m_macd(data.close, commit=False)
        
        self.state.current_rsi = rsi
        self.state.atr = atr
        self.state.atr_ma = atr_ma
        self.state.macdhist = hist
        
        # 3. 熔断与网格管理
        if self.state.is_halted:
            if self.state.resume_time and data.timestamp >= self.state.resume_time:
                self.state.is_halted = False
            else: return []
            
        self._manage_grid(data)

        if context:
            return self._generate_signals(data, context)
        return []

    def _manage_grid(self, data: MarketData):
        now = data.timestamp
        if self.state.grid_upper == 0 or (now - getattr(self.state, 'last_grid_reset', now - timedelta(days=1))) > timedelta(hours=12):
            anchor = (data.close + self.ma50_15m) / 2
            buffer = self.params.get('grid_buffer', 0.03) * np.clip(self.state.atr / (self.state.atr_ma + 1e-9), 0.8, 1.5)
            self.state.grid_upper = anchor * (1 + buffer)
            self.state.grid_lower = anchor * (1 - buffer)
            self.state.grid_lines = np.linspace(self.state.grid_lower, self.state.grid_upper, self.params.get('grid_layers', 6) + 1).tolist()
            self.state.last_grid_reset = now

    def _generate_signals(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        signals = []
        pos = context.positions.get(self.symbol)
        pos_size = pos.size if pos else 0
        avg_price = pos.avg_price if pos else 0.0
        
        is_bull = data.close > self.ma200_15m
        is_strong_bull = is_bull and data.close > self.ma50_15m
        
        if pos_size > 0:
            if not self.has_active_cluster:
                self.has_active_cluster = True
                self.cluster_peak_price = data.close
            else:
                self.cluster_peak_price = max(self.cluster_peak_price, data.close)
        else:
            self.has_active_cluster = False; self.cluster_peak_price = 0.0

        # 1. 卖出逻辑
        if pos_size > 0:
            # (a) 追踪止盈
            if self.cluster_peak_price > avg_price * 1.08:
                if data.close < self.cluster_peak_price * 0.95:
                    signals.append(Signal(data.timestamp, self.symbol, Side.SELL, pos_size, reason="V7.1 Pure Trailing TP"))
            
            # (b) RSI 止盈 (带碎单过滤)
            elif not signals and self.state.current_rsi > self._p_rsi_sell:
                can_sell = not hasattr(self.state, 'sell_cooldown_ends') or data.timestamp >= self.state.sell_cooldown_ends
                if can_sell:
                    sell_ratio = 0.5 if is_strong_bull else 1.0
                    sell_size = pos_size * sell_ratio
                    if sell_size * data.close > 100 or sell_ratio == 1.0:
                        signals.append(Signal(data.timestamp, self.symbol, Side.SELL, sell_size, reason=f"V7.1 RSI TP: {sell_ratio*100}%"))
                        if sell_ratio < 1.0: self.state.sell_cooldown_ends = data.timestamp + timedelta(hours=1)
                
            # (c) ATR 动态止损
            elif not signals:
                atr_sl_price = avg_price - self.state.atr_ma * self._p_atr_sl_mult
                if data.close < atr_sl_price:
                    self.state.is_halted = True
                    self.state.resume_time = data.timestamp + timedelta(hours=12)
                    signals.append(Signal(data.timestamp, self.symbol, Side.SELL, pos_size, reason=f"V7.1 ATR SL"))

        # 2. 买入逻辑
        if not signals:
            if hasattr(self.state, 'cooldown_ends') and data.timestamp < self.state.cooldown_ends:
                return []
                
            is_downtrend = (self.ma50_15m < self.ma200_15m) and (data.close < self.ma200_15m)
            if not is_downtrend and self.state.current_rsi < self._p_rsi_buy:
                vol_factor = np.clip(self.state.atr_ma / (self.state.atr + 1e-9), 0.7, 1.3)
                trend_factor = 1.2 if is_strong_bull else 0.8
                buy_usdt = self._p_capital * 0.2 * vol_factor * trend_factor
                
                idx = -1
                for i in range(len(self.state.grid_lines) - 1):
                    if self.state.grid_lines[i] <= data.close < self.state.grid_lines[i+1]:
                        idx = i; break
                
                if idx != -1 and idx < 3 and context.cash >= buy_usdt:
                    signals.append(Signal(data.timestamp, self.symbol, Side.BUY, buy_usdt, meta={'size_in_quote': True}, reason=f"V7.1 Buy (Turbo)"))
                    self.state.cooldown_ends = data.timestamp + timedelta(hours=self._p_cooldown_hrs)

        return signals

    def get_status(self, context=None):
        from strategies.grid_mtf_6_0 import GridMTFStrategyV6_0
        res = GridMTFStrategyV6_0.get_status(self, context)
        res['ma50'] = round(self.ma50_15m, 2)
        res['ma200'] = round(self.ma200_15m, 2)
        res['turbo'] = True
        return res
