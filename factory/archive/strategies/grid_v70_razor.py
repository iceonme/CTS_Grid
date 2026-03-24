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

class GridStrategyV70Razor(BaseStrategy):
    """
    GridStrategy V7.0-Razor (Kimibigclaw)
    
    鏍稿績鐗规€э細
    - 绾?RSI 宸︿晶鍔ㄦ€佺綉鏍硷紙MACD 瀹屽叏鍓旈櫎锛?
    - RSI 鍒嗗眰鍝嶅簲锛堟瀬绔?鏍囧噯锛?
    - ATR 鍔ㄦ€佺綉鏍奸棿璺?
    - 闃舵姝㈢泩 (Ladder Take-Profit)
    - 榛戝ぉ楣呮姢鐩?(Black Swan Guard)
    - 甯告€佺綉鏍?(RSI 28-70 V7.1 鎭㈠)
    """

    def __init__(self, name: str = "Grid_V70_Razor", **params):
        super().__init__(name, **params)
        self.params_path = params.get('config_path', 'config/grid_v70_razor_btc_runtime.json')
        self.meta_path = self.params_path.replace('runtime.json', 'meta.json')
        self.symbol = params.get('symbol', 'BTC-USDT')
        self.param_metadata = {}
        self._load_params()

        # 鏁版嵁缂撳瓨
        self._data_1m = deque(maxlen=400)   # 1m K绾跨敤浜庢瀬绔鎺?(ATR)
        self._data_5m = deque(maxlen=400)   # 5m K绾跨敤浜庢牳蹇?RSI 淇″彿涓庣綉鏍?

        # 绛栫暐鍐呴儴鐘舵€?
        @dataclass
        class StrategyState:
            current_rsi: float = 50.0
            atr: float = 0.0          # 1m ATR
            atr_ma: float = 0.0       # 1m ATR 杩囧幓 x 灏忔椂鍧囧€?
            
            grid_lower: float = 0.0
            grid_upper: float = 0.0
            grid_lines: List[float] = field(default_factory=list)
            
            is_halted: bool = False
            halt_reason: str = ""
            resume_time: Optional[datetime] = None
            
            last_grid_reset: Optional[datetime] = None
            last_buy_time: Optional[datetime] = None
            last_buy_price: float = 0.0
            last_trade_price: float = 0.0 # 鐢ㄤ簬甯告€佺綉鏍肩Щ鍔ㄤ腑鏋?

        self.state = StrategyState()

    def _load_params(self):
        """鍔犺浇杩愯鍙傛暟"""
        if os.path.exists(self.params_path):
            try:
                with open(self.params_path, 'r', encoding='utf-8') as f:
                    self.params.update(json.load(f))
            except Exception as e:
                print(f"[V7.0-Razor] 鍔犺浇鍙傛暟澶辫触: {e}")
        
        if os.path.exists(self.meta_path):
            try:
                with open(self.meta_path, 'r', encoding='utf-8') as f:
                    self.param_metadata = json.load(f)
            except Exception as e:
                print(f"[V7.0-Razor] 鍔犺浇鍏冩暟鎹け璐? {e}")

    def initialize(self):
        super().initialize()
        print(f"[V7.0-Razor] {self.name} 鍒濆鍖栧畬鎴?)

    def on_data(self, data: MarketData, context: Optional[StrategyContext]) -> List[Signal]:
        if not self._initialized:
            self.initialize()

        # 1. 鏇存柊鏁版嵁 (1m 涓?5m)
        self._update_data(data)
        
        # 鎸囨爣璁＄畻闇€瑕佽冻澶熸暟鎹?
        if len(self._data_5m) < 30 or len(self._data_1m) < 30:
            return []

        # 2. 璁＄畻绾?RSI 鍜?ATR
        self._calculate_indicators()

        # 3. 榛戝ぉ楣呴鎺ф娴?
        if self._check_halt(data, context):
            # 濡傛灉瑙﹀彂鐔旀柇涓旀寔浠擄紝鎶涘嚭娓呬粨淇″彿 (鍏ㄥ钩)
            if self.state.is_halted and context:
                pos = context.positions.get(self.symbol)
                if pos and pos.size > 0:
                    return [Signal(
                        timestamp=data.timestamp,
                        symbol=self.symbol,
                        side=Side.SELL,
                        size=float(pos.size),
                        reason=f"Black Swan Guard: ATR Surge. Emergency Sell All."
                    )]
            return []

        # 4. ATR 鍔ㄦ€佺綉鏍肩鐞?
        self._manage_grid(data)

        # 5. RSI 鍒嗗眰鍝嶅簲鐢熸垚淇″彿
        if context:
            return self._generate_signals(data, context)
        return []

    def _update_data(self, data: MarketData):
        """鏇存柊 1m 鍜?5m 鏁版嵁"""
        ts = data.timestamp
        # --- 1m K绾?---
        bar_1m_ts = ts.replace(second=0, microsecond=0)
        if self._data_1m and self._data_1m[-1].timestamp.replace(second=0, microsecond=0) == bar_1m_ts:
            last = self._data_1m[-1]
            updated = MarketData(
                timestamp=ts, symbol=data.symbol,
                open=last.open, high=max(last.high, data.high),
                low=min(last.low, data.low), close=data.close, volume=data.volume
            )
            self._data_1m[-1] = updated
        else:
            self._data_1m.append(data)

        # --- 5m K绾?---
        bar_5m_ts = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        if self._data_5m and self._data_5m[-1].timestamp.replace(
                minute=(self._data_5m[-1].timestamp.minute // 5) * 5, second=0, microsecond=0) == bar_5m_ts:
            last = self._data_5m[-1]
            updated = MarketData(
                timestamp=ts, symbol=data.symbol,
                open=last.open, high=max(last.high, data.high),
                low=min(last.low, data.low), close=data.close, volume=data.volume
            )
            self._data_5m[-1] = updated
        else:
            self._data_5m.append(data)

    def _calculate_indicators(self):
        """浠呰绠楁牳蹇?RSI 鍜?鍔ㄦ€佺綉鏍煎繀闇€鐨?ATR"""
        # 5m RSI
        closes_5m = pd.Series([d.close for d in self._data_5m])
        self.state.current_rsi = self._rsi(closes_5m, self.params.get('signals', {}).get('rsi_period', 14))
        
        # 1m ATR (鐢ㄤ簬椋庢帶)
        highs_1m = pd.Series([d.high for d in self._data_1m])
        lows_1m = pd.Series([d.low for d in self._data_1m])
        closes_1m = pd.Series([d.close for d in self._data_1m])
        # 浣跨敤 14 鍛ㄦ湡 ATR
        atr_1m_val = self._atr(highs_1m, lows_1m, closes_1m, 14)
        self.state.atr = atr_1m_val
        
        # 缁熻杩囧幓 6 灏忔椂 (360 鍒嗛挓=360鏍?m K绾? ATR鍧囧€?
        lookback = 360
        if len(self._data_1m) >= lookback:
            # 绠€鍖栵細鐢ㄦ敹鐩樹环鐨勬尝鍔ㄤ唬鐞嗗巻鍙?ATR 鍧囧€间及绠楋紝閬垮厤鍏ㄩ噺璁＄畻鎬ц兘鎹熻€?
            hist_closes = closes_1m.iloc[-lookback:]
            hist_highs = highs_1m.iloc[-lookback:]
            hist_lows = lows_1m.iloc[-lookback:]
            self.state.atr_ma = self._atr(hist_highs, hist_lows, hist_closes, 14).mean()
        else:
            self.state.atr_ma = atr_1m_val

    def _manage_grid(self, data: MarketData):
        """鍔ㄦ€佽绠楃綉鏍艰寖鍥达細鍩轰簬 ATR 涔樻暟"""
        grid_params = self.params.get('grid', {})
        min_spacing = grid_params.get('min_spacing', 0.003)
        atr_mult = grid_params.get('atr_multiplier', 0.15)
        layers = self.params.get('trading', {}).get('grid_layers', 5)

        # 鍔ㄦ€侀棿璺濊绠?Spacing = max(min_spacing, (ATR / Price) * multiplier)
        if data.close > 0 and self.state.atr > 0:
            atr_pct = (self.state.atr / data.close) * atr_mult
            spacing_pct = max(min_spacing, atr_pct)
        else:
            spacing_pct = min_spacing

        # 浠ュ綋鍓嶄环鏍间负涓灑锛屼笂涓嬪睍寮€缃戞牸杈圭晫 (绠€鍗曢€昏緫)锛屾垨鑰呬娇鐢ㄨ繎鏈熼珮浣庣偣
        # 鏀硅繘锛歏7.1 閲囩敤涓婁竴娆′氦鏄撲环鎴栧綋鍓嶄环涓哄熀鍑嗕笅鎺€?
        anchor = self.state.last_trade_price if self.state.last_trade_price > 0 else data.close
        
        # 缃戞牸瑕嗙洊鑼冨洿
        total_range_pct = spacing_pct * layers
        self.state.grid_upper = anchor * (1 + total_range_pct * 0.5)
        self.state.grid_lower = anchor * (1 - total_range_pct * 0.5)
        
        self.state.grid_lines = np.linspace(self.state.grid_lower, self.state.grid_upper, layers + 1).tolist()

    def _check_halt(self, data: MarketData, context: Optional[StrategyContext]) -> bool:
        """榛戝ぉ楣呴鎺э細ATR寮傚父婵€澧炲垽瀹?""
        if self.state.is_halted:
            if self.state.resume_time and data.timestamp >= self.state.resume_time:
                self.state.is_halted = False
                self.state.halt_reason = ""
                print(f"[V7.0-Razor] 鎭㈠浜ゆ槗")
            else:
                return True
        
        risk_params = self.params.get('risk', {})
        black_swan_mult = risk_params.get('black_swan_atr_mult', 3.0)
        
        if self.state.atr_ma > 0 and self.state.atr > self.state.atr_ma * black_swan_mult:
            self.state.is_halted = True
            self.state.halt_reason = "Black Swan (ATR Surge)"
            # 榛樿鍐峰嵈 15 鍒嗛挓
            self.state.resume_time = data.timestamp + timedelta(minutes=15)
            print(f"[V7.0-Razor] 瑙﹀彂鐔旀柇: {self.state.halt_reason}")
            return True
            
        return False

    def _generate_signals(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        signals = []
        pos = context.positions.get(self.symbol)
        pos_size = float(pos.size) if pos else 0.0
        
        trading_params = self.params.get('trading', {})
        signal_params = self.params.get('signals', {})
        risk_params = self.params.get('risk', {})

        total_capital = trading_params.get('initial_capital', 10000)
        max_layers = trading_params.get('grid_layers', 5)
        layer_percent = trading_params.get('layer_size_percent', 20) / 100.0
        layer_value = total_capital * layer_percent

        current_layers = int(round(pos_size * data.close / layer_value)) if pos_size > 0 else 0

        # --- 闃舵姝㈢泩閫昏緫 (Ladder Take-Profit) ---
        sell_ratio = 0.0
        if pos_size > 0:
            rsi_sell_normal = signal_params.get('rsi_sell_normal', 70)
            rsi_sell_extreme = signal_params.get('rsi_sell_extreme', 80)
            tp_ladder = risk_params.get('ladder_take_profit', [0.3, 0.4, 0.3])
            
            sig_type = ""
            
            # 鍒ゆ柇鎶涘敭灞傜骇 (鏋佸害璐┆ = 鍗?灞?澶ф瘮渚嬶紝璐┆ = 鍗?灞?鏍囧噯姣斾緥)
            if self.state.current_rsi > rsi_sell_extreme:
                # 鏋佺璐┆锛氬弻鍊嶅崠鍑?(2灞傛垨鍓╀綑鎬婚噺鐨勫緢澶ф瘮渚?
                sig_type = "EXTREME GREED (鏋佸害璐┆)"
                # 灏濊瘯鏍规嵁闃舵琛ㄥ崠鍑哄浠斤紝绠€鍗曞鐞嗕负鍗栧嚭 2 浠芥瘮渚?
                if len(tp_ladder) >= 2:
                    sell_ratio = tp_ladder[0] + tp_ladder[1]
                else:
                    sell_ratio = 0.6 # fallback
                # 涓嶈秴杩?1.0
                sell_ratio = min(1.0, sell_ratio) 
                # 闃叉鏋佸叾缁嗗井娈嬬暀
                if pos_size * (1 - sell_ratio) * data.close < 10: 
                    sell_ratio = 1.0

            elif self.state.current_rsi > rsi_sell_normal:
                sig_type = "GREED (璐┆)"
                sell_ratio = tp_ladder[0] if tp_ladder else 0.3
                # 闃叉缁嗗井娈嬬暀
                if pos_size * (1 - sell_ratio) * data.close < 10: 
                    sell_ratio = 1.0
                    
            if sell_ratio > 0:
                sell_amount = pos_size * sell_ratio
                reason = f"Razor Sell [{sig_type}]: RSI={self.state.current_rsi:.1f} 闃舵姝㈢泩姣斾緥={sell_ratio*100:.0f}%"
                signals.append(Signal(
                    timestamp=data.timestamp,
                    symbol=self.symbol,
                    side=Side.SELL,
                    size=sell_amount,
                    reason=reason
                ))
                self.state.last_trade_price = data.close
                # 鍙戝嚭鍗栧嚭淇″彿鍚庡喎鍗翠竴娈垫椂闂达紙閫氳繃杩囨护鍚屽悜淇″彿瀹炵幇锛夛紝褰撳墠鐢卞紩鎿庨鐜囨帶鍒讹紝姝ゅ涓嶅仛寮洪攣

        # --- 鍒嗗眰涔板叆閫昏緫 ---
        rsi_buy_normal = signal_params.get('rsi_buy_normal', 28)
        rsi_buy_extreme = signal_params.get('rsi_buy_extreme', 20)
        
        can_buy = False
        buy_layers_req = 0
        sig_type = ""

        # 鐗规畩椋庢帶锛欴OGE 鍐峰嵈鎴栨寔浠撲笂闄?(鍦ㄦ墿灞曞瓙绫绘垨閰嶇疆涓綋鐜?
        max_pos_percent = risk_params.get('max_position_percent', 100) / 100.0
        current_pos_value = pos_size * data.close
        if current_pos_value >= total_capital * max_pos_percent:
            # 杈惧埌鎸佷粨涓婇檺
            pass
        elif current_layers < max_layers:
            if self.state.current_rsi < rsi_buy_extreme:
                buy_layers_req = 2  # 鏋佺鎭愭儳锛屽弻鍊嶄拱鍏?
                sig_type = "EXTREME FEAR (鏋佸害鎭愭儳 涓ゅ€?"
            elif self.state.current_rsi < rsi_buy_normal:
                buy_layers_req = 1  # 鎭愭儳锛屾爣鍑嗕拱鍏?
                sig_type = "FEAR (鎭愭儳 涓€鍊?"
            
            # 闄愬埗涓嶈兘瓒呰繃鏈€澶у眰鏁伴檺鍒跺拰鍓╀綑鍙敤璧勯噾
            buy_layers_req = min(buy_layers_req, max_layers - current_layers)
            
            if buy_layers_req > 0:
                # 浠锋牸缃戞牸妫€鏌ワ細鍗充娇 RSI 婊¤冻锛岃嫢璺濈涓婃涔板叆浠锋牸澶繎鍒欎笉涔?(寮哄埗缃戞牸闂磋窛)
                grid_params = self.params.get('grid', {})
                min_spacing = grid_params.get('min_spacing', 0.003)
                if self.state.last_buy_price > 0:
                    price_drop = (self.state.last_buy_price - data.close) / self.state.last_buy_price
                    if price_drop > min_spacing:
                        can_buy = True
                    # 鎴栬€呭鏋滄槸绌轰粨锛岀洿鎺ュ彲浠ヤ拱
                    elif current_layers == 0:
                        can_buy = True
                else:
                    can_buy = True

        if can_buy:
            buy_usdt = layer_value * buy_layers_req
            if context.cash >= buy_usdt * 0.95:  
                reason = f"Razor Buy [{sig_type}]: RSI={self.state.current_rsi:.1f} 鎶曞叆灞傛暟={buy_layers_req}"
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
                self.state.last_trade_price = data.close

        # --- 甯告€佺綉鏍奸€昏緫 (V7.1 RSI 28-70 涔嬮棿杩愯) ---
        if not can_buy and sell_ratio == 0.0:
            # 鎰忓懗鐫€娌℃湁瑙﹀彂鏋佺 RSI 鐨勪拱鍏ュ拰鍗栧嚭
            grid_params = self.params.get('grid', {})
            min_spacing = grid_params.get('min_spacing', 0.003)
            
            # 浣庡惛 (璺岀牬涓嬭建 涓?鏈夎祫閲戞湁灞傛暟)
            if data.close < self.state.grid_lower:
                if current_layers < max_layers:
                    buy_usdt = layer_value
                    if context.cash >= buy_usdt * 0.95:
                        grid_buy_reason = f"Normal Grid Buy: 浠锋牸璺岀牬涓嬭建 ({data.close:.2f} < {self.state.grid_lower:.2f})"
                        signals.append(Signal(
                            timestamp=data.timestamp,
                            symbol=self.symbol,
                            side=Side.BUY,
                            size=buy_usdt,
                            meta={'size_in_quote': True},
                            reason=grid_buy_reason
                        ))
                        self.state.last_buy_time = data.timestamp
                        self.state.last_buy_price = data.close
                        self.state.last_trade_price = data.close
            
            # 楂樻姏 (绐佺牬涓婅建 涓?鏈夋寔浠?
            elif data.close > self.state.grid_upper:
                if pos_size > 0:
                    sell_amount = pos_size / max(1, current_layers) # 鍗栧嚭1灞?
                    # 褰撳墠浠锋牸璺濈涓婃浜ゆ槗澶繎鍒欎笉鍗栵紝鎴栬€呰繖閲屽己鍒跺崠
                    grid_sell_reason = f"Normal Grid TP: 浠锋牸绐佺牬涓婅建 ({data.close:.2f} > {self.state.grid_upper:.2f})"
                    signals.append(Signal(
                        timestamp=data.timestamp,
                        symbol=self.symbol,
                        side=Side.SELL,
                        size=sell_amount,
                        reason=grid_sell_reason
                    ))
                    self.state.last_trade_price = data.close
            
            # 缃戞牸閲嶇疆鏈哄埗锛堝亸绂昏繃澶э級
            # 渚嬪濡傛灉浠锋牸鑴辩閿氱偣瓒呰繃涓€瀹氳窛绂诲苟涓旀病鏈夋垚浜ゅ彂鐢燂紝涓诲姩璺熼殢
            if abs(data.close - self.state.last_trade_price) / (self.state.last_trade_price or data.close) > min_spacing * 3:
                self.state.last_trade_price = data.close
                self.state.last_grid_reset = data.timestamp

        return signals

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
        signal_text = "涓€ц鏈?
        signal_color = "neutral"
        
        rsi = self.state.current_rsi
        sp = self.params.get('signals', {})
        if self.state.is_halted:
            signal_text = f"鐔旀柇: {self.state.halt_reason}"
            signal_color = "sell"
        elif rsi < sp.get('rsi_buy_extreme', 20):
            signal_text = "鏋佸害鎭愭儳"
            signal_color = "buy"
        elif rsi < sp.get('rsi_buy_normal', 28):
            signal_text = "鎭愭儳"
            signal_color = "buy"
        elif rsi > sp.get('rsi_sell_extreme', 80):
            signal_text = "鏋佸害璐┆"
            signal_color = "sell"
        elif rsi > sp.get('rsi_sell_normal', 70):
            signal_text = "璐┆"
            signal_color = "sell"

        pos_count = 0
        pos_size = 0.0
        pos_avg_price = 0.0
        pos_unrealized_pnl = 0.0
        if context and self.symbol in context.positions:
            pos = context.positions[self.symbol]
            pos_size = float(pos.size)
            pos_avg_price = float(pos.avg_price)
            pos_unrealized_pnl = float(pos.unrealized_pnl)
            
            trading_params = self.params.get('trading', {})
            total_cap = trading_params.get('initial_capital', 10000)
            layers = trading_params.get('grid_layers', 5)
            if pos_size > 0:
                pos_count = max(1, int(round(pos_size * pos_avg_price / (total_cap / layers))))

        return {
            'name': self.name,
            'current_rsi': float(np.round(self.state.current_rsi, 2)),
            'atr': float(np.round(self.state.atr, 2)),
            'atr_ma': float(np.round(self.state.atr_ma, 2)),
            'atrVal': float(np.round(self.state.atr, 2)),
            'marketRegime': '闇囪崱/鏈煡',
            'vol_trend': '骞崇ǔ',
            'current_volume': float(self._data_1m[-1].volume) if self._data_1m else 0.0,
            'signal_text': signal_text,
            'signal_color': signal_color,
            'position_size': pos_size,
            'position_avg_price': pos_avg_price,
            'position_unrealized_pnl': pos_unrealized_pnl,
            'grid_lower': float(np.round(self.state.grid_lower, 2)),
            'grid_upper': float(np.round(self.state.grid_upper, 2)),
            'grid_range': f"{self.state.grid_lower:.1f} - {self.state.grid_upper:.1f}",
            'grid_lines': self.state.grid_lines,
            'rsi_oversold': sp.get('rsi_buy_normal', 28),
            'rsi_overbought': sp.get('rsi_sell_normal', 70),
            'position_count': pos_count,
            'is_halted': self.state.is_halted,
            'halt_reason': self.state.halt_reason,
            'params': self.params,
            'param_metadata': self.param_metadata
        }
