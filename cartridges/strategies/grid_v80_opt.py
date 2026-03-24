import os
import json
import math
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from collections import deque

from console.core import (
    MarketData, Signal, Side, OrderType, 
    FillEvent, Position, StrategyContext
)
from cartridges.strategies.base import BaseStrategy

class GridStrategyV80Opt(BaseStrategy):
    """
    GridStrategy V8.0-OPT-FINAL (Kimibigclaw)
    
    鏍稿績鐗规€э細
    - 6灏忔椂 5鍙? 鎶楁彃閽堢綉鏍间腑鏋㈣绠?
    - 5灞?7灞?鍔ㄦ€佸眰鏁板垏鎹?
    - 瀹炰綋灞傜洿鎺ヤ氦鏄?+ 铏氭嫙灞?RSI(鑷€傚簲) 杩囨护
    - 鍙屽悜鐔旀柇鍙婅繛缁啍鏂皝鍗颁繚鎶?
    - ATR 榛戝ぉ楣呮姢鐩鹃槻寰?(閫愭鍑忎粨10%)
    - 涓ユ牸鍗曞眰缁戝畾閿佸畾闃插鍚告満鍒?
    """

    def __init__(self, name: str = "Grid_V80_OPT", **params):
        super().__init__(name, **params)
        self.params_path = params.get('config_path', 'config/grid_v80_opt_btc_runtime.json')
        self.meta_path = self.params_path.replace('runtime.json', 'meta.json')
        self.symbol = params.get('symbol', 'BTC-USDT')
        self.param_metadata = {}
        self._load_params()

        # 鏁版嵁缂撳瓨 (婊¤冻6h鐨勬暟鎹姹?
        self._data_main = deque(maxlen=2000)   
        self._timeframe_mins = params.get('timeframe_minutes', 1) # 榛樿1m
        self._initialized = False
        
        # 鍥炴祴涓庣啍鏂洃鎺у瓨鍌?
        self._circuit_breaker_history: List[datetime] = []

        @dataclass
        class StrategyState:
            current_rsi: float = 50.0
            current_atr: float = 0.0          
            atr_ma: float = 0.0               
            
            # --- 6h 璁＄畻鍑虹殑鏍稿績缃戞牸灞炴€?---
            volatility: float = 0.0         # 6h 娴嬬畻鍑虹殑闇囧箙娉㈠姩鐜?
            base_top: float = 0.0           # 6h 5鍙? 椤堕儴涓灑
            base_bottom: float = 0.0        # 6h 5鍙? 搴曢儴涓灑
            active_layers_mode: int = 5     # 褰撳墠瀹為檯婵€娲荤殑灞傜骇妯″紡 (5 鎴?7)
            
            # 瀹炰綋+铏氭嫙 瀹屾暣鐨勭綉鏍煎埢搴︾嚎鏁扮粍
            grid_lines: List[float] = field(default_factory=list)
            
            # RSI 鍔ㄦ€侀槇鍊艰褰?
            dynamic_rsi_buy: float = 25.0
            dynamic_rsi_sell: float = 75.0
            
            # 鐘舵€佹帶鍒?
            is_halted: bool = False
            halt_reason: str = ""
            resume_time: Optional[datetime] = None
            
            # 榛戝ぉ楣呴鎺ф帶鍒?
            black_swan_mode: bool = False
            last_swan_exit_time: Optional[datetime] = None
            
            last_rebalance_time: Optional[datetime] = None
            
            # 涓ユ牸闃插鍚稿崰鐢ㄥ瓧鍏? key = c_idx, value = True 琛ㄧず鏈眰宸插缓浠撲笖鏈钩浠?
            layer_holdings: Dict[int, bool] = field(default_factory=dict)

        self.state = StrategyState()

    def _load_params(self):
        """鏀寔娣卞害鍔犺浇鍙傛暟"""
        if os.path.exists(self.params_path):
            try:
                with open(self.params_path, 'r', encoding='utf-8') as f:
                    self.params.update(json.load(f))
            except Exception as e:
                print(f"[V8.0-OPT] 鍔犺浇鍙傛暟澶辫触: {e}")
        
        if os.path.exists(self.meta_path):
            try:
                with open(self.meta_path, 'r', encoding='utf-8') as f:
                    self.param_metadata = json.load(f)
            except Exception as e:
                print(f"[V8.0-OPT] 鍔犺浇鍏冩暟鎹け璐? {e}")

    def initialize(self):
        super().initialize()
        print(f"[V8.0-OPT] {self.name} 鍒濆鍖栧畬鎴?)

    def on_data(self, data: MarketData, context: Optional[StrategyContext]) -> List[Signal]:
        if not self._initialized:
            self.initialize()

        # 1. 鏇存柊鍐呴儴鏁版嵁鍫嗗彔 (1m 閫昏緫锛屾寜鍒嗛挓瀵归綈鏀舵暃)
        ts = data.timestamp
        # 瀵归綈鍒板綋鍓嶅垎閽熺殑绗?绉?
        bar_ts = ts.replace(second=0, microsecond=0)
        
        if self._data_main and self._data_main[-1].timestamp.replace(second=0, microsecond=0) == bar_ts:
            # 鏇存柊褰撳墠姝ｅ湪鍙樺姩鐨?K 绾?
            last = self._data_main[-1]
            updated = MarketData(
                timestamp=data.timestamp,
                symbol=data.symbol,
                open=last.open,
                high=max(last.high, data.high),
                low=min(last.low, data.low),
                close=data.close,
                volume=data.volume
            )
            self._data_main[-1] = updated
        else:
            # 鏂扮殑涓€鍒嗛挓 Bar
            self._data_main.append(data)
        
        # 6灏忔椂 = 360 鏍?1m 绾?
        min_bars = 360 
        atr_period = self.params.get('atr_period', 14)
        if len(self._data_main) < min_bars + atr_period: # 鍔犱笂鎸囨爣鍛ㄦ湡缂撳啿
            return []

        # 2. 璁＄畻鐭嚎鎸囨爣 (Main RSI / ATR)
        self._calculate_indicators()

        # 3. 椋庢帶锛欰TR榛戝ぉ楣呭強鍙屽悜鐔旀柇闃绘柇
        is_risk_halted = self._check_risk_and_halt(data, context)

        # 4. 6灏忔椂 5鍙? 鐨勭綉鏍奸噸骞宠　璁＄畻涓庡姩鎬?RSI 閫傞厤
        if not is_risk_halted or self.state.black_swan_mode:
            self._rebalance_grid_if_needed(data)

        if self.state.base_top == 0.0 or len(self.state.grid_lines) == 0:
            return []

        # 5. 鏍规嵁褰撳墠鐨勫疄浣撳眰 / 铏氭嫙灞?鍙婇粦澶╅箙鐘舵€佷骇鐢熶氦鏄撴寚浠?
        if context:
            self._sync_position_to_layers(context, data.close)
            
            if self.state.black_swan_mode:
                return self._process_black_swan_exit(data, context)
                
            if not is_risk_halted and not self.state.is_halted:
                return self._generate_signals(data, context)
                
        return []

    def _update_data(self, data: MarketData):
        """(鍏煎鎬т繚鐣欙紝涓婚€昏緫宸叉敼鐢?on_data 鐩存帴 append)"""
        pass

    def _calculate_indicators(self):
        closes_main = pd.Series([d.close for d in self._data_main])
        rsi_cfg = self.params.get('rsi', {})
        self.state.current_rsi = self._rsi(closes_main, rsi_cfg.get('period', 14))
        
        atr_period = self.params.get('atr_period', 14)
        atr_ma_lookback = self.params.get('atr_ma_lookback', 120)
        
        highs_main = pd.Series([d.high for d in self._data_main])
        lows_main = pd.Series([d.low for d in self._data_main])
        
        atr_main_val = self._atr(highs_main, lows_main, closes_main, atr_period)
        self.state.current_atr = atr_main_val
        
        # ATR MA 杩芥函
        hist_closes = closes_main.iloc[-atr_ma_lookback:]
        hist_highs = highs_main.iloc[-atr_ma_lookback:]
        hist_lows = lows_main.iloc[-atr_ma_lookback:]
        self.state.atr_ma = self._atr(hist_highs, hist_lows, hist_closes, atr_period).mean()

    def _rebalance_grid_if_needed(self, data: MarketData):
        """鎵ц缃戞牸鏍稿績绠楁硶涓庡弬鏁拌嚜閫傚簲 - 鏀寔6灏忔椂甯歌妯″紡鎴?灏忔椂鐔旀柇閲嶇疆妯″紡"""
        current_time = data.timestamp
        
        # 妫€鏌ユ槸鍚︽槸鐔旀柇鍚庣殑4灏忔椂閲嶇疆妯″紡
        use_4h_mode = getattr(self.state, 'use_4h_grid', False)
        
        if use_4h_mode:
            # 鐔旀柇鍚庡己鍒剁珛鍗虫墽琛?灏忔椂缃戞牸璁＄畻
            self._calculate_4h_grid_with_preserve(data)
            self.state.use_4h_grid = False  # 閲嶇疆鏍囪
            return
        
        # 甯歌6灏忔椂缃戞牸閲嶅钩琛℃鏌?
        interval_mins = self.params.get('grid', {}).get('rebalance_interval_minutes', 60)
        
        if self.state.last_rebalance_time is not None:
            if (current_time - self.state.last_rebalance_time).total_seconds() < interval_mins * 60:
                return
                
        grid_cfg = self.params.get('grid', {})
        # 璁＄畻 6 灏忔椂瀵瑰簲鐨?K 绾挎牴鏁?
        lookback_bars = (grid_cfg.get('lookback_hours', 6) * 60) // self._timeframe_mins
        if len(self._data_main) < lookback_bars:
            return
        
        # 鎵ц6灏忔椂缃戞牸璁＄畻
        self._calculate_grid_core(data, lookback_bars, hours_label="6h")

    def _calculate_4h_grid_with_preserve(self, data: MarketData):
        """璁＄畻4灏忔椂缃戞牸锛堢啍鏂秴鏃跺悗鐨勯噸缃ā寮忥級"""
        print(f"[V8.0-OPT] 寮€濮嬭绠?灏忔椂缃戞牸锛堢啍鏂噸缃ā寮忥級")
        
        # 浣跨敤4灏忔椂鏁版嵁
        lookback_bars = (4 * 60) // self._timeframe_mins  # 4灏忔椂 = 240鏍?鍒嗛挓绾?
        if len(self._data_main) < lookback_bars:
            print(f"[V8.0-OPT] 4灏忔椂鏁版嵁涓嶈冻({len(self._data_main)}/{lookback_bars})锛屼娇鐢ㄥ叏閮ㄥ彲鐢ㄦ暟鎹?)
            lookback_bars = len(self._data_main)
        
        # 鎵ц4灏忔椂缃戞牸璁＄畻
        self._calculate_grid_core(data, lookback_bars, hours_label="4h")
        
        print(f"[V8.0-OPT] 4灏忔椂缃戞牸閲嶇疆瀹屾垚 | 淇濈暀鍏ㄩ儴鎸佷粨浣滀负鏂扮綉鏍煎簳浠?)

    def _calculate_grid_core(self, data: MarketData, lookback_bars: int, hours_label: str = "6h"):
        """缃戞牸鏍稿績璁＄畻 - 5鍙?绠楁硶"""
        history = list(self._data_main)[-lookback_bars:]
        
        grid_cfg = self.params.get('grid', {})
        segments = grid_cfg.get('sample_points', 5)
        segment_size = len(history) // segments
        
        high_points = []
        low_points = []
        
        for i in range(segments):
            start_idx = i * segment_size
            end_idx = start_idx + segment_size if i < segments - 1 else len(history)
            seg_data = history[start_idx:end_idx]
            
            h = max([d.high for d in seg_data])
            l = min([d.low for d in seg_data])
            high_points.append(h)
            low_points.append(l)
            
        high_points.sort()
        low_points.sort()
        
        h_trimmed = high_points[1:-1]
        l_trimmed = low_points[1:-1]
        
        base_top = sum(h_trimmed) / len(h_trimmed)
        base_bottom = sum(l_trimmed) / len(l_trimmed)
        
        self.state.base_top = base_top
        self.state.base_bottom = base_bottom
        
        volatility = (base_top - base_bottom) / base_bottom if base_bottom > 0 else 0
        self.state.volatility = volatility
        
        layer_cfg = self.params.get('layer', {})
        base_layers = layer_cfg.get('base_layers', 5)
        vol_threshold = layer_cfg.get('volatility_threshold', 0.012)
        virtual_layers = layer_cfg.get('virtual_layers', 2)
        
        if volatility > vol_threshold:
            active_layers = base_layers + 2  # 7灞傛ā寮?
        else:
            active_layers = base_layers      # 5灞傛ā寮?
            
        self.state.active_layers_mode = active_layers
        
        layer_height = (base_top - base_bottom) / active_layers
        
        real_lines = []
        for i in range(active_layers + 1):
            real_lines.append(base_bottom + i * layer_height)
            
        lower_v_lines = []
        for i in range(1, virtual_layers + 1):
            lower_v_lines.insert(0, base_bottom - i * layer_height)
            
        upper_v_lines = []
        for i in range(1, virtual_layers + 1):
            upper_v_lines.append(base_top + i * layer_height)
            
        self.state.grid_lines = lower_v_lines + real_lines + upper_v_lines
        
        rsi_cfg = self.params.get('rsi', {})
        if rsi_cfg.get('dynamic_adjustment', True):
            adj = rsi_cfg.get('adjustment_factors', {})
            high_vol = adj.get('high_volatility', {})
            low_vol = adj.get('low_volatility', {})
            normal = adj.get('normal', {})
            
            if volatility > high_vol.get('volatility_min', 0.02):
                self.state.dynamic_rsi_buy = high_vol.get('buy', 20)
                self.state.dynamic_rsi_sell = high_vol.get('sell', 80)
            elif volatility < low_vol.get('volatility_max', 0.012):
                self.state.dynamic_rsi_buy = low_vol.get('buy', 30)
                self.state.dynamic_rsi_sell = low_vol.get('sell', 70)
            else:
                self.state.dynamic_rsi_buy = normal.get('buy', 25)
                self.state.dynamic_rsi_sell = normal.get('sell', 75)
        else:
            self.state.dynamic_rsi_buy = rsi_cfg.get('buy_threshold', 25)
            self.state.dynamic_rsi_sell = rsi_cfg.get('sell_threshold', 75)
            
        self.state.last_rebalance_time = data.timestamp
        print(f"[V8.0-OPT] 閲嶇畻缃戞牸瀹屾垚 [{hours_label}] | Vol={volatility*100:.2f}% ({active_layers}灞? RSI=[{self.state.dynamic_rsi_buy}-{self.state.dynamic_rsi_sell}]")

    def _check_risk_and_halt(self, data: MarketData, context: Optional[StrategyContext]) -> bool:
        """
        瀹屾暣椋庢帶妫€鏌ワ細鍙屽悜鐔旀柇(鏅鸿兘瑙傚療妯″紡) + 榛戝ぉ楣?+ 杩炵画鐔旀柇灏佸嵃
        杩斿洖 True = 闃绘柇浜ゆ槗
        """
        now = data.timestamp
        cb_cfg = self.params.get('circuit_breaker', {})
        bs_cfg = self.params.get('black_swan', {})
        
        # === 1. 妫€鏌ユ槸鍚﹀凡鍦ㄦ煇绉嶇啍鏂姸鎬佷腑 ===
        
        # 1.1 鍙屽悜鐔旀柇瑙傚療鏈燂紙鏅鸿兘瑙傚療妯″紡锛?
        if self.state.is_halted and self.state.halt_reason and self.state.halt_reason.startswith("OBSERVE"):
            return self._handle_observation_mode(data, now)
        
        # 1.2 榛戝ぉ楣呮ā寮忥紙鍑忎粨淇濇姢锛?
        if self.state.black_swan_mode:
            return True  # 闃绘柇鏂板紑浠擄紝鐢?_process_black_swan_exit 澶勭悊鍑忎粨
        
        # 1.3 杩炵画鐔旀柇灏佸嵃
        if self.state.is_halted and self.state.halt_reason and "Meltdown" in self.state.halt_reason:
            if now >= self.state.resume_time:
                self._resume_from_meltdown()
            return True
        
        # === 2. 妫€鏌ヨ繛缁啍鏂鏁帮紙24灏忔椂鍐咃級===
        if cb_cfg.get('enabled', True):
            if self._check_consecutive_limit(now, cb_cfg):
                return True
        
        # === 3. 妫€鏌TR榛戝ぉ楣咃紙浼樺厛浜庡弻鍚戠啍鏂級===
        if bs_cfg.get('enabled', True):
            if self._check_black_swan_trigger(data, bs_cfg):
                return True
        
        # === 4. 妫€鏌ュ弻鍚戣秺鐣岀啍鏂紙鏅鸿兘瑙傚療妯″紡锛?==
        if cb_cfg.get('enabled', True):
            if self._check_bidirectional_breaker(data, now, cb_cfg):
                return True
        
        return False

    def _check_bidirectional_breaker(self, data: MarketData, now: datetime, cb_cfg: dict) -> bool:
        """鍙屽悜瓒婄晫鐔旀柇 - 鏅鸿兘瑙傚療妯″紡"""
        if len(self.state.grid_lines) == 0:
            return False
        
        trigger_beyond = cb_cfg.get('trigger_beyond_virtual', True)
        if not trigger_beyond:
            return False
        
        # 绐佺牬铏氭嫙灞傝Е鍙?
        if data.close < self.state.grid_lines[0] or data.close > self.state.grid_lines[-1]:
            direction = "DOWN" if data.close < self.state.grid_lines[0] else "UP"
            self._enter_observation_mode(now, direction, data.close)
            return True
        
        return False

    def _enter_observation_mode(self, now: datetime, direction: str, trigger_price: float):
        """杩涘叆瑙傚療鏈?- 鎸佷粨涓嶅彉锛岀瓑寰呬环鏍煎洖褰掓垨瓒呮椂"""
        self.state.is_halted = True
        self.state.halt_reason = f"OBSERVE_{direction}"
        self.state.halt_start_time = now
        self.state.halt_trigger_price = trigger_price
        self.state.halt_grid_bottom = self.state.base_bottom
        self.state.halt_grid_top = self.state.base_top
        
        # 璁板綍鐔旀柇鍘嗗彶
        self._circuit_breaker_history.append(now)
        
        print(f"[V8.0-OPT] 鐔旀柇瑙﹀彂 | 鏂瑰悜: {direction} | 瑙﹀彂浠? {trigger_price}")
        print(f"[V8.0-OPT] 杩涘叆2灏忔椂瑙傚療鏈?| 鎸佷粨涓嶅彉 | 绛夊緟浠锋牸鍥炲綊缃戞牸...")

    def _handle_observation_mode(self, data: MarketData, now: datetime) -> bool:
        """澶勭悊瑙傚療鏈熼€昏緫 - 杩斿洖True琛ㄧず缁х画闃绘柇锛孎alse琛ㄧず鎭㈠浜ゆ槗"""
        elapsed = (now - self.state.halt_start_time).total_seconds()
        
        grid_bottom = self.state.halt_grid_bottom
        grid_top = self.state.halt_grid_top
        current_price = data.close
        
        # 鎯呭喌1: 浠锋牸鍥炲綊缃戞牸 鈫?鎻愬墠鎭㈠
        if grid_bottom <= current_price <= grid_top:
            self._resume_from_observation("PRICE_RETURN", elapsed)
            return False  # 涓嶉樆鏂紝鎭㈠浜ゆ槗
        
        # 鎯呭喌2: 婊?灏忔椂鏈洖褰?鈫?閲嶇疆4灏忔椂缃戞牸
        cooldown_seconds = 2 * 3600  # 2灏忔椂 = 7200绉?
        if elapsed >= cooldown_seconds:
            self._reset_grid_after_timeout(now)
            return False  # 鏂扮綉鏍煎凡鐢熸垚锛屾仮澶嶄氦鏄?
        
        # 鎯呭喌3: 浠嶅湪瑙傚療涓?鈫?闃绘柇浜ゆ槗锛屾瘡5鍒嗛挓鎵撳嵃鏃ュ織
        if int(elapsed) % 300 == 0 and elapsed > 0:
            remaining = cooldown_seconds - elapsed
            print(f"[V8.0-OPT] 瑙傚療涓?| 宸茶繃: {elapsed/60:.0f}鍒?| 鍓╀綑: {remaining/60:.0f}鍒?| 浠锋牸: {current_price:.2f}")
        
        return True

    def _resume_from_observation(self, reason: str, elapsed_sec: float):
        """浠锋牸鍥炲綊锛屾彁鍓嶆仮澶嶆甯?""
        self.state.is_halted = False
        self.state.halt_reason = ""
        self.state.halt_start_time = None
        
        print(f"[V8.0-OPT] 鐔旀柇瑙ｉ櫎 | 鍘熷洜: {reason}")
        print(f"[V8.0-OPT] 瑙傚療鏃堕暱: {elapsed_sec/60:.1f}鍒嗛挓 | 鎸佷粨涓嶅彉 | 鎭㈠姝ｅ父浜ゆ槗")

    def _reset_grid_after_timeout(self, now: datetime):
        """2灏忔椂瓒呮椂锛屼繚鐣欐寔浠撻噸缃?灏忔椂缃戞牸"""
        # 淇濆瓨褰撳墠鎸佷粨淇℃伅
        preserved_btc = 0.0
        avg_price = 0.0
        
        print(f"[V8.0-OPT] 瑙傚療鏈熸弧2灏忔椂 | 浠锋牸鏈洖褰?| 鍚姩4灏忔椂缃戞牸閲嶇疆")
        
        # 閲嶇疆瑙傚療鏈熺姸鎬?
        self.state.is_halted = False
        self.state.halt_reason = ""
        self.state.halt_start_time = None
        
        # 鏍囪闇€瑕侀噸缃綉鏍硷紙浣跨敤4灏忔椂鏁版嵁锛夛紝鍦?_rebalance_grid_if_needed 涓鐞?
        self.state.last_rebalance_time = None
        self.state.use_4h_grid = True  # 鏍囪浣跨敤4灏忔椂妯″紡
        
        print(f"[V8.0-OPT] 鏂扮綉鏍煎弬鏁板凡璁剧疆 | 涓嬫閲嶅钩琛″皢浣跨敤4灏忔椂鏁版嵁骞朵繚鐣欐寔浠?)

    def _check_black_swan_trigger(self, data: MarketData, bs_cfg: dict) -> bool:
        """妫€鏌TR榛戝ぉ楣呰Е鍙?""
        if self.state.atr_ma <= 0:
            return False
        
        if self.state.current_atr >= self.state.atr_ma * bs_cfg.get('atr_multiplier', 3.0):
            self.state.is_halted = True
            self.state.black_swan_mode = True
            self.state.halt_reason = "Black Swan (ATR Surge)"
            self.state.last_swan_exit_time = None
            self._circuit_breaker_history.append(data.timestamp)
            
            print(f"[V8.0-OPT] 瑙﹀彂榛戝ぉ楣呯啍鏂?| ATR: {self.state.current_atr:.2f} | 鍧囩嚎: {self.state.atr_ma:.2f}")
            print(f"[V8.0-OPT] 鍋滄鏂板紑浠擄紝鍚姩姣?0鍒嗛挓鑷姩甯備环鍑忎粨绋嬪簭")
            return True
        
        return False

    def _check_consecutive_limit(self, now: datetime, cb_cfg: dict) -> bool:
        """妫€鏌?4灏忔椂鍐呯啍鏂鏁?""
        cutoff = now - timedelta(hours=24)
        self._circuit_breaker_history = [t for t in self._circuit_breaker_history if t > cutoff]
        
        limit = cb_cfg.get('consecutive_limit', 3)
        if len(self._circuit_breaker_history) >= limit:
            self.state.is_halted = True
            self.state.halt_reason = "Consecutive Meltdown (Max limit reached within 24h)"
            self.state.resume_time = now + timedelta(hours=12)
            
            print(f"[V8.0-OPT] 杩炵画鐔旀柇淇濇姢 | 24灏忔椂鍐呭凡鐔旀柇{len(self._circuit_breaker_history)}娆?)
            print(f"[V8.0-OPT] 杩涘叆12灏忔椂灏佸嵃鏈?| 瀹屽叏鍋滄浜ゆ槗")
            return True
        
        return False

    def _resume_from_meltdown(self):
        """浠庤繛缁啍鏂皝鍗颁腑鎭㈠"""
        self.state.is_halted = False
        self.state.halt_reason = ""
        self.state.resume_time = None
        self.state.last_rebalance_time = None
        print(f"[V8.0-OPT] 灏佸嵃瑙ｉ櫎 | 鎭㈠浜ゆ槗锛屽己鍒跺埛鏂板熀鍑?)

    def _process_black_swan_exit(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        pos = context.positions.get(self.symbol)
        pos_size = float(pos.size) if pos else 0.0
        
        if pos_size <= 0:
            self.state.black_swan_mode = False
            self.state.is_halted = False
            self.state.halt_reason = ""
            print(f"[V8.0-OPT] 榛戝ぉ楣呭凡琚寲瑙ｏ紝宸插畬鎴愬叏浠撴竻鐩樸€傜瓑寰呴噸鍚€?)
            return []

        # 鑻ヤ环鏍煎弽寮硅秴鎴愭湰浠?鈫?鍋滄鍑忎粨锛屾仮澶嶆甯?
        if data.close >= float(pos.avg_price):
            print(f"[V8.0-OPT] 榛戝ぉ楣呮湡闂村己鍔插弽寮癸紝浠锋牸宸茶鐩栧钩鍧囨垚鏈紝鎾ら攢璀︽姤銆?)
            self.state.black_swan_mode = False
            self.state.is_halted = False
            self.state.halt_reason = ""
            return []

        # 姣?0鍒嗛挓璇勪及涓€娆?
        mins_interval = self.params.get('black_swan', {}).get('gradual_exit_interval_minutes', 10)
        if self.state.last_swan_exit_time is None or (data.timestamp - self.state.last_swan_exit_time).total_seconds() >= mins_interval * 60:
            self.state.last_swan_exit_time = data.timestamp
            
            # 鍗栧嚭鎬讳粨浣嶇殑10%
            sell_qty = pos_size * 0.1
            
            trading_cfg = self.params.get('trading', {})
            cap = trading_cfg.get('initial_capital', 10000)
            layer_val = (cap * trading_cfg.get('max_position_pct', 0.8)) / self.state.active_layers_mode
            
            # 娈嬫崯閲戦涓嶈冻浠ュ垏鍒嗘椂鐩存帴娓呯洏
            if pos_size * data.close < layer_val * 0.4:
                 sell_qty = pos_size
                 
            print(f"[V8.0-OPT] 榛戝ぉ楣呭噺浠撴墽琛屼腑: 鎶涘敭 {sell_qty:.4f}")
            return [Signal(
                timestamp=data.timestamp, symbol=self.symbol, side=Side.SELL,
                size=sell_qty, reason="Black Swan Gradual Exit (-10%)"
            )]
            
        return []

    def _sync_position_to_layers(self, context: StrategyContext, current_price: float):
        """涓ユ牸閲嶅缓鐩墠琚攣瀹氱殑澶瑰眰缁撴瀯"""
        pos = context.positions.get(self.symbol)
        pos_size = float(pos.size) if pos else 0.0
        if pos_size <= 0:
            self.state.layer_holdings.clear()
            return

        trading_cfg = self.params.get('trading', {})
        cap = trading_cfg.get('initial_capital', 10000)
        max_pct = trading_cfg.get('max_position_pct', 0.8)
        
        target_total = cap * max_pct
        layer_cap = target_total / self.state.active_layers_mode 
        layer_size_expected = layer_cap / current_price if current_price > 0 else 0
        
        if layer_size_expected > 0:
            expected_layers = int(round(pos_size / layer_size_expected))
            if expected_layers != len(self.state.layer_holdings):
                # We need to rebuild it accurately mapping locked bottom up
                self.state.layer_holdings.clear()
                V = self.params.get('layer', {}).get('virtual_layers', 2)
                for i in range(expected_layers):
                    # Forcing synthetic locks from bottom virtual+real layer upwards
                    # Index mapping logic: V represents lowest real layer
                    self.state.layer_holdings[V + i] = True

    def _get_current_layer_index(self, price: float) -> int:
        lines = self.state.grid_lines
        if len(lines) == 0:
            return -1
        if price <= lines[0]: return 0
        if price >= lines[-1]: return len(lines) - 2
        for i in range(len(lines) - 1):
            if lines[i] <= price <= lines[i + 1]:
                return i
        return -1


    def _generate_signals(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        signals = []
        pos = context.positions.get(self.symbol)
        pos_size = float(pos.size) if pos else 0.0
        
        trading_cfg = self.params.get('trading', {})
        total_cap = trading_cfg.get('initial_capital', 10000)
        max_pct = trading_cfg.get('max_position_pct', 0.8)
        max_capital = total_cap * max_pct
        
        layer_value = max_capital / self.state.active_layers_mode

        c_idx = self._get_current_layer_index(data.close)
        lines = self.state.grid_lines
        if c_idx == -1 or len(lines) == 0:
            return []
            
        virtual_layers_cnt = self.params.get('layer', {}).get('virtual_layers', 2)
        is_lower_virtual = c_idx < virtual_layers_cnt
        is_upper_virtual = c_idx >= len(lines) - 1 - virtual_layers_cnt
        is_real = not (is_lower_virtual or is_upper_virtual)
        
        # 涓ユ牸鎸夌収鏂囨。閿佹瀹炰綋灞傜紪鍙风殑瑙掕壊鏉冮檺
        # 5灞? 0(涔?, 1/2(缂撳啿), 3/4(鍗?
        # 7灞? 0/1(涔?, 2/3/4(缂撳啿), 5/6(鍗?
        sell_allowed_in_real = False
        buy_allowed_in_real = False
        
        if is_real:
            r_idx = c_idx - virtual_layers_cnt
            if self.state.active_layers_mode == 5:
                if r_idx in (3, 4): sell_allowed_in_real = True
                if r_idx == 0: buy_allowed_in_real = True
            else: # 7 layers
                if r_idx in (5, 6): sell_allowed_in_real = True
                if r_idx in (0, 1): buy_allowed_in_real = True

        # ---------------- 鍒ゅ畾鍗栧嚭 (姝㈢泩) ----------------
        should_sell = False
        sell_reason = ""
        
        if pos_size > 0:
            if is_upper_virtual:
                if self.state.current_rsi >= self.state.dynamic_rsi_sell:
                    should_sell = True
                    sell_reason = f"Virtual High Zone Sell (RSI {self.state.current_rsi:.1f})"
            elif is_real and sell_allowed_in_real:
                # 鍙湁鍦ㄨ繖涓や釜椤跺眰鎵嶈兘鐩存帴鍗栧嚭
                should_sell = True
                sell_reason = f"Real Zone Top Layer Profit (Layer {c_idx})"
            
            if should_sell:
                sell_sz = min(pos_size, layer_value / data.close)
                if pos_size * data.close < layer_value * 1.5:  
                    sell_sz = pos_size
                
                # 骞充粨鏃惰В闄ゆ渶椤堕儴涓€涓喕缁撳眰鐨勯攣
                if self.state.layer_holdings:
                    highest_layer = max(self.state.layer_holdings.keys())
                    self.state.layer_holdings.pop(highest_layer)
                    
                signals.append(Signal(
                    timestamp=data.timestamp, symbol=self.symbol, side=Side.SELL,
                    size=sell_sz, reason=sell_reason
                ))
                return signals

        # ---------------- 鍒ゅ畾涔板叆 (寤轰粨) ----------------
        should_buy = False
        buy_reason = ""
        
        # 涓ユ牸闃插鍚搁殧绂伙細褰撳墠鍖洪棿灞傝嫢琚缓浠撹繃锛屾棤璁鸿窛绂诲杩滈兘涓嶅啀杩介珮鎴栬ˉ浠?
        if c_idx in self.state.layer_holdings:
            return signals

        if pos_size * data.close + layer_value * 0.95 <= max_capital and context.cash >= layer_value * 0.95:
            if is_lower_virtual:
                if self.state.current_rsi <= self.state.dynamic_rsi_buy:
                    should_buy = True
                    buy_reason = f"Virtual Low Zone Buy (RSI {self.state.current_rsi:.1f})"
            elif is_real and buy_allowed_in_real:
                should_buy = True
                buy_reason = f"Real Zone Bottom Layer Strike (Layer {c_idx})"

            if should_buy:
                self.state.layer_holdings[c_idx] = True
                signals.append(Signal(
                    timestamp=data.timestamp, symbol=self.symbol, side=Side.BUY,
                    size=layer_value, meta={'size_in_quote': True},
                    reason=buy_reason
                ))

        return signals


    # Helper Utils
    def _rsi(self, series, period):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs.iloc[-1])) if not np.isnan(rs.iloc[-1]) else 50.0

    def _atr(self, high, low, close, period):
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        return tr.rolling(window=period).mean().iloc[-1]

    def get_status(self, context: Optional[StrategyContext] = None) -> Dict[str, Any]:
        signal_text = "瑙傚療 / 瑙傛湜"
        signal_color = "neutral"
        
        if self.state.is_halted:
            if self.state.black_swan_mode:
                signal_text = f"榛戝ぉ楣呯啍鏂?(閫愭鍑忎粨淇濇姢)"
            else:
                signal_text = f"鐔旀柇鍐峰嵈涓?({self.state.halt_reason})"
            signal_color = "sell"
            
        pos_size = 0.0
        pos_avg_price = 0.0
        pos_unrealized_pnl = 0.0
        pos_count = 0
        
        if context and self.symbol in context.positions:
            pos = context.positions[self.symbol]
            pos_size = float(pos.size)
            pos_avg_price = float(pos.avg_price)
            pos_unrealized_pnl = float(pos.unrealized_pnl)
            
            p_trade = self.params.get('trading', {})
            layer_cap = (p_trade.get('initial_capital', 10000) * p_trade.get('max_position_pct', 0.8)) / max(self.state.active_layers_mode, 1)
            if pos_size > 0 and pos_avg_price > 0:
                pos_count = max(1, int(round((pos_size * pos_avg_price) / layer_cap)))

        gl = self.state.grid_lines
        lower_bound = gl[0] if len(gl) > 0 else 0
        upper_bound = gl[-1] if len(gl) > 0 else 0

        return {
            'name': self.name,
            'current_rsi': float(np.round(self.state.current_rsi, 2)),
            'atr': float(np.round(self.state.current_atr, 2)),
            'atr_ma': float(np.round(self.state.atr_ma, 2)),
            'atrVal': float(np.round(self.state.current_atr, 2)),
            'volatility_state': f"{self.state.volatility*100:.2f}% ({self.state.active_layers_mode}灞傚疄浣?",
            'marketRegime': f"妯″紡: {self.state.active_layers_mode}灞傚疄浣?,
            'vol_trend': '榛戝ぉ楣呴槻寰″紑鍚? if self.state.black_swan_mode else '鑷€傚簲瑙﹀彂',
            'current_volume': float(self._data_main[-1].volume) if self._data_main else 0.0,
            
            'signal_text': signal_text,
            'signal_color': signal_color,
            
            'position_size': pos_size,
            'position_avg_price': pos_avg_price,
            'position_unrealized_pnl': pos_unrealized_pnl,
            'position_count': pos_count,
            
            'grid_lower': float(np.round(lower_bound, 2)),
            'grid_upper': float(np.round(upper_bound, 2)),
            'grid_range': f"{lower_bound:.1f} - {upper_bound:.1f}" if lower_bound > 0 else "璁＄畻涓?..",
            'grid_lines': gl,
            'layer_holdings': list(self.state.layer_holdings.keys()),
            
            'rsi_oversold': float(np.round(self.state.dynamic_rsi_buy, 1)),
            'rsi_overbought': float(np.round(self.state.dynamic_rsi_sell, 1)),
            
            'is_halted': self.state.is_halted,
            'halt_reason': self.state.halt_reason,
            'params': self.params,
            'param_metadata': self.param_metadata
        }
