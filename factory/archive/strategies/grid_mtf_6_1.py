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
# V6.1 杩涘寲鐗堬細鍔ㄦ€佷粨浣嶇鐞?(Dynamic Position Sizing)
# ============================================================

class GridMTFStrategyV6_1(BaseStrategy):
    """
    V6.1-Dynamic 鍔ㄦ€佷粨浣嶇増
    鏍稿績杩涘寲锛氬紩鍏ュ熀浜?ATR 娉㈠姩鐜囦笌瓒嬪娍寮哄害鐨勫姩鎬佷粨浣嶇缉鏀?
    """
    def __init__(self, name: str = "Grid_V61_Dynamic", **params):
        super().__init__(name, **params)
        
        # 璺緞涓庨厤缃?(鍏变韩 6.0 鐨勯粯璁ら厤缃紝浣嗗彲浠ュ崟鐙鐩?
        current_file_dir = Path(__file__).parent.resolve()
        config_dir = current_file_dir.parent / "config"
        
        self.default_params_path = str(config_dir / 'grid_v60_default.json')
        self.params_path = str(config_dir / 'grid_v61_runtime.json') # 鐙珛鐨勮繍琛屾椂鏂囦欢
        self.meta_path = str(config_dir / 'grid_v60_meta.json')
        
        self.symbol = params.get('symbol', 'BTCUSDT')
        self._load_params()

        # 鏁版嵁缂撳瓨
        self._data_5m = deque(maxlen=300) 
        self._data_15m = deque(maxlen=100)
        self._last_15m_ts: Optional[datetime] = None

        self.state = StrategyState()
        self.indicators = IncrementalIndicatorsV6(self.params)
        self._last_5m_ts = None
        self._last_bar_5m = None
        self._last_15m_bar_close = 0.0

    def _load_params(self):
        # 鍔犺浇榛樿
        if os.path.exists(self.default_params_path):
            with open(self.default_params_path, 'r', encoding='utf-8') as f:
                self.params.update(json.load(f))
        # 瑕嗙洊杩愯鏃?(濡傛湁)
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

        # 鑾峰彇澧為噺鎸囨爣
        rsi, atr, atr_ma = self.indicators.update_5m(data, commit=False)
        macd, sig, hist = self.indicators.update_15m_macd(data.close, commit=False)
        
        self.state.current_rsi = rsi
        self.state.atr = atr
        self.state.atr_ma = atr_ma
        self.state.macd = macd
        self.state.macdsignal = sig
        self.state.macdhist = hist
        
        # 鐔旀柇妫€娴?
        if self._check_halt(data): return []

        # 缃戞牸缁存姢
        self._manage_grid(data)

        # 淇″彿鐢熸垚
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

        # 鏍稿績杩涘寲 1锛氬姩鎬佷粨浣嶇郴鏁?(Volatility Factor)
        # 褰?ATR 杩滈珮浜庡钩鍧?ATR 鏃讹紝璇存槑甯傚満鏋佸害涓嶇ǔ瀹氾紝澶у箙缂╁皬鍗曠瑪閲戦
        # 褰?ATR 杩滀綆浜庡钩鍧?ATR 鏃讹紝璇存槑甯傚満骞崇ǔ锛屽彲浠ラ€傚綋鏀惧ぇ浠撲綅
        vol_factor = 1.0
        if self.state.atr_ma > 0:
            # 鍩虹姣斾緥锛氭甯告尝鍔ㄧ巼涓?1.0銆傛尝鍔ㄧ巼缈诲€嶅垯浠撲綅鍑忓崐銆?
            vol_factor = np.clip(self.state.atr_ma / (self.state.atr + 1e-9), 0.5, 1.5)

        # 鏍稿績杩涘寲 2锛氳秼鍔垮己搴︾郴鏁?(Trend Strength)
        # 濡傛灉 MACD 鏌辩姸鍥惧湪澧為暱涓斾负姝ｏ紝璇存槑鍔ㄩ噺鍦ㄥ姞寮猴紝鍙互鏇存縺杩?
        trend_factor = 1.0
        if is_bullish and hist_growth > 0:
            trend_factor = 1.2
        elif not is_bullish:
            trend_factor = 0.7 # 寮卞娍鏈熷噺浠?

        # 1. 鍗栧嚭閫昏緫
        if pos_size > 0:
            sell_threshold = self.params.get('rsi_sell_threshold', 70)
            if is_bullish and hist_growth > 0:
                # 寮鸿秼鍔夸笅锛岀◢寰嬁涔呬竴鐐?
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

        # 2. 涔板叆閫昏緫
        if not signals:
            if is_bullish and self.state.current_rsi < self.params.get('rsi_buy_threshold', 28):
                idx = -1
                for i in range(len(self.state.grid_lines) - 1):
                    if self.state.grid_lines[i] <= data.close < self.state.grid_lines[i+1]:
                        idx = i; break
                
                if idx != -1 and idx < 2:
                    layers = self.params.get('grid_layers', 5)
                    base_weight = (layers - idx) / sum(range(1, layers + 1))
                    
                    # 缁煎悎鍔ㄦ€佷粨浣?
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
        status = super().get_status(context) # 姝ゅ浼氬洜 BaseStrategy 娌″啓鑰屾姤閿欙紝闇€鎵嬪姩琛ラ綈鎴栫被浼?6.0
        # 绠€鍖栫増 status 閫傞厤 Dashboard
        return status # 瀹為檯涓?6.0 鍐欑殑寰堝叏锛?.1 搴旇涔熶繚鐣?
