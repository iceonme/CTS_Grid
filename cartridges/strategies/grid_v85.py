import os
import json
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

class GridStrategyV85(BaseStrategy):
    """
    GridStrategy V8.5 (Jeff Huang 鐗?
    
    鏍稿績閫昏緫锛?
    - 6灏忔椂 (360min) "5鍙?" 鎶楁彃閽堢綉鏍间腑鏋㈣绠?
    - 鍔ㄦ€佸眰鏁?(5灞?7灞? 鑷姩鍒囨崲
    - L0 缂撳啿瑙傛湜灞?(浠锋牸杩涘叆 L0 涓嶄氦鏄?
    - 鍖洪棿鎰熷簲瑙﹀彂锛氫笅鍗婂眰涔板叆 (0-50%) / 涓婂崐灞傚崠鍑?(50-100%)
    - 1/n 鍔ㄦ€佸垎浠擄細涔板叆鍒濆璧勯噾 1/n锛屽崠鍑哄綋鍓嶆寔浠?1/n
    - 2灏忔椂瑙傚療鐔旀柇鏈燂細瓒呮椂鍚庝繚鐣欐寔浠撳苟閲嶇畻缃戞牸
    - 澧炲己鍨嬫棩蹇楋細瀹炴椂杈撳嚭鍖洪棿娣卞害涓庡喅绛栬鎯?
    """

    def __init__(self, name: str = "Grid_V85_Jeff", **params):
        super().__init__(name, **params)
        self.symbol = params.get('symbol', 'BTC-USDT')
        
        # 鏁版嵁缂撳瓨 (婊¤冻 4h = 240min 鐨勬暟鎹姹?
        self._data_1m = deque(maxlen=500)   # 鍐椾綑缂撳瓨
        self._initialized = False
        
        @dataclass
        class StrategyState:
            current_rsi: float = 50.0
            volatility: float = 0.0
            avg_gain: float = 0.0          # 宸插簾寮冿紝淇濈暀鍏煎鎬?
            avg_loss: float = 0.0          # 宸插簾寮冿紝淇濈暀鍏煎鎬?
            gain_dq: deque = field(default_factory=lambda: deque(maxlen=14))
            loss_dq: deque = field(default_factory=lambda: deque(maxlen=14))
            gain_sum: float = 0.0
            loss_sum: float = 0.0
            base_top: float = 0.0           # 缃戞牸椤堕儴 (涓灑)
            base_bottom: float = 0.0        # 缃戞牸搴曢儴 (涓灑)
            active_layers_mode: int = 5     # 5 鎴?7
            grid_lines: List[float] = field(default_factory=list)
            
            # RSI 鍔ㄦ€侀槇鍊?
            dynamic_rsi_buy: float = 25.0
            dynamic_rsi_sell: float = 75.0
            
            # 鐔旀柇瑙傚療鐘舵€?
            is_observing: bool = False
            observe_start_time: Optional[datetime] = None
            observe_trigger_price: float = 0.0
            
            # 璁板綍涓婃閲嶇畻鏃堕棿
            last_rebalance_time: Optional[datetime] = None
            
            # 璁板綍涓婃浠锋牸 (鐢ㄤ簬 Crossing Logic)
            last_marker_price: float = 0.0
            
            # 璁板綍灞傜骇鎸佷粨閿佸畾 (闃插鍚?
            layer_holdings: Dict[int, bool] = field(default_factory=dict)

        self.state = StrategyState()
        
        # 绛栫暐鍙皟鍙傛暟
        self.rsi_period = params.get('rsi_period', 14)
        self.observe_hours = params.get('observe_hours', 2.0)
        self.max_position_pct = params.get('max_position_pct', 0.8)
        self.lookback_hours = params.get('lookback_hours', 4.0) # 鏂板锛氭敮鎸?2h/4h/6h 鍥炵湅
        self.unlock_mode = params.get('unlock_mode', 'fifo')    # 鏂板锛?fifo' 鎴?'lifo'
        self.range_multiplier = params.get('range_multiplier', 1.0) # 鏂板锛氱綉鏍煎搴︾缉鏀剧郴鏁?
        self.verbose = params.get('verbose', False)            # 鏂板锛氭帶鍒舵棩蹇楄緭鍑?
        
        # 璧勯噾绠＄悊鍙傛暟
        self.initial_capital = params.get('initial_capital', 10000.0)
        self.initialize()
        
        # 鍐崇瓥杩借釜 (Trace Log): {timestamp_ms: [msg1, msg2, ...]}
        self.decision_trace = {}

    def initialize(self):
        """[鏍囧噯鎺ュ彛] 鍒濆鍖?閲嶇疆绛栫暐鐘舵€?""
        super().initialize()
        self._data_1m.clear()
        self.decision_trace.clear()
        
        # 閲嶆柊鍒濆鍖?StrategyState (閬垮厤鏃х綉鏍煎拰鎸佷粨骞叉壈)
        @dataclass
        class StrategyState:
            current_rsi: float = 50.0
            volatility: float = 0.0
            avg_gain: float = 0.0          # 宸插簾寮冿紝淇濈暀鍏煎鎬?
            avg_loss: float = 0.0          # 宸插簾寮冿紝淇濈暀鍏煎鎬?
            gain_dq: deque = field(default_factory=lambda: deque(maxlen=14))
            loss_dq: deque = field(default_factory=lambda: deque(maxlen=14))
            gain_sum: float = 0.0
            loss_sum: float = 0.0
            base_top: float = 0.0           # 缃戞牸椤堕儴 (涓灑)
            base_bottom: float = 0.0        # 缃戞牸搴曢儴 (涓灑)
            active_layers_mode: int = 5     # 5 鎴?7
            grid_lines: List[float] = field(default_factory=list)
            
            # RSI 鍔ㄦ€侀槇鍊?
            dynamic_rsi_buy: float = 25.0
            dynamic_rsi_sell: float = 75.0
            
            # 鐔旀柇瑙傚療鐘舵€?
            is_observing: bool = False
            observe_start_time: Optional[datetime] = None
            observe_trigger_price: float = 0.0
            
            # 璁板綍涓婃閲嶇畻鏃堕棿
            last_rebalance_time: Optional[datetime] = None
            
            # 璁板綍涓婃浠锋牸 (鐢ㄤ簬 Crossing Logic)
            last_marker_price: float = 0.0
            
            # 璁板綍灞傜骇鎸佷粨閿佸畾 (闃插鍚?
            layer_holdings: Dict[int, bool] = field(default_factory=dict)
            
        self.state = StrategyState()
        if self.verbose:
            print(f"[V8.5] 绛栫暐鍐呴儴鐘舵€佸凡閲嶇疆")

    def on_data(self, data: MarketData, context: Optional[StrategyContext]) -> List[Signal]:
        # 1. 鏁版嵁瀵归綈涓庣紦瀛?
        self._data_1m.append(data)
        
        # 2. 璁＄畻鎸囨爣 (鍗充娇鍦ㄩ鐑湡涔熻绠楋紝浠ヤ究 Dashboard 鏈夋暟鎹?
        self._calculate_indicators()
        
        # 浠呭湪鏁村垎鏃舵墦涓€涓績璺?trace
        if data.timestamp.second == 0 and data.timestamp.minute % 5 == 0:
            ts_ms = int(data.timestamp.timestamp() * 1000)
            self._trace(ts_ms, f"Tick: {data.close:.2f} | RSI: {self.state.current_rsi:.1f}")
        
        # 棰勭儹妫€鏌?(240min)
        if len(self._data_1m) < 240:
            if self.verbose and len(self._data_1m) % 60 == 0:
                print(f"[V8.5] 鏁版嵁棰勭儹涓? {len(self._data_1m)}/240")
            return []

        # 璁板綍鍩虹鐘舵€?Trace (鍗充娇娌℃湁浠讳綍淇″彿)
        ts_ms = int(data.timestamp.timestamp() * 1000)
        self._trace(ts_ms, f"Price: {data.close:.1f} | RSI: {self.state.current_rsi:.1f}")

        # 3. 缃戞牸閲嶇畻閫昏緫 (姣?6 灏忔椂鎴栧垵娆℃垨鐔旀柇鎭㈠)
        self._rebalance_grid_logic(data, context)

        if not self.state.grid_lines:
            return []

        # 4. 鐔旀柇瑙傚療鏈熷鐞?
        if self.state.is_observing:
            return self._handle_observation(data, context)

        # 5. 浜ゆ槗閫昏緫
        if context:
            return self._generate_signals(data, context)
            
        return []

    def _calculate_indicators(self):
        if not self._data_1m:
            return
            
        data = self._data_1m[-1]
        if len(self._data_1m) < 2:
            return
            
        prev_data = self._data_1m[-2]
        delta = data.close - prev_data.close
        gain = max(0, delta)
        loss = max(0, -delta)
        
        # 鏇存柊闃熷垪闀垮害锛堝鏋滃弬鏁版敼鍙橈級
        if self.state.gain_dq.maxlen != self.rsi_period:
            self.state.gain_dq = deque(list(self.state.gain_dq), maxlen=self.rsi_period)
            self.state.loss_dq = deque(list(self.state.loss_dq), maxlen=self.rsi_period)

        # 澧為噺鏇存柊 SMA
        if len(self.state.gain_dq) == self.rsi_period:
            self.state.gain_sum -= self.state.gain_dq.popleft()
            self.state.loss_sum -= self.state.loss_dq.popleft()
        
        self.state.gain_dq.append(gain)
        self.state.loss_dq.append(loss)
        self.state.gain_sum += gain
        self.state.loss_sum += loss
        
        # 璁＄畻 RSI (SMA Based - Cutler's RSI)
        count = len(self.state.gain_dq)
        if count == 0:
            self.state.current_rsi = 50.0
        else:
            rsi_g = self.state.gain_sum / count
            rsi_l = self.state.loss_sum / count
            
            if rsi_l < 1e-9:
                self.state.current_rsi = 100.0
            else:
                rs = rsi_g / rsi_l
                self.state.current_rsi = 100.0 - (100.0 / (1.0 + rs))

    def _rebalance_grid_logic(self, data: MarketData, context: Optional[StrategyContext] = None):
        now = data.timestamp
        # 姣?6 灏忔椂閲嶇畻涓€娆★紝鎴栬€呭垵娆¤繍琛?
        if (self.state.last_rebalance_time is None or 
            (now - self.state.last_rebalance_time).total_seconds() >= 6 * 3600):
            self._calculate_5_take_3_grid(data, context)
            self.state.last_rebalance_time = now

    def _calculate_5_take_3_grid(self, data: MarketData, context: Optional[StrategyContext] = None):
        """鏍稿績: 5鍙?鎶楁彃閽堢畻娉?""
        lookback_mins = int(self.lookback_hours * 60)
        history = list(self._data_1m)[-lookback_mins:]
        segment_size = len(history) // 5
        
        h_points = []
        l_points = []
        
        for i in range(5):
            seg = history[i*segment_size : (i+1)*segment_size]
            h_points.append(max(d.high for d in seg))
            l_points.append(min(d.low for d in seg))
            
        h_points.sort()
        l_points.sort()
        
        # 鏍稿績锛氬幓鎺?1 涓渶楂橈紝鍘绘帀 1 涓渶浣庯紝鍙栦腑闂?3 涓潎鍊?
        h_trimmed = h_points[1:4]
        l_trimmed = l_points[1:4]
        
        self.state.base_top = sum(h_trimmed) / 3
        self.state.base_bottom = sum(l_trimmed) / 3
        
        # 娉㈠姩鐜囧垽瀹?
        vol = (self.state.base_top - self.state.base_bottom) / self.state.base_bottom
        self.state.volatility = vol
        
        # 5灞?vs 7灞?鍒ゅ畾 (>1.2% 涓?7 灞?
        if vol > 0.012:
            self.state.active_layers_mode = 7
        else:
            self.state.active_layers_mode = 5
            
        # 鍔ㄦ€?RSI 闃堝€?
        if vol > 0.02: # 楂樻尝鍔?
            self.state.dynamic_rsi_buy, self.state.dynamic_rsi_sell = 20, 80
        elif vol < 0.012: # 浣庢尝鍔?
            self.state.dynamic_rsi_buy, self.state.dynamic_rsi_sell = 30, 70
        else: # 姝ｅ父
            self.state.dynamic_rsi_buy, self.state.dynamic_rsi_sell = 25, 75
            
        # 鏋勫缓瀹屾暣鍒诲害 (鍖呭惈 2 灞傝櫄鎷?
        self._build_grid_lines()
        
        # 鏍稿績浼樺寲锛氭寔浠撶户鎵?(Position Inheritance)
        # 涓嶅啀 simple clear锛岃€屾槸鏍规嵁褰撳墠鎸佷粨鏁伴噺鍙嶅悜鎺ㄧ畻閿佸畾灞傜骇
        self.state.layer_holdings.clear() 
        if context:
            pos = context.positions.get(self.symbol)
            if pos and pos.size > 0:
                current_capital = context.total_value
                unit_val = (current_capital * self.max_position_pct) / self.state.active_layers_mode
                # 璁＄畻澶х害鎸佹湁澶氬皯浠?(灞?
                pos_in_layers = round((pos.size * data.close) / unit_val)
                if pos_in_layers > 0:
                    # 鏍稿績淇 3锛氭寔浠撶户鎵块伩寮€ L0 绂佸尯
                    v_lower_count = 2
                    n = self.state.active_layers_mode
                    l0_idx = v_lower_count + (n // 2)
                    locked_count = 0
                    current_idx = v_lower_count # 浠庢渶搴曞眰鐨勫疄浣撳眰寮€濮?

                    while locked_count < pos_in_layers and current_idx < len(self.state.grid_lines) - 1:
                        # 蹇呴』璺宠繃 L0 绂佸尯鍜屽崠鍑哄眰 (鍙攣涔板叆灞傦紝鍗崇储寮曞皬浜?l0_idx)
                        if current_idx < l0_idx:
                            self.state.layer_holdings[current_idx] = True
                            locked_count += 1
                        current_idx += 1
                    if self.verbose:
                        print(f"[V8.5 INHERIT] 妫€娴嬪埌鎸佷粨 {pos.size:.4f} BTC锛岃嚜鍔ㄧ户鎵块攣瀹氭柊缃戞牸搴曢儴鐨?{locked_count} 涓疄浣撲拱鍏ュ眰")
        
        # 澧炲己鏃ュ織
        if self.verbose:
            print(f"\n>>>> [V8.5 GRID RECALC] {data.timestamp} <<<<")
            print(f"| 鍘熷楂樼偣: {[f'{x:.1f}' for x in h_points]} -> 淇濈暀: {[f'{x:.1f}' for x in h_trimmed]}")
            print(f"| 鍘熷浣庣偣: {[f'{x:.1f}' for x in l_points]} -> 淇濈暀: {[f'{x:.1f}' for x in l_trimmed]}")
            print(f"| 涓灑椤堕儴: {self.state.base_top:.2f} | 搴曢儴: {self.state.base_bottom:.2f}")
            print(f"| 娉㈠姩鐜? {vol*100:.2f}% -> 妯″紡: {self.state.active_layers_mode}灞?| RSI: {self.state.dynamic_rsi_buy}/{self.state.dynamic_rsi_sell}")
            print(f"| 鏍稿績缃戞牸鑼冨洿: {self.state.grid_lines[0]:.1f} - {self.state.grid_lines[-1]:.1f}\n")

    def _build_grid_lines(self):
        """鏋勫缓鍖呭惈 2 灞傝櫄鎷熷眰鐨勪环鏍煎埢搴?""
        n = self.state.active_layers_mode
        h = ((self.state.base_top - self.state.base_bottom) / n) * self.range_multiplier
        
        lines = []
        # 涓嬫柟 2 灞傝櫄鎷? V-2, V-1
        lines.append(self.state.base_bottom - 2 * h)
        lines.append(self.state.base_bottom - 1 * h)
        
        # 瀹炰綋灞? 鍖呭惈 base_bottom (鍏?n+1 鏉＄嚎锛屽洿鎴?n 涓尯闂?
        for i in range(n + 1):
            lines.append(self.state.base_bottom + i * h)
            
        # 涓婃柟 2 灞傝櫄鎷? V+1, V+2
        lines.append(self.state.base_top + 1 * h)
        lines.append(self.state.base_top + 2 * h)
            
        self.state.grid_lines = lines

    def _handle_observation(self, data: MarketData, context: Optional[StrategyContext] = None) -> List[Signal]:
        elapsed = (data.timestamp - self.state.observe_start_time).total_seconds()
        
        # 鏍稿績淇 4锛氱啍鏂В闄ゆ潯浠跺榻?(鍖呭惈铏氭嫙灞?
        ts_ms = int(data.timestamp.timestamp() * 1000)
        if self.state.grid_lines[0] <= data.close <= self.state.grid_lines[-1]:
            msg = f"鐔旀柇瑙ｉ櫎: 浠锋牸 {data.close:.2f} 鍥炲綊鍖洪棿 (鑰楁椂 {elapsed/60:.1f}min)"
            if self.verbose:
                print(f"[V8.5] {msg}")
            self._trace(ts_ms, msg)
            self.state.is_observing = False
            return []
        else:
            # 璁板綍鐔旀柇涓殑鍋忕鐘舵€?
            grid_center = (self.state.grid_lines[0] + self.state.grid_lines[-1]) / 2
            deviation = (data.close - grid_center) / grid_center * 100
            self._trace(ts_ms, f"鐔旀柇瑙傚療涓? 浠锋牸 {data.close:.1f} 鍋忕涓灑 {deviation:+.2f}%")
            
        # 婊?N 灏忔椂鏈洖褰?
        if elapsed >= self.observe_hours * 3600:
            if self.verbose:
                print(f"[V8.5] 鐔旀柇瓒呮椂 ({self.observe_hours}h): 鍚姩缃戞牸閲嶇畻 (淇濈暀鎸佷粨)")
            self.state.is_observing = False
            # 鐔旀柇閲嶇畻涔熼渶瑕?context 鏉ュ鐞嗘寔浠撶户鎵?
            self._calculate_5_take_3_grid(data, context) 
            self.state.last_rebalance_time = data.timestamp
            
        return []

    def _generate_signals(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        price = data.close
        lines = self.state.grid_lines
        
        # 妫€鏌ユ槸鍚︾獊鐮存暣缃戞牸杈圭紭 (杩涘叆瑙傚療鏈?
        if price < lines[0] or price > lines[-1]:
            ts_ms = int(data.timestamp.timestamp() * 1000)
            msg = f"瑙﹀彂鐔旀柇瑙傚療: 浠锋牸 {price:.2f} 婧㈠嚭杈圭晫 [{lines[0]:.1f}, {lines[-1]:.1f}]"
            if self.verbose:
                print(f"[V8.5] {msg}")
            self._trace(ts_ms, msg)
            self.state.is_observing = True
            self.state.observe_start_time = data.timestamp
            self.state.observe_trigger_price = price
            return []

        # 瀹氫綅褰撳墠鎵€鍦ㄥ眰绾?
        layer_idx = -1
        for i in range(len(lines) - 1):
            if lines[i] <= price <= lines[i+1]:
                layer_idx = i
                break
        
        if layer_idx == -1: return []
        
        # 鏄犲皠灞傜骇灞炴€?
        # lines 缁撴瀯: [V-2, V-1, L(-n), ..., L(0), ..., L(n), V1, V2]
        # 鎬诲叡鏈?n + 4 灞傚尯闂?
        n = self.state.active_layers_mode
        v_lower_count = 2
        
        # L0 绱㈠紩璁＄畻锛?
        # lines 缁撴瀯 (涓句緥 n=5): [0:V-2, 1:V-1, 2:B, 3:L1, 4:L2, 5:L3, 6:L4, 7:T, 8:V+1, 9:V+2]
        # 鏈?9 涓尯闂淬€備腑闂村尯闂?(L0) 搴旇鏄 [4, 5] 鏉＄嚎鏋勬垚鐨勫尯闂达紝绱㈠紩涓?4銆?
        # 鍏紡: v_lower_count + (n // 2) 鍒氬ソ鎸囧悜 index=2 + 2 = 4 (鍗冲尯闂?[lines[4], lines[5]])
        l0_idx = v_lower_count + (n // 2)
        rel_idx = layer_idx - l0_idx
        
        # 1. L0 缂撳啿绂佸尯
        ts_ms = int(data.timestamp.timestamp() * 1000)
        if rel_idx == 0:
            self._trace(ts_ms, f"浣嶇疆: L0 缂撳啿绂佸尯 ({price:.1f}) | 瑙傛湜涓?)
            return []
            
        # 2. 鍒ゆ柇瀹炰綋/铏氭嫙
        is_virtual_buy = layer_idx < v_lower_count
        is_virtual_sell = layer_idx >= v_lower_count + n
        
        layer_name = f"L{rel_idx}"
        if is_virtual_buy or is_virtual_sell:
            layer_name = f"铏氭嫙灞?{layer_name}"
        else:
            layer_name = f"瀹炰綋灞?{layer_name}"
            
        self._trace(ts_ms, f"浣嶇疆: {layer_name} | Price: {price:.1f}")
        
        # 3. 璁＄畻鍖洪棿娣卞害 (0-100%)
        bounds = (lines[layer_idx], lines[layer_idx+1])
        depth = (price - bounds[0]) / (bounds[1] - bounds[0])
        
        # 4. 鍒ゅ畾涔板崠
        signals = []
        pos = context.positions.get(self.symbol)
        pos_size = float(pos.size) if pos else 0.0
        
        # 鑾峰彇涓婃浠锋牸
        last_price = self.state.last_marker_price if self.state.last_marker_price > 0 else price
        self.state.last_marker_price = price # 鏇存柊璁板綍
        
        # 瑙﹀彂涓綅绾?(姣忎竴灞傜殑 50% 澶?
        trigger_line = bounds[0] + (bounds[1] - bounds[0]) * 0.5
        
        # 涔板叆閫昏緫 (rel_idx < 0): 蹇呴』鏄敱涓婂悜涓嬬┛杩囪Е鍙戠嚎
        if rel_idx < 0:
            # Crossing Logic: 涓婃浠锋牸鍦ㄨЕ鍙戠嚎涓婃柟锛屼笖褰撳墠浠锋牸鍦ㄨЕ鍙戠嚎涓嬫柟 (鎴栫瓑浜?
            is_crossing_down = (last_price > trigger_line and price <= trigger_line)
            
            if is_crossing_down:
                # 鍙湁褰撹灞傛病鏈夐攣瀹氭椂鎵嶄拱鍏?(闃插鍚?
                if layer_idx in self.state.layer_holdings:
                    self._trace(ts_ms, f"璺宠繃涔板叆: {layer_name} 宸茶閿佸畾 (闃插鍚镐繚鎶?")
                else:
                    if is_virtual_buy and self.state.current_rsi > self.state.dynamic_rsi_buy:
                        self._trace(ts_ms, f"璺宠繃涔板叆: {layer_name} RSI({self.state.current_rsi:.1f}) > 闃堝€?{self.state.dynamic_rsi_buy})")
                        return []
                        
                    # 鏍稿績淇锛?/n 鍔ㄦ€佸垎浠擄紙鍩轰簬褰撳墠鍙敤 USDT 璧勯噾锛?
                    # 鐢ㄦ埛瑕佹眰锛氫拱鍏ヤ粨浣嶉渶瑕佹槸褰撳墠鎵€鎷ユ湁鐨勮祫閲慤SDT鐨?/n
                    buy_val = context.cash / n
                    self.state.layer_holdings[layer_idx] = True
                    msg = f"鎴愪氦涔板叆: L({rel_idx}) 浠锋牸 {price:.1f} 閲?{buy_val:.1f} USDT"
                    if self.verbose:
                        print(f"[V8.5 TRADE] {msg} | RSI: {self.state.current_rsi:.1f}")
                    self._trace(ts_ms, msg)
                    signals.append(Signal(
                        timestamp=data.timestamp, symbol=self.symbol, side=Side.BUY,
                        size=buy_val, meta={
                            'size_in_quote': True,
                            "rsi": self.state.current_rsi,
                            "volatility": self.state.volatility,
                            "layer_idx": layer_idx,
                            "rel_idx": rel_idx,
                            "active_layers": self.state.active_layers_mode,
                            "holdings_count": len(self.state.layer_holdings),
                            "snapshot_pos": pos_size
                        },
                        reason=f"L({rel_idx}) Crossing Down {trigger_line:.2f}"
                    ))
            else:
                if price <= trigger_line:
                    self._trace(ts_ms, f"绛夊緟涔板叆: 浠锋牸宸插湪瑙﹀彂绾?({trigger_line:.1f}) 涓嬫柟锛岀瓑寰呭弽寮圭┛瓒婃垨涓嬩釜鍛ㄦ湡")
                else:
                    dist = price - trigger_line
                    self._trace(ts_ms, f"绛夊緟涔板叆: 璺?{layer_name} 瑙﹀彂绾胯繕宸?{dist:.1f} USDT")
                    
        # 鍗栧嚭閫昏緫 (rel_idx > 0): 蹇呴』鏄敱涓嬪悜涓婄┛杩囪Е鍙戠嚎
        elif rel_idx > 0:
            is_crossing_up = (last_price < trigger_line and price >= trigger_line)
            
            if is_crossing_up:
                if pos_size <= 0:
                    self._trace(ts_ms, f"璺宠繃鍗栧嚭: {layer_name} 瑙﹀彂锛屼絾褰撳墠鏃犳寔浠?)
                else:
                    # 鏍稿績淇 5锛氬潎浠蜂繚鎶ゆ満鍒?(Cost Basis Protection)
                    avg_cost = float(pos.avg_price) if hasattr(pos, 'avg_price') else 0.0
                    # 濡傛灉褰撳墠浠锋牸浣庝簬鎸佷粨鍧囦环锛屾嫆缁濆崠鍑猴紙闃叉缃戞牸涓嬬Щ瀵艰嚧鐨勫壊鑲夛級
                    if avg_cost > 0 and price < avg_cost:
                        if self.verbose:
                            print(f"[V8.5 PROTECT] 瑙﹀彂鍗栧嚭淇″彿浣嗕环鏍?{price:.2f})浣庝簬鍧囦环({avg_cost:.2f})锛屾嫆缁濆壊鑲夈€?)
                        self._trace(ts_ms, f"淇濇姢璺宠繃: 浠锋牸({price:.2f}) < 鍧囦环({avg_cost:.2f})")
                        return []

                    if is_virtual_sell and self.state.current_rsi < self.state.dynamic_rsi_sell:
                        self._trace(ts_ms, f"璺宠繃鍗栧嚭: {layer_name} RSI({self.state.current_rsi:.1f}) < 闃堝€?{self.state.dynamic_rsi_sell})")
                        return []
                    
                    # 鏍稿績淇 1锛?/n 鍗栧嚭绠楁硶浼樺寲 (澶勭悊鑺濊鐨勪箤榫?
                    current_capital = context.total_value
                    target_sell_val = (current_capital * self.max_position_pct) / n
                    sell_qty = target_sell_val / price

                    # 鍏滃簳涓庣簿搴︿繚鎶わ細闃叉鍗栧嚭閲忚秴杩囧疄闄呮寔浠擄紝鎴栧鐞嗗熬浠?
                    if sell_qty > pos_size or (pos_size - sell_qty) * price < 10.0:
                        sell_qty = pos_size  # 濡傛灉鍓╀綑灏句粨浠峰€煎皬浜?10 U锛岀洿鎺ユ竻浠?

                # 鏈€灏忎笅鍗曢搴︽嫤鎴?(鍋囪浜ゆ槗鎵€瑕佹眰鍗曠瑪鑷冲皯 5 USDT)
                if sell_qty * price < 5.0:
                    self._trace(ts_ms, f"璺宠繃鍗栧嚭: 涓嬪崟閲戦 {sell_qty*price:.1f} 杩囧皬")
                    return [] 
                
                # 鏍稿績淇 2锛氳В閿侀€昏緫浼樺寲 (鏀寔 FIFO/LIFO)
                if self.state.layer_holdings:
                    # 瑙ｉ攣閫昏緫
                    if self.unlock_mode == 'lifo':
                        # LIFO: 瑙ｉ攣鏈€杩戜拱鍏ョ殑锛堥€氬父鏄环鏍兼渶浣庣殑灞傜骇锛?
                        target_key = max(self.state.layer_holdings.keys()) # 娉ㄦ剰锛歀IFO搴旇瑙ｆ渶楂榢ey(鏈€娣变拱鍏?
                        mode_label = "LIFO"
                    else:
                        # FIFO (Default): 瑙ｉ攣鏈€鏃╀拱鍏ョ殑锛堥€氬父鏄环鏍兼渶楂樼殑灞傜骇锛?
                        target_key = min(self.state.layer_holdings.keys())
                        mode_label = "FIFO"
                        
                    self.state.layer_holdings.pop(target_key)
                    if self.verbose:
                        print(f"[V8.5 DEBUG] 浣跨敤 {mode_label} 鎴愬姛瑙ｉ攣灞傜骇 L({target_key - l0_idx})")
                
                msg = f"鎴愪氦鍗栧嚭: L({rel_idx}) 浠锋牸 {price:.1f} 閲?{sell_qty:.4f}"
                if self.verbose:
                    print(f"[V8.5 TRADE] {msg} | RSI: {self.state.current_rsi:.1f}")
                self._trace(ts_ms, msg)
                
                signals.append(Signal(
                    timestamp=data.timestamp, symbol=self.symbol, side=Side.SELL,
                    size=sell_qty, reason=f"L({rel_idx}) Crossing Up {trigger_line:.2f}",
                    meta={
                        "rsi": self.state.current_rsi,
                        "volatility": self.state.volatility,
                        "layer_idx": layer_idx,
                        "rel_idx": rel_idx,
                        "active_layers": self.state.active_layers_mode,
                        "holdings_count": len(self.state.layer_holdings),
                        "snapshot_pos": pos_size,
                        "avg_cost": float(pos.avg_price) if hasattr(pos, 'avg_price') else 0.0
                    }
                ))
            else:
                if price >= trigger_line:
                    self._trace(ts_ms, f"绛夊緟鍗栧嚭: 浠锋牸宸插湪瑙﹀彂绾?({trigger_line:.1f}) 涓婃柟锛岀瓑寰呭洖璋冪┛瓒婃垨涓嬩釜鍛ㄦ湡")
                else:
                    dist = trigger_line - price
                    self._trace(ts_ms, f"绛夊緟鍗栧嚭: 璺?{layer_name} 瑙﹀彂绾胯繕宸?{dist:.1f} USDT")

        return signals

    def _trace(self, ts_ms: int, msg: str):
        """璁板綍鍐崇瓥杩借釜鏃ュ織"""
        if ts_ms not in self.decision_trace:
            self.decision_trace[ts_ms] = []
        self.decision_trace[ts_ms].append(msg)

    def get_status(self, context: Optional[StrategyContext] = None) -> Dict[str, Any]:
        # 鍒ゅ畾褰撳墠淇″彿鏂囨湰鍜岄鑹?
        signal_text = "绛夊緟淇″彿"
        signal_color = "neutral"
        if self.state.is_observing:
            signal_text = "鐔旀柇瑙傚療涓?
            signal_color = "warning"
        
        status = {
            'name': self.name,
            'current_rsi': round(self.state.current_rsi, 2),
            'rsi_oversold': self.state.dynamic_rsi_buy,
            'rsi_overbought': self.state.dynamic_rsi_sell,
            'volatility': self.state.volatility,
            'atrVal': self.state.volatility * 100, 
            'signal_text': signal_text,
            'signal_color': signal_color,
            'signal_strength_val': f"{self.state.volatility*100:.2f}%",
            'marketRegime': f"{self.state.active_layers_mode} 灞傛ā寮?,
            'vol_trend': "涓婂崌" if self.state.volatility > 0.01 else "骞崇ǔ", 
            'grid_lower': self.state.base_bottom,
            'grid_upper': self.state.base_top,
            'layers_mode': self.state.active_layers_mode,
            'state_label': "瑙傚療鏈? if self.state.is_observing else "杩愯涓?,
            'layer_holdings': list(self.state.layer_holdings.keys()),
            'position_count': len(self.state.layer_holdings),
            'grid_lines': self.state.grid_lines,
            'decision_trace_count': len(self.decision_trace)
        }

        if context and self.symbol in context.positions:
            pos = context.positions[self.symbol]
            status.update({
                'position_size': float(pos.size),
                'position_avg_price': float(pos.avg_price) if hasattr(pos, 'avg_price') else 0.0,
                'position_unrealized_pnl': float(pos.unrealized_pnl)
            })
        
        # 琛ュ厖鍙傛暟淇℃伅渚?Dashboard 鏄剧ず
        status['params'] = {
            'symbol': self.symbol,
            'rsi_period': self.rsi_period,
            'lookback_hours': self.lookback_hours,
            'observe_hours': self.observe_hours,
            'max_position_pct': self.max_position_pct,
            'unlock_mode': self.unlock_mode,
            'range_multiplier': self.range_multiplier,
            'l0_idx': 2 + (self.state.active_layers_mode // 2)
        }
        return status
