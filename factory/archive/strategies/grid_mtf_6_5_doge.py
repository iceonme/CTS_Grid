import os
import json
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from collections import deque

from console.core import (
    MarketData, Signal, Side, OrderType, 
    FillEvent, Position, StrategyContext
)
from cartridges.strategies.base import BaseStrategy

class GridStrategyV65B(BaseStrategy):
    """
    V6.5B 鍔ㄦ€佺綉鏍间氦鏄撶瓥鐣?(DOGE-PRO)
    
    鍩轰簬 V6.5A 鏋舵瀯锛岄拡瀵?DOGE 绛夐珮娉㈠姩甯佺浼樺寲锛?
    - 鏀惧 RSI 闃堝€硷紝鎻愰珮鍙備笌搴?
    - 缂╃煭鍐峰嵈鏃堕棿锛屾崟鎹夊揩閫熸満浼?
    - 鍑忓皯鏈€澶ф寔浠撳眰鏁帮紝鎺у埗鏋佺椋庨櫓
    """

    def __init__(self, name: str = "Grid_V65B_DOGE", **params):
        super().__init__(name, **params)
        self.params_path = params.get('config_path', 'config/grid_v65b_doge_runtime.json')
        # 鑷姩鎺ㄥ meta 璺緞 (渚嬪 runtime.json -> meta.json)
        self.meta_path = self.params_path.replace('runtime.json', 'meta.json')
        self.symbol = params.get('symbol', 'DOGE-USDT')
        self.param_metadata = {}
        self._load_params()

        # 鏁版嵁缂撳瓨
        self._data_5m = deque(maxlen=400)   # 5m K绾跨紦瀛?(绾?3灏忔椂锛岀‘淇濊兘鐪嬪埌瀹屾暣鏃ョ粨鏋?
        self._data_15m = deque(maxlen=200)  # 15m 閲嶉噰鏍风紦瀛?
        self._last_15m_ts: Optional[datetime] = None

        # 绛栫暐鍐呴儴鐘舵€?
        @dataclass
        class StrategyState:
            current_rsi: float = 50.0
            macd: float = 0.0
            macdsignal: float = 0.0
            macdhist: float = 0.0
            macd_prev: float = 0.0
            macdsignal_prev: float = 0.0
            macdhist_prev: float = 0.0
            atr: float = 0.0
            atr_ma: float = 0.0
            
            grid_lower: float = 0.0
            grid_upper: float = 0.0
            grid_lines: List[float] = field(default_factory=list)
            
            is_halted: bool = False
            halt_reason: str = ""
            resume_time: Optional[datetime] = None
            pivots_high: List[Dict[str, Any]] = field(default_factory=list)
            pivots_low: List[Dict[str, Any]] = field(default_factory=list)
            
            last_grid_reset: Optional[datetime] = None
            last_buy_time: Optional[datetime] = None
            last_buy_price: float = 0.0

        self.state = StrategyState()

    def _load_params(self):
        """鍔犺浇杩愯鍙傛暟涓庡厓鏁版嵁璇存槑"""
        # 1. 鍔犺浇杩愯鍙傛暟
        if os.path.exists(self.params_path):
            try:
                with open(self.params_path, 'r', encoding='utf-8') as f:
                    self.params.update(json.load(f))
            except Exception as e:
                print(f"[V6.5B] 鍔犺浇鍙傛暟澶辫触: {e}")
        
        # 2. 鍔犺浇鍏冩暟鎹?(鐢ㄤ簬 Dashboard 璇存槑闈㈡澘)
        if os.path.exists(self.meta_path):
            try:
                with open(self.meta_path, 'r', encoding='utf-8') as f:
                    self.param_metadata = json.load(f)
            except Exception as e:
                print(f"[V6.5B] 鍔犺浇鍏冩暟鎹け璐? {e}")

    def initialize(self):
        super().initialize()
        print(f"[V6.5B] {self.name} 鍒濆鍖栧畬鎴?)

    def on_data(self, data: MarketData, context: Optional[StrategyContext]) -> List[Signal]:
        if not self._initialized:
            self.initialize()

        # 1. 鏇存柊鏁版嵁涓庨噸閲囨牱 (5m -> 15m)
        self._update_data(data)
        
        # 鎸囨爣璁＄畻闇€瑕佽冻澶熸暟鎹?
        if len(self._data_5m) < 30 or len(self._data_15m) < 30:
            return []

        # 2. 璁＄畻鎸囨爣
        self._calculate_indicators()

        # 3. 鐔旀柇妫€娴?(榛戝ぉ楣?
        if self._check_halt(data):
            return []

        # 4. 缃戞牸绠＄悊 (杈圭晫璁＄畻涓庨噸缃?
        self._manage_grid(data)

        # 5. 淇″彿鐢熸垚
        if context:
            return self._generate_signals(data, context)
        return []

    def _update_data(self, data: MarketData):
        """鏇存柊 5m 鏁版嵁骞舵墽琛?15m 閲嶉噰鏍?
        
        鍏抽敭锛歄KX 鏁版嵁娴佹瘡2绉掓帹閫佷竴娆″悓涓€鏍?鍒嗛挓K绾跨殑鏈€鏂扮姸鎬侊紝
        蹇呴』灏嗗悓涓€5鍒嗛挓鍛ㄦ湡鐨勫娆℃帹閫佸悎骞朵负涓€鏉¤褰曪紝
        鍚﹀垯 _data_5m 閲屽瓨鐨勬槸2绉掑揩鐓ц€岄潪5鍒嗛挓K绾匡紝鎵€鏈夋寚鏍囪绠楅兘浼氶敊璇€?
        """
        ts = data.timestamp
        # 鎸?鍒嗛挓鍙栨暣浣滀负褰撳墠K绾跨殑鏍囪瘑鏃堕棿
        bar_ts = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        
        if self._data_5m and self._data_5m[-1].timestamp.replace(
                minute=(self._data_5m[-1].timestamp.minute // 5) * 5, 
                second=0, microsecond=0) == bar_ts:
            # 鍚屼竴鏍?鍒嗛挓K绾匡細鏇存柊鏈€鍚庝竴鏉＄殑 high/low/close/volume
            last = self._data_5m[-1]
            updated = MarketData(
                timestamp=data.timestamp,  # 鐢ㄦ渶鏂版椂闂存埑
                symbol=data.symbol,
                open=last.open,            # open 淇濇寔涓嶅彉锛堣K绾跨涓€娆＄殑寮€鐩樹环锛?
                high=max(last.high, data.high),
                low=min(last.low, data.low),
                close=data.close,          # close 鐢ㄦ渶鏂颁环
                volume=data.volume         # OKX姣忔鎺ㄩ€佺殑宸茬粡鏄繖鏍?mK绾跨殑绱閲忥紝鏁呯洿鎺ヨ鐩?
            )
            self._data_5m[-1] = updated
        else:
            # 鏂扮殑5鍒嗛挓鍛ㄦ湡锛氳拷鍔犳柊璁板綍
            self._data_5m.append(data)
        
        # 15m 閲嶉噰鏍烽€昏緫 (浠?0, 15, 30, 45 鍒嗛挓涓虹晫)
        period_ts = ts.replace(minute=(ts.minute // 15) * 15, second=0, microsecond=0)
        
        if self._last_15m_ts is None or period_ts > self._last_15m_ts:
            # 鏂扮殑 15m 鍛ㄦ湡寮€濮?
            self._last_15m_ts = period_ts
            self._data_15m.append({
                'timestamp': period_ts,
                'open': data.open, 'high': data.high, 
                'low': data.low, 'close': data.close, 
                'volume': data.volume
            })
        else:
            # 鏇存柊褰撳墠鐨?15m 鍛ㄦ湡
            bar = self._data_15m[-1]
            bar['high'] = max(bar['high'], data.high)
            bar['low'] = min(bar['low'], data.low)
            bar['close'] = data.close
            
            # 璁＄畻 15m 鍛ㄦ湡鍐呯殑绮剧‘ volume锛?
            vol_sum = 0
            for i in range(len(self._data_5m) - 1, -1, -1):
                d = self._data_5m[i]
                d_period_ts = d.timestamp.replace(minute=(d.timestamp.minute // 15) * 15, second=0, microsecond=0)
                if d_period_ts < period_ts:
                    break
                if d_period_ts == period_ts:
                    vol_sum += d.volume
            bar['volume'] = vol_sum


    def _calculate_indicators(self):
        """璁＄畻 RSI(5m), MACD(15m), ATR(5m)"""
        # 5m RSI
        closes_5m = pd.Series([d.close for d in self._data_5m])
        self.state.current_rsi = self._rsi(closes_5m, self.params.get('rsi_period', 14))
        
        # 5m ATR
        highs = pd.Series([d.high for d in self._data_5m])
        lows = pd.Series([d.low for d in self._data_5m])
        closes = pd.Series([d.close for d in self._data_5m])
        atr_val = self._atr(highs, lows, closes, self.params.get('atr_period', 14))
        self.state.atr = atr_val
        # 缁熻杩囧幓 6 灏忔椂鐨?ATR 鍧囧€?(72 鏍?5m)
        self.state.atr_ma = pd.Series([d.atr for d in list(self._data_5m)[-72:] if hasattr(d, 'atr')]).mean() if len(self._data_5m) >= 72 else atr_val

        # 15m MACD
        df_15m = pd.DataFrame(list(self._data_15m))
        macd, signal, hist = self._macd(
            df_15m['close'], 
            self.params.get('macd_fast', 12),
            self.params.get('macd_slow', 26),
            self.params.get('macd_signal', 9)
        )
        self.state.macd_prev = self.state.macd
        self.state.macdsignal_prev = self.state.macdsignal
        self.state.macdhist_prev = self.state.macdhist

        self.state.macd = macd
        self.state.macdsignal = signal
        self.state.macdhist = hist

        # 娉㈡鐐硅瘑鍒?(3楂?浣庨€昏緫锛岄泦鎴?V4.0)
        df_5m = pd.DataFrame(list(self._data_5m))
        self._find_pivot_points(df_5m)

    def _manage_grid(self, data: MarketData):
        """浠ユ尝娈电粨鏋勭偣椹卞姩鍔ㄦ€佺綉鏍?(3楂?浣?"""
        now = data.timestamp
        
        # 浠呭湪鏈夊畬鏁存尝娈垫暟鎹椂鏇存柊缃戞牸
        if not self.state.pivots_high or not self.state.pivots_low:
            # 鍥為€€鍒拌繃鍘?6 灏忔椂 ATR 閫昏緫 (闃叉鍐峰惎鍔?
            lookback = self.params.get('grid_lookback_hours', 6)
            bars = list(self._data_5m)[-int(lookback * 12):]
            if not bars: return
            upper = max(b.high for b in bars)
            lower = min(b.low for b in bars)
        else:
            # 浣跨敤3楂?浣庣殑鏋佸€间綔涓虹綉鏍艰竟鐣?
            upper = max(p['price'] for p in self.state.pivots_high)
            lower = min(p['price'] for p in self.state.pivots_low)

        # 缂撳啿鍖哄鐞?
        range_size = upper - lower
        if range_size <= 0: range_size = upper * 0.01
        buffer = self.params.get('grid_buffer', 0.02)
        
        self.state.grid_upper = upper * (1 + buffer)
        self.state.grid_lower = lower * (1 - buffer)
        
        # 鐢熸垚缃戞牸绾?
        layers = self.params.get('grid_layers', 4)
        self.state.grid_lines = np.linspace(self.state.grid_lower, self.state.grid_upper, layers + 1).tolist()
        self.state.last_grid_reset = now

    def _check_halt(self, data: MarketData) -> bool:
        """榛戝ぉ楣呮娴?""
        if self.state.is_halted:
            if self.state.resume_time and data.timestamp >= self.state.resume_time:
                self.state.is_halted = False
                print(f"[V6.5B] 鎭㈠浜ゆ槗")
            else:
                return True
        
        # ATR 寮傚父妫€娴?
        if self.state.atr > self.state.atr_ma * self.params.get('atr_blackswan_mult', 3.0):
            self.state.is_halted = True
            self.state.halt_reason = "High Volatility (ATR Blackswan)"
            self.state.resume_time = data.timestamp + timedelta(minutes=self.params.get('atr_cooldown_min', 30))
            print(f"[V6.5B] 瑙﹀彂鐔旀柇: {self.state.halt_reason}")
            return True
            
        return False

    def _generate_signals(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        signals = []
        pos = context.positions.get(self.symbol)
        pos_size = float(pos.size) if pos else 0.0
        
        # MACD Status
        is_macd_golden = self.state.macd > self.state.macdsignal and getattr(self.state, 'macd_prev', 0) <= getattr(self.state, 'macdsignal_prev', 0)
        is_macd_dead = self.state.macd < self.state.macdsignal and getattr(self.state, 'macd_prev', 0) >= getattr(self.state, 'macdsignal_prev', 0)

        # Layers calculation
        layer_value = self.params.get('total_capital', 10000) / self.params.get('grid_layers', 4)
        current_layers = int(round(pos_size * data.close / layer_value)) if pos_size > 0 else 0

        # --- 鍏ㄥ眬鍐峰嵈閿侊細闃茶繛缁拱鍗曚笌鐬椂"涓€涔板氨鍗?寮傚父 ---
        cooldown_lock = False
        cooldown_min = self.params.get('buy_cooldown_min', 10)
        if getattr(self.state, 'last_buy_time', None) is not None:
            from datetime import timedelta
            if data.timestamp < self.state.last_buy_time + timedelta(minutes=cooldown_min):
                cooldown_lock = True

        # 1. Sell Logic
        if pos_size > 0 and not cooldown_lock:
            rsi_sell_gold = self.params.get('rsi_sell_gold', 68)
            rsi_sell_silver = self.params.get('rsi_sell_silver', 60)
            
            sell_layers = 0
            sig_type = ""
            
            if self.state.current_rsi > rsi_sell_gold and is_macd_dead:
                sell_layers = 2
                sig_type = "GOLD (MACD姝诲弶)"
            elif self.state.current_rsi > rsi_sell_silver:
                sell_layers = 1
                sig_type = "SILVER (瓒呬拱)"
                
            if sell_layers > 0:
                sell_layers = min(sell_layers, current_layers) if current_layers > 0 else 1
                sell_ratio = sell_layers / current_layers if current_layers > 0 else 1.0
                reason = f"MTF Sell [{sig_type}]: RSI={self.state.current_rsi:.1f} 鎶涘敭灞傛暟={sell_layers} 鍓╀綑鎸佷粨~={max(0, current_layers-sell_layers)}灞?
                signals.append(Signal(
                    timestamp=data.timestamp,
                    symbol=self.symbol,
                    side=Side.SELL,
                    size=pos_size * sell_ratio,
                    reason=reason
                ))

        # 2. Buy Logic
        can_buy = False
        buy_layers = 0
        sig_type = ""
        
        rsi_buy_threshold = self.params.get('rsi_buy_threshold', 35)
        
        if self.state.current_rsi < rsi_buy_threshold and current_layers < self.params.get('grid_layers', 4) and not cooldown_lock:
            if is_macd_golden:
                buy_layers = 2
                sig_type = "GOLD (MACD閲戝弶)"
            else:
                buy_layers = 1
                sig_type = "SILVER (瓒呭崠)"
            
            buy_layers = min(buy_layers, self.params.get('grid_layers', 4) - current_layers)
            if buy_layers > 0:
                can_buy = True

        if can_buy:
            buy_usdt = layer_value * buy_layers
            if context.cash >= buy_usdt * 0.95:  
                reason = f"MTF Buy [{sig_type}]: RSI={self.state.current_rsi:.1f} 涔板叆灞傛暟={buy_layers} 褰撳墠宸叉湁={current_layers}灞?
                signals.append(Signal(
                    timestamp=data.timestamp,
                    symbol=self.symbol,
                    side=Side.BUY,
                    size=buy_usdt,
                    meta={'size_in_quote': True},
                    reason=reason
                ))
                self.state.last_buy_time = data.timestamp
                self.state.last_buy_price = data.close

        return signals

    # --- 鎶€鏈寚鏍囪绠楀伐鍏?(绮剧畝鐗? ---
    def _rsi(self, series, period):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs.iloc[-1])) if not np.isnan(rs.iloc[-1]) else 50.0

    def _atr(self, high, low, close, period):
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        return tr.rolling(window=period).mean().iloc[-1]

    def _macd(self, series, fast, slow, signal):
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal, adjust=False).mean()
        return macd.iloc[-1], signal_line.iloc[-1], (macd - signal_line).iloc[-1]

    def _find_pivot_points(self, df: pd.DataFrame):
        """
        瀵绘壘鏈€杩戠殑 n 涓粨鏋勬€ф尝娈甸珮鐐瑰拰浣庣偣
        鏍稿績鎬濊矾锛歏4.0 鐨?鍙栨渶杩?N 涓浆鎶樼偣"锛岃€岄潪"鍙?N 涓渶鏋佺浠锋牸"
        """
        if len(self._data_5m) < 30: return
        
        n = 3  # 3楂?浣?
        # 灞€閮ㄧ‘璁ゅ垽瀹氱獥鍙?(澧炲ぇ鍒?10 鏍?= 50 鍒嗛挓锛岃繃婊ょ煭鏈熷櫔鐐?
        window_size = 10
        
        data_list = list(self._data_5m)
        highs = df['high'].values
        lows = df['low'].values
        curr_idx = len(df) - 1
        
        all_highs = []
        all_lows = []

        # 鍏ㄩ噺鎵弿缂撳瓨涓殑鎵€鏈夋暟鎹?
        for i in range(window_size, curr_idx + 1):
            # --- 浣庣偣妫€娴嬶細姣斿乏杈?window_size 鏍归兘浣?---
            if lows[i] <= min(lows[i-window_size:i]):
                is_pivot = False
                if i > curr_idx - window_size:
                    # 瀹炴椂鍖猴細鏄?i 鍒板綋鍓嶄箣闂寸殑鏈€浣庣偣
                    if i == curr_idx or lows[i] <= min(lows[i+1:]):
                        is_pivot = True
                else:
                    # 纭鍖猴細姣斿彸杈?window_size 鏍逛篃浣?
                    if lows[i] < min(lows[i+1 : i+window_size+1]):
                        is_pivot = True
                
                if is_pivot:
                    all_lows.append({'price': float(lows[i]), 'time': data_list[i].timestamp.isoformat(), 'index': i})

            # --- 楂樼偣妫€娴嬶細姣斿乏杈?window_size 鏍归兘楂?---
            if highs[i] >= max(highs[i-window_size:i]):
                is_pivot = False
                if i > curr_idx - window_size:
                    if i == curr_idx or highs[i] >= max(highs[i+1:]):
                        is_pivot = True
                else:
                    if highs[i] > max(highs[i+1 : i+window_size+1]):
                        is_pivot = True
                
                if is_pivot:
                    all_highs.append({'price': float(highs[i]), 'time': data_list[i].timestamp.isoformat(), 'index': i})

        # 鍙栨渶杩?n 涓粨鏋勮浆鎶樼偣 (浠庡彸鍚戝乏锛岄棿闅旇嚦灏?window_size 鏍归槻閲嶅彔)
        def _get_recent_n(pivots):
            res = []
            for p in reversed(pivots):  # 浠庢渶鏂板線鍥炲彇
                if not res or (res[-1]['index'] - p['index']) >= window_size:
                    res.append(p)
                if len(res) >= n:
                    break
            res.reverse()  # 鎭㈠鏃堕棿椤哄簭
            return res

        self.state.pivots_high = _get_recent_n(all_highs)
        self.state.pivots_low = _get_recent_n(all_lows)


    def get_status(self, context: Optional[StrategyContext] = None) -> Dict[str, Any]:
        # 璁＄畻杈呭姪鏄剧ず鎸囨爣
        is_bullish = self.state.macdhist > 0
        macd_trend = "寮虹墰" if is_bullish and self.state.macdhist > self.state.macdhist_prev else "鐗涘競" if is_bullish else "闇囪崱"
        if self.state.macdhist < 0:
            macd_trend = "寮虹唺" if self.state.macdhist < self.state.macdhist_prev else "鐔婂競"
        
        # 淇″彿鐘舵€佸垽瀹?(鐢ㄤ簬 UI 鏄剧ず)
        signal_text = "绛夊緟瓒嬪娍"
        signal_color = "neutral"
        signal_strength = "--"

        if self.state.is_halted:
            signal_text = f"鐔旀柇: {self.state.halt_reason}"
            signal_color = "sell"
        elif is_bullish:
            signal_color = "buy"
            # 璁＄畻淇″彿寮哄害: 鍩轰簬 RSI 鎺ヨ繎绋嬪害鍜?MACD 澧為暱
            rsi_dist = max(0, self.params.get('rsi_buy_threshold', 35) - self.state.current_rsi)
            if self.state.current_rsi < self.params.get('rsi_buy_threshold', 35):
                signal_text = "澶氬ご鎷╂椂涔板叆"
                signal_strength = "寮? if rsi_dist > 5 else "楂?
            else:
                signal_text = "瓒嬪娍鎸佹湁涓?
                signal_strength = "涓?
        else:
            signal_strength = "寮? if self.state.macdhist < -5 else "浣?

        # 閲忚兘鍒嗘瀽
        vol_current = 0
        vol_trend = "鎸佸钩"
        if self._data_5m:
            df = pd.DataFrame(list(self._data_5m))
            vol_current = df['volume'].iloc[-1]
            vol_ma = df['volume'].rolling(20).mean().iloc[-1]
            if not np.isnan(vol_ma) and vol_ma > 0:
                ratio = vol_current / vol_ma
                if ratio > 1.5: vol_trend = "鏀鹃噺"
                elif ratio < 0.6: vol_trend = "缂╅噺"

        pos_count = 0
        pos_size = 0.0
        pos_avg_price = 0.0
        pos_unrealized_pnl = 0.0
        if context and self.symbol in context.positions:
            pos = context.positions[self.symbol]
            pos_size = float(pos.size)
            pos_avg_price = float(pos.avg_price)
            pos_unrealized_pnl = float(pos.unrealized_pnl)
            if pos_size > 0:
                # DOGE 浠锋牸杈冧綆锛岃皟鏁村眰鏁颁及绠?
                pos_count = max(1, int(pos_size * pos_avg_price / (self.params.get('total_capital', 10000) / self.params.get('grid_layers', 4))))

        return {
            'name': self.name,
            'current_rsi': round(self.state.current_rsi, 2),
            'macd': round(self.state.macd, 4),
            'macdsignal': round(self.state.macdsignal, 4),
            'macdhist': round(self.state.macdhist, 4),
            'atr': round(self.state.atr, 2),
            'atrVal': round(self.state.atr, 2),
            'macd_trend': macd_trend,
            'signal_text': signal_text,
            'signal_color': signal_color,
            'signal_strength': signal_strength,
            'position_size': pos_size,
            'position_avg_price': pos_avg_price,
            'position_unrealized_pnl': pos_unrealized_pnl,
            'grid_lower': round(self.state.grid_lower, 2),
            'grid_upper': round(self.state.grid_upper, 2),
            'grid_range': f"{self.state.grid_lower:.1f} - {self.state.grid_upper:.1f}",
            'grid_lines': self.state.grid_lines,
            'rsi_oversold': self.params.get('rsi_buy_threshold', 35),
            'rsi_overbought': self.params.get('rsi_sell_threshold', 68),
            'position_count': pos_count,
            'marketRegime': "涓婂崌閫氶亾" if is_bullish else "闇囪崱涓嬭" if self.state.macdhist < -5 else "璋冩暣闃舵",
            'vol_trend': vol_trend,
            'current_volume': round(vol_current, 2),
            'is_halted': self.state.is_halted,
            'halt_reason': self.state.halt_reason,
            'pivots': {
                'pivots_high': getattr(self.state, 'pivots_high', []),
                'pivots_low': getattr(self.state, 'pivots_low', [])
            },
            'params': self.params,
            'param_metadata': self.param_metadata
        }
