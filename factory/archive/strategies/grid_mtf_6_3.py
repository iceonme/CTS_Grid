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
# V6.3 绌舵瀬杩涘寲鐗堬細楂樼偣鍒╂鼎閿佸畾 (Eagle Peak Lock)
# ============================================================

class GridMTFStrategyV6_3(BaseStrategy):
    """
    V6.3-Eagle 鐚庨拱鐗?
    鏍稿績杩涘寲锛?
    1. 瓒嬪娍杩借釜姝㈢泩 (Trailing TP)锛氬湪 15m MACD 寮哄澶村悗鍑虹幇琛扮淇″彿鏃讹紝澶ф瘮渚嬪鐜般€?
    2. 鍥炴挙鑷€傚簲鍏ュ満 (Drawdown Barrier)锛氬湪鎬ヨ穼鍚庣殑闇囪崱鏈熸墠寮€鍚綉鏍硷紝閬垮厤闃磋穼鏈熻繃搴︽秷鑰楄祫閲戙€?
    3. 闆嗘垚 6.1 鐨勫姩鎬佷粨浣嶉€昏緫銆?
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
        
        # 6.3 鐗规湁鐘舵€?
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
            # 15m 鑱氬悎鍚屾
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
        
        # 妫€娴嬬啍鏂?
        if self._check_halt(data): return []
        
        # 缃戞牸缁存姢
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
        
        # 鏇存柊宄板€艰祫浜?
        if total_val > self.peak_equity:
            self.peak_equity = total_val
            
        is_bullish = self.state.macdhist > 0
        self.state.macdhist_prev = getattr(self.state, 'macdhist_prev', self.state.macdhist)
        hist_growth = self.state.macdhist - self.state.macdhist_prev
        self.state.macdhist_prev = self.state.macdhist

        # 鏍稿績杩涘寲锛氶珮鐐逛繚鎶ら€昏緫
        # 濡傛灉褰撳墠璧勪骇浠庡嘲鍊煎洖鎾よ秴杩?5%锛屼笖 MACD 鏌辩姸鍥惧湪璧板急锛屽垯瑙嗕负鈥滃啿楂樺洖钀解€濓紝杩涘叆闃插尽閿佸畾鐘舵€併€?
        mdd_from_peak = (self.peak_equity - total_val) / self.peak_equity if self.peak_equity > 0 else 0
        if mdd_from_peak > 0.05 and not is_bullish:
            # 鍦ㄨ繖绉嶇姸鎬佷笅锛屾垜浠澶ф瘮渚嬪崠鍑猴紝鐩村埌瓒嬪娍閲嶆柊绔欑ǔ
            self.is_locking = True
        elif is_bullish and hist_growth > 0:
            self.is_locking = False # 閲嶆柊绔欑ǔ锛屾仮澶?

        # 1. 鍗栧嚭閫昏緫
        if pos_size > 0:
            # 鍗栫偣 1: 姝ｅ父缃戞牸鍗栧嚭
            sell_threshold = self.params.get('rsi_sell_threshold', 70)
            if self.state.current_rsi > sell_threshold and data.close >= self.state.grid_lines[-2]:
                signals.append(Signal(data.timestamp, self.symbol, Side.SELL, pos_size, reason="Grid TP"))
            
            # 鍗栫偣 2: 鐚庨拱姝㈢泩 (閿佸畾楂樹綅鍒╂鼎)
            if not signals and self.is_locking:
                # 鍙湁褰撴寔浠撶浉瀵逛簬鎬讳环鍊艰秴杩囦竴瀹氭瘮渚嬫椂鎵嶁€滃ぇ鐮嶁€濓紝闃叉姣忓垎閽熶骇鐢熷井灏忓崠鍗?
                if pos_size * data.close > total_val * 0.1:
                    signals.append(Signal(data.timestamp, self.symbol, Side.SELL, pos_size * 0.9, reason="Eagle Peak Lock"))

        # 2. 涔板叆閫昏緫
        if not signals:
            # 鍙湁鍦ㄩ潪閿佸畾鐘舵€佷笅锛屼笖 MACD 寮哄澶达紝鎵嶅厑璁哥綉鏍间拱鍏?
            if not self.is_locking and is_bullish and self.state.current_rsi < self.params.get('rsi_buy_threshold', 28):
                idx = -1
                for i in range(len(self.state.grid_lines) - 1):
                    if self.state.grid_lines[i] <= data.close < self.state.grid_lines[i+1]:
                        idx = i; break
                
                if idx != -1 and idx < 2:
                    # 闆嗘垚 6.1 鐨勫姩鎬佷粨浣?
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
        from cartridges.strategies.grid_mtf_6_0 import GridMTFStrategyV6_0
        res = GridMTFStrategyV6_0.get_status(self, context)
        res['eagle_locking'] = self.is_locking
        res['peak_equity'] = round(self.peak_equity, 2)
        return res
