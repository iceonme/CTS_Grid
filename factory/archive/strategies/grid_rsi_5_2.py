"""
鍔ㄦ€佺綉鏍?RSI 绛栫暐 V5.2 - 鍏ㄦ柊閲嶅啓鐗?
5鍒嗛挓瓒嬪娍纭 + 寮哄埗婊′粨 + 鍔ㄦ€佹鐩?+ 澶氶噸鍙嶈浆淇濇姢
"""

import json
import numpy as np
import time as _time
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from collections import deque

import pandas as pd
from console.core import (
    Signal, MarketData, StrategyContext, FillEvent,
    Side, OrderType, MarketRegime
)
from .base import BaseStrategy

# ============================================================
# 1. 鐘舵€佷笌甯搁噺
# ============================================================

@dataclass
class StrategyState:
    # 鏍稿績鎸佷粨鐘舵€?
    current_layers: int = 0
    grid_center: Optional[float] = None
    dynamic_grid: bool = True
    
    # 鎸囨爣鏁版嵁
    rsi_6: float = 50.0
    rsi_12: float = 50.0
    rsi_24: float = 50.0
    macd_line: float = 0.0
    signal_line: float = 0.0
    histogram: float = 0.0
    ma5: float = 0.0
    ma10: float = 0.0
    vol_ma20: float = 0.0
    vol_ratio: float = 1.0
    
    # 鍘嗗彶璁板綍 (鐢ㄤ簬 RSI 楠ら檷鍒ゆ柇绛?
    history_rsi_6: deque = field(default_factory=lambda: deque(maxlen=20))
    trend_score: int = 0
    target_layers: int = 0
    
    # 浜ゆ槗璁板綍
    last_trade_ts: float = 0.0
    last_candle: Dict[str, Any] = field(default_factory=dict)
    
    # 銆愬吋瀹规€цˉ鍏ㄣ€? 渚?LiveEngine 棰勭儹涓庣敾鍥句娇鐢?
    grid_upper: float = 0.0
    grid_lower: float = 0.0
    grid_prices: List[float] = field(default_factory=list)
    last_grid_update: int = 0
    
    # 淇″彿鎶戝埗鐘舵€?
    last_buy_price: float = 0.0
    last_buy_bar_ts: Optional[datetime] = None
    last_sell_price: float = 0.0
    last_sell_bar_ts: Optional[datetime] = None
    
    @property
    def current_rsi(self) -> float:
        return self.rsi_6

# ============================================================
# 2. 楂樻€ц兘 O(1) 澧為噺鎸囨爣寮曟搸
# ============================================================

class IncrementalIndicatorsV52:
    """澧為噺璁＄畻 MACD, 澶氬懆鏈?RSI, MA, 鎴愪氦閲?MA"""
    def __init__(self, p: dict):
        self.p = p
        self.count = 0
        self.prev_close = 0.0
        
        # MACD
        self.ema_12 = 0.0
        self.ema_26 = 0.0
        self.macd_sig = 0.0
        
        # RSI (6, 12, 24) - 浣跨敤 Wilder 骞虫粦绠楁硶
        self.rsi_params = [
            {'p': p['rsi_period_shorter'], 'gain': 0.0, 'loss': 0.0, 'val': 50.0},
            {'p': p['rsi_period_medium'],  'gain': 0.0, 'loss': 0.0, 'val': 50.0},
            {'p': p['rsi_period_longer'],  'gain': 0.0, 'loss': 0.0, 'val': 50.0}
        ]
        
        # MA (5, 10) & Volume MA 20 - 浣跨敤 deque 缁存姢绐楀彛鍜?
        self.win_ma5 = deque(maxlen=5)
        self.win_ma10 = deque(maxlen=10)
        self.win_vol20 = deque(maxlen=20)
        self.sum_ma5 = 0.0
        self.sum_ma10 = 0.0
        self.sum_ma10 = 0.0
        self.sum_vol20 = 0.0

        # MACD 绯绘暟棰勮绠?(閬垮厤 update 涓噸澶嶈绠?
        self.alpha_12 = 2.0 / (12 + 1)
        self.alpha_26 = 2.0 / (26 + 1)
        self.alpha_sig = 2.0 / (9 + 1)

    def update(self, d: MarketData, s: StrategyState, commit: bool = True):
        """
        璁＄畻骞舵洿鏂版寚鏍囥€?
        commit=True: 姘镐箙鎺ㄨ繘鎸囨爣鏇茬嚎 (鐢ㄤ簬 Bar 鍒囨崲)
        commit=False: 浠呰绠楀綋鍓嶉瑙堝€煎苟濉叆 s锛屼笉鏀瑰彉绫诲唴閮ㄧ殑 EMA/MA 鐘舵€?(鐢ㄤ簬 Tick 鏇存柊)
        """
        c, v = d.close, d.volume
        
        # 1. MACD (12, 26, 9)
        alpha12, alpha26, alphasig = self.alpha_12, self.alpha_26, self.alpha_sig
        
        # 棰勮璁＄畻
        tmp_ema12 = self.ema_12 + (c - self.ema_12) * alpha12
        tmp_ema26 = self.ema_26 + (c - self.ema_26) * alpha26
        tmp_macd = tmp_ema12 - tmp_ema26
        tmp_sig = self.macd_sig + (tmp_macd - self.macd_sig) * alphasig
        
        # 2. RSI (6, 12, 24)
        diff = c - self.prev_close
        gain = max(diff, 0)
        loss = max(-diff, 0)
        
        tmp_rsi_results = []
        for item in self.rsi_params:
            period = item['p']
            # 璁＄畻棰勮骞冲潎娑ㄨ穼
            tmp_gain = (item['gain'] * (period - 1) + gain) / period
            tmp_loss = (item['loss'] * (period - 1) + loss) / period
            rs = tmp_gain / tmp_loss if tmp_loss > 1e-9 else 100.0
            val = 100.0 - (100.0 / (1.0 + rs)) if tmp_loss > 1e-9 else 100.0
            tmp_rsi_results.append(val)
        
        # 3. MA (5, 10, 20)
        # 娉ㄦ剰: 姝ゅ MA 棰勮绠€鍖栧鐞嗭紝浣跨敤褰撳墠鍊兼浛浠ｇ獥鍙ｆ渶鏃у€艰绠?
        tmp_ma5 = s.ma5 if not commit else 0 # 鍗犱綅
        tmp_ma10 = s.ma10 if not commit else 0 # 鍗犱綅
        
        # 鍐欏叆鐘舵€?(棰勮)
        s.macd_line, s.signal_line, s.histogram = tmp_macd, tmp_sig, tmp_macd - tmp_sig
        s.rsi_6, s.rsi_12, s.rsi_24 = tmp_rsi_results
        
        # 濡傛灉鏄?commit 妯″紡锛屽垯姘镐箙鏇存柊鍐呴儴鐘舵€?
        if commit:
            self.count += 1
            if self.count == 1:
                self.ema_12 = self.ema_26 = self.prev_close = c
                s.ma5 = s.ma10 = c
                s.vol_ma20 = v
                return

            self.ema_12, self.ema_26, self.macd_sig = tmp_ema12, tmp_ema26, tmp_sig
            self.prev_close = c
            
            for i, val in enumerate(tmp_rsi_results):
                period = self.rsi_params[i]['p']
                self.rsi_params[i]['gain'] = (self.rsi_params[i]['gain'] * (period - 1) + gain) / period
                self.rsi_params[i]['loss'] = (self.rsi_params[i]['loss'] * (period - 1) + loss) / period
                
            # MA 绐楀彛鏇存柊
            if len(self.win_ma5) == self.win_ma5.maxlen: self.sum_ma5 -= self.win_ma5.popleft()
            self.win_ma5.append(c); self.sum_ma5 += c; s.ma5 = self.sum_ma5 / len(self.win_ma5)
            
            if len(self.win_ma10) == self.win_ma10.maxlen: self.sum_ma10 -= self.win_ma10.popleft()
            self.win_ma10.append(c); self.sum_ma10 += c; s.ma10 = self.sum_ma10 / len(self.win_ma10)
            
            if len(self.win_vol20) == self.win_vol20.maxlen: self.sum_vol20 -= self.win_vol20.popleft()
            self.win_vol20.append(v); self.sum_vol20 += v; s.vol_ma20 = self.sum_vol20 / len(self.win_vol20)
            s.vol_ratio = v / s.vol_ma20 if s.vol_ma20 > 0 else 1.0
            
            s.history_rsi_6.append(s.rsi_6)

    @property
    def warmup_done(self) -> bool:
        return self.count >= 25 # 瑕嗙洊鏈€闀?RSI 24

# ============================================================
# 3. 鏍稿績閫昏緫寮曟搸 (Scorer, Risk, Grid)
# ============================================================

class TrendScorerV52:
    @staticmethod
    def calculate(s: StrategyState, p: Dict[str, Any]) -> int:
        score = 0
        
        # 1. MACD (鏂囨。閫昏緫: MACD > Signal 涓?MACD > 0 绉?2 鍒? 浠?MACD > Signal 绉?1 鍒?
        if s.macd_line > s.signal_line:
            if s.macd_line > 0:
                score += 2
            else:
                score += 1
                
        # 2. RSI 鍒嗗眰 (鏂囨。閫昏緫: RSI1 < 40 绉?2 鍒? RSI1 < 50 绉?1 鍒? RSI3 > 50 棰濆绉?1 鍒?
        # 娉ㄦ剰: 鏂囨。涓?RSI1 瀵瑰簲 short (6), RSI3 瀵瑰簲 long (24)
        if s.rsi_6 < 40:
            score += 2
        elif s.rsi_6 < 50:
            score += 1
            
        if s.rsi_24 > 50:
            score += 1
            
        # 3. 鎴愪氦閲?(鏂囨。閫昏緫: Vol > MA20 * 1.3 绉?1 鍒?
        vol_thr = p.get('volume_threshold', 1.3)
        if s.vol_ratio > vol_thr:
            score += 1
            
        return min(score, 5)

class RiskControllerV52:
    @staticmethod
    def check_reversal(s: StrategyState, p: Dict[str, Any], prev_s: Dict[str, Any]) -> str:
        if not prev_s: return None
        
        # 1. MA 浜ゅ弶 (MA5 涓嬬┛ MA10) -> 鍑?2 灞?
        if s.ma5 < s.ma10 and prev_s.get('ma5', 0) >= prev_s.get('ma10', 0):
            return "MA5涓嬬┛MA10"
            
        # 2. MACD 姝诲弶 (MACD < Signal 涓?MACD > 0) -> 鍑?1 灞?
        if s.macd_line < s.signal_line and s.macd_line > 0:
            # 銆愪紭鍖栬ˉ鍏呫€? 濡傛灉褰撳墠鏄己瓒嬪娍(Score>=4)锛屽拷鐣?MACD 姝诲弶浠ュ厤琚绻佹礂鍑猴紝淇′换 MA 鍜?RSI 楠ら檷
            if s.trend_score >= 4:
                return None
            
            if prev_s.get('macd_line', 0) >= prev_s.get('signal_line', 0):
                return "MACD姝诲弶"
                
        # 3. RSI 楠ら檷 (1灏忔椂鍗?2鏍圭嚎鍐呰穼骞?> 15) -> 鍑?2 灞?
        # 閫昏緫锛氶渶瑕?state 涓淮鎶ゅ巻鍙?RSI銆傝嫢鏈疄瑁咃紝鏆傛椂鐢ㄧ畝鍖栫増銆?
        # 宸茬粡鍦?state 涓湁浜?rsi_history_1h 鐨勯€昏緫銆?
        if len(s.history_rsi_6) >= 12:
            old_rsi = s.history_rsi_6[0]
            if old_rsi - s.rsi_6 > p.get('stop_loss_rsi_drop', 15):
                return f"RSI楠ら檷({old_rsi-s.rsi_6:.1f})"
                
        # 4. 鏀鹃噺涓嬭穼 (鏂囨。閫昏緫: 閲忔瘮 > 1.5 涓斾环鏍兼敹闃?
        if s.vol_ratio > p.get('stop_loss_volume_spike', 1.5) and s.last_candle.get('close', 0) < s.last_candle.get('open', 0):
            return "鏀鹃噺涓嬭穼"
            
        return None

    @staticmethod
    def check_take_profit(s: StrategyState, p: dict) -> Optional[Tuple[int, int]]:
        """闃舵姝㈢泩灞傛暟鍒ゆ柇: 杩斿洖 (鍗栧嚭灞傛暟, 闃舵绱㈠紩)"""
        if not p.get('take_profit_enable'): return None
        levels = p['take_profit_rsi_levels']
        layers = p['take_profit_sell_layers']
        
        # 浠庨珮鍒颁綆妫€鏌ワ紝鍙Е鍙戞渶楂樼殑閭ｄ竴绾?
        for i in range(len(levels) - 1, -1, -1):
            if s.rsi_6 > levels[i]:
                return layers[i], i + 1
        return None

# ============================================================
# 5. 绛栫暐涓荤被闆嗘垚
# ============================================================

class GridRSIStrategyV5_2(BaseStrategy):
    def __init__(self, symbol: str = "BTC-USDT", config_path: str = None, **kwargs):
        super().__init__(name=kwargs.get("name", "GridRSI_V5.2_TrendForce"), **kwargs)
        self.symbol = symbol
        
        # 鍔ㄦ€佸畾浣嶆牳蹇冮厤缃洰褰?(鍏煎 Arena 鍜?Live 妯″紡)
        current_file_dir = Path(__file__).parent.resolve()
        self.config_dir = current_file_dir.parent / "config"
        self.default_config_path = self.config_dir / "grid_v52_default.json"
        
        # 鍏煎鎬у鐞嗭細濡傛灉 runtime 涓嶅瓨鍦紝鍒欎娇鐢?default
        self.runtime_config_path = self.config_dir / "grid_v52_runtime.json"
        self.active_config_path = Path(config_path) if config_path else self.runtime_config_path
        if not self.active_config_path.exists():
            self.active_config_path = self.default_config_path
            
        # 鍏煎鍒悕: 渚?Runner 璇嗗埆
        self.params_path = str(self.active_config_path)
            
        self.params = {}
        self.param_metadata = {}
        self._last_config_mtime = 0.0
        self.reload_config(force=True)
            
        self.state = StrategyState()
        self.indicators = IncrementalIndicatorsV52(self.params) 
        self._data_buffer = deque(maxlen=200) 
        
        self._prev_state_mini = {} 
        self._tick_count = 0
        self._last_signal_time = None # 淇″彿椋庢毚淇濇姢: 鍚屼竴涓椂闂存埑(Bar)鍙鐞嗕竴娆′俊鍙?
        self._last_bar_ts = None # Bar 鍒囨崲妫€娴?
        self._last_tick_data = None
        
    def reload_config(self, force=False):
        """鍔犺浇鎴栫儹閲嶈浇閰嶇疆 (鏀寔鐢?Runner 澶栭儴鏄惧紡瑙﹀彂锛岀Щ闄よ疆璇?"""
        # 1. 鍏堣浇鍏ヤ繚搴曢粯璁ら厤缃?(濡傛灉瀛樺湪)
        if self.default_config_path.exists():
            try:
                with open(self.default_config_path, 'r', encoding='utf-8') as f:
                    self.params.update(json.load(f))
            except: pass
        
        # 2. 杞藉叆褰撳墠娲诲姩鐨勯厤缃?(runtime)
        if self.active_config_path.exists():
            try:
                mtime = self.active_config_path.stat().st_mtime
                if mtime > self._last_config_mtime or force:
                    with open(self.active_config_path, 'r', encoding='utf-8') as f:
                        self.params.update(json.load(f))
                    self._last_config_mtime = mtime

                    # 3. 杞藉叆 UI 鍏冩暟鎹?
                    meta_file = self.config_dir / "grid_v52_meta.json"
                    if meta_file.exists():
                        with open(meta_file, 'r', encoding='utf-8') as f:
                            self.param_metadata = json.load(f)
                    
                    print(f"[V5.2] 閰嶇疆閲嶈浇鎴愬姛: {self.active_config_path.name}")
            except Exception as e:
                print(f"[V5.2] 閲嶈浇閰嶇疆澶辫触: {e}")

    def warmup(self, data_list: List[MarketData]):
        """[鏍囧噯鎺ュ彛] 瀹炵幇楂樻晥棰勭儹涓庣綉鏍煎垵濮嬪寲"""
        if not data_list: return
        
        print(f"[V5.2] 姝ｅ湪澶勭悊 {len(data_list)} 鏍瑰巻鍙?K 绾胯繘琛屾寚鏍囬鐑?..")
        for data in data_list:
            # 1. 鏇存柊鍐呴儴缂撳瓨 (鐢ㄤ簬 Dashboard 鍘嗗彶璁板綍)
            self._data_buffer.append(data)
            # 2. 鎺ㄨ繘鎸囨爣璁＄畻 (commit=True)
            self.indicators.update(data, self.state, commit=True)
            # 3. 鏇存柊杩蜂綘鐘舵€佷緵涓嬫瀵规瘮
            self._save_mini_state(data)
            
        # 4. 鑷姩鍒濆鍖栫綉鏍?(鏇夸唬鍘?Engine 涓殑纭紪鐮侀€昏緫)
        last_price = data_list[-1].close
        rng = self.params.get('grid_range_percent', 0.04)
        self.state.grid_center = last_price
        self.state.grid_upper = last_price * (1 + rng)
        self.state.grid_lower = last_price * (1 - rng)
        
        # 璁＄畻缃戞牸鐐?(鍏煎鏃х増鐘舵€佹樉绀?
        levels = self.params.get('max_positions', 5)
        self.state.grid_prices = np.linspace(self.state.grid_lower, self.state.grid_upper, levels + 1).tolist()
        self.state.last_grid_update = len(self._data_buffer)
        
        print(f"  [OK] 鎸囨爣棰勭儹瀹屾垚锛岀綉鏍煎凡閿氬畾鍦? {last_price:.2f}")

    def on_data(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        signals = []
        
        # 0. 淇″彿椋庢毚淇濇姢 (鍚屼竴涓?Tick 涓嶅彂澶氬崟锛屼繚鐣欏熀纭€閫昏緫)
        if self._last_signal_time == data.timestamp and self._tick_count > 0:
            # 娉ㄦ剰: 濡傛灉鏄疄鏃?Tick 鍐呴儴锛屽悓涓€涓鍙兘鏀跺埌澶氫釜鍖呫€?
            # 杩欓噷绠€鍗曠敤涓婁竴鏉?data 瀵硅薄瀵规瘮涔熷彲浠ワ紝浣嗕负浜嗘敮鎸?2s 閫昏緫锛屾垜浠線涓嬭蛋銆?
            pass

        # 1. 鎸囨爣寮曟搸鏍稿績: 5m 绾у埆婕旇繘 vs 2s 绾у埆棰勮
        if self._last_bar_ts is None:
            # 鍚姩鍚庣涓€涓?Tick锛屾寮忓垵濮嬪寲
            self.indicators.update(data, self.state, commit=True)
            self._last_bar_ts = data.timestamp
        elif data.timestamp > self._last_bar_ts:
            # 鍛ㄦ湡鍒囨崲 (姣斿浠?08:55 鍒颁簡 09:00)
            # 1.1 鍏堢敤涓婁竴鏍?Bar 鐨勬渶缁堟暟鎹?last_tick_data)姝ｅ紡閿佸畾涓婁竴鏍规寚鏍?
            if self._last_tick_data:
                self.indicators.update(self._last_tick_data, self.state, commit=True)
            # 1.2 鏇存柊褰撳墠鍩哄噯鏃堕棿
            self._last_bar_ts = data.timestamp
            
        # 2. 鏃犺鏄惁鍒囨崲锛屾瘡涓?Tick 閮借繘琛屸€滈瑙堣绠椻€濓紝纭繚 RSI 灞曠ず鍜岄鎺ф槸鏈€鏂扮殑
        self.indicators.update(data, self.state, commit=False)
        self._last_tick_data = data
        self._tick_count += 1

        # 3. 妫€鏌ュ弽杞繚鎶?(闃插畧浼樺厛)
        if not self.indicators.warmup_done:
            self._save_mini_state(data)
            return []
            
        # 3. 璁＄畻璐︽埛鎸佷粨涓庡眰鏁?(鎻愬墠鍒板喅绛栧墠锛岀‘淇濅簰鏂ュ垽鏂噯纭?
        pos_size = context.positions[self.symbol].size if context and self.symbol in context.positions else 0
        avg_price = context.positions[self.symbol].avg_price if pos_size > 0 else data.close
        current_layers = self._get_current_pos_layers(pos_size, avg_price)
        self.state.current_layers = current_layers

        # 4. 妫€鏌ュ弽杞繚鎶?(闃插畧浼樺厛)
        is_reversal = False
        rev_reason = RiskControllerV52.check_reversal(self.state, self.params, self._prev_state_mini)
        
        # 銆愪簰鏂ラ€昏緫銆戝鏋滃湪鍚屼竴 Bar 鍐呭凡缁忚秼鍔夸拱鍏ワ紝灞忚斀闈炵揣鎬ョ殑鍙嶈浆鍗栧嚭 (瑙ｅ喅绉掍拱绉掑崠)
        if rev_reason and self.state.last_buy_bar_ts == data.timestamp:
            if "RSI楠ら檷" not in rev_reason and "鏀鹃噺涓嬭穼" not in rev_reason:
                rev_reason = None # 杩囨护鎺?MACD/MA 鍣煶
        
        # 濡傛灉妫€娴嬪埌鍙嶈浆锛屽己鍒剁洰鏍囦粨浣嶅綊闆?(闃插畧浼樺厛)
        if rev_reason:
            self.state.target_layers = 0
            is_reversal = True
        else:
            self.state.trend_score = TrendScorerV52.calculate(self.state, self.params)
            
            # 銆愪簰鏂ラ€昏緫銆戝鏋滃湪鍚屼竴 Bar 鍐呭凡缁忓崠鍑猴紙鎴栧弽杞崠鍑猴級锛岄櫎闈炶鎯呭墽鍙橈紝鍚﹀垯涓嶇珛鍗充拱鍥?
            if self.state.last_sell_bar_ts == data.timestamp:
                self.state.target_layers = min(self.state.target_layers, current_layers) # 涓嶅厑璁稿湪杩欎釜 Bar 鍐呭鍔犲眰鏁?
            
            # 鏍规嵁璇勫垎鍐冲畾鐩爣灞傛暟涓庣綉鏍肩姸鎬?
            if self.state.trend_score >= self.params.get('trend_score_high', 4):
                self.state.target_layers = self.params.get('trend_target_high', 5)
                self.state.dynamic_grid = False 
                if self.state.grid_center is None: self.state.grid_center = data.close
            elif self.state.trend_score >= self.params.get('trend_score_mid', 2):
                self.state.target_layers = self.params.get('trend_target_mid', 3)
                self.state.dynamic_grid = True
            else:
                self.state.target_layers = self.params.get('trend_target_low', 1)
                self.state.dynamic_grid = True

        if pos_size > 0:
            # A. 鍙嶈浆淇濇姢 (宸茬粡璁＄畻杩?rev_reason)
            if is_reversal:
                # 鍐嶆纭 rev_reason 涓嶄负绌?(闃叉姢鎬х紪绋?
                if not rev_reason:
                    is_reversal = False
                else:
                    # 鍑忎粨閫昏緫 (鏍规嵁鏂囨。)
                    layers_to_sell = 2 if "RSI楠ら檷" in rev_reason else 1
                    
                    # 銆愬叧閿慨澶嶃€? 濡傛灉褰撳墠鎸佷粨鍝€曚笉瓒?1 灞?(濡?dust)锛屽湪鍙嶈浆淇濇姢鏃朵篃搴旇涓?1 灞備互渚挎竻绌?
                    eff_layers = max(1, current_layers)
                    actual_sell = min(layers_to_sell, eff_layers)
                    
                    if actual_sell > 0:
                        signals.append(self._make_signal(Side.SELL, actual_sell, data, f"鍙嶈浆淇濇姢:{rev_reason}", pos_size=pos_size))
                        current_layers -= actual_sell
        
            # B. 鍔ㄦ€佸垎鎵规鐩?
            tp_info = RiskControllerV52.check_take_profit(self.state, self.params)
            if tp_info and pos_size > 0:
                sell_num, idx = tp_info
                eff_layers = max(1, current_layers)
                actual_sell = min(sell_num, eff_layers)
                signals.append(self._make_signal(Side.SELL, actual_sell, data, f"闃舵姝㈢泩({idx}/3) RSI:{self.state.rsi_6:.1f}", pos_size=pos_size))
                current_layers -= actual_sell

        # 4. 瓒嬪娍寤轰粨閫昏緫
        if current_layers < self.state.target_layers:
            # 涔板叆淇″彿: 鏂囨。閫昏緫 - 寮鸿秼鍔挎斁瀹借嚦 55锛屽惁鍒欎娇鐢ㄩ厤缃?榛樿40)
            buy_thr = 55 if self.state.trend_score >= 4 else self.params.get('rsi_buy_threshold', 40)
            
            # 銆愪紭鍖栬ˉ鍏呫€? 濡傛灉褰撳墠鏄灞傚缓浠?鎸佷粨涓?)锛岀‖鎬ц姹?RSI < 45锛岄伩鍏嶅湪娉㈠嘲杩介珮鍐峰惎鍔?
            if current_layers == 0:
                buy_thr = min(buy_thr, 45)
                
            if self.state.rsi_6 < buy_thr:
                needed = self.state.target_layers - current_layers
                # 鏂囨。瑕佹眰: 涓€娆¤ˉ榻愬樊棰濈殑涓€鍗?(batch = max(1, needed // 2))
                batch = max(1, needed // 2)
                # 銆愬叧閿慨澶嶃€? 纭繚琛ヤ粨閲忎笉瓒呰繃鏈€澶ч檺鍒?
                batch = min(batch, self.params.get('max_positions', 5) - current_layers)
                
                if batch > 0:
                    # 銆愭姂鍒堕€昏緫銆戞鏌ユ槸鍚﹀湪鍚屼竴 Bar 涓斾环鏍兼尝鍔ㄤ笉瓒?
                    price_buff = self.params.get('signal_price_buffer', 0.005) # 榛樿 0.5%
                    is_duplicate = False
                    if self.state.last_buy_bar_ts == data.timestamp:
                        price_diff = abs(data.close - self.state.last_buy_price) / self.state.last_buy_price if self.state.last_buy_price > 0 else 1.0
                        if price_diff < price_buff:
                            is_duplicate = True
                    
                    if not is_duplicate:
                        signals.append(self._make_signal(Side.BUY, batch, data, f"瓒嬪娍寤轰粨(鍒?{self.state.trend_score})"))
                        current_layers += batch

        # 5. 缃戞牸杈呭姪 (浠呭湪闇囪崱/涓瓑瓒嬪娍涓?
        if self.state.dynamic_grid and self.state.grid_center and not signals:
            rng = self.params.get('grid_range_percent', 0.04)
            up = self.state.grid_center * (1 + rng)
            lo = self.state.grid_center * (1 - rng)
            
            if data.close > up and pos_size > 0:
                # 鍗栧嚭鍔犻攣鏍￠獙
                price_buff = self.params.get('signal_price_buffer', 0.005)
                if self.state.last_sell_bar_ts != data.timestamp or \
                   (self.state.last_sell_price > 0 and abs(data.close - self.state.last_sell_price)/self.state.last_sell_price > price_buff):
                    signals.append(self._make_signal(Side.SELL, 1, data, "缃戞牸涓婅建姝㈢泩", pos_size=pos_size))
                    self.state.grid_center = data.close # 绉诲姩缃戞牸
            elif data.close < lo and current_layers < self.params.get('max_positions', 5):
                # 涔板叆鍔犻攣鏍￠獙
                price_buff = self.params.get('signal_price_buffer', 0.005)
                if self.state.last_buy_bar_ts != data.timestamp or \
                   (self.state.last_buy_price > 0 and abs(data.close - self.state.last_buy_price)/self.state.last_buy_price > price_buff):
                    signals.append(self._make_signal(Side.BUY, 1, data, "缃戞牸涓嬭建琛ヤ粨"))
                    self.state.grid_center = data.close

        self._save_mini_state(data)
        return signals

    def _get_current_pos_layers(self, size: float, avg_price: float) -> int:
        if size <= 0: return 0
        layer_val = self.params.get('layer_size_usdt', 2000)
        # 鐢ㄣ€愭垚鏈€戣€岄潪銆愮幇浠枫€戣绠楀眰鏁帮紝鍥犱负灞傛暟浠ｈ〃璧勯噾鍗犵敤
        total_cost = size * avg_price
        # 浣跨敤 0.8 鐨勫亸绉绘潵闄嶄綆鍥犳墜缁垂瀵艰嚧鐨勮垗鍏ヨ宸紝纭繚 0.9 灞備篃琚涓?1 灞?
        return int((total_cost + layer_val * 0.2) // layer_val)

    def _make_signal(self, side: Side, layers: int, d: MarketData, reason: str, pos_size: float = 0) -> Signal:
        # 灏嗗眰鏁拌浆鎹负鍏蜂綋鐨勬暟閲?
        layer_val_usdt = self.params.get('layer_size_usdt', 2000)
        
        if side == Side.BUY:
            # 涔板崟浣跨敤鎶ヤ环甯侀噾棰?(USDT)锛岃缃?size_in_quote=True
            val = layers * layer_val_usdt
            sig = Signal(
                timestamp=d.timestamp,
                symbol=self.symbol,
                side=side,
                size=val,
                price=None,
                order_type=OrderType.MARKET,
                reason=reason,
                meta={'size_in_quote': True, 'layers': layers}
            )
            # 鏇存柊涔板叆璁板繂
            self.state.last_buy_price = d.close
            self.state.last_buy_bar_ts = d.timestamp
            return sig
        else:
            # 鍗栧崟: 姣斾緥鍑忎粨閫昏緫 (淇 insufficient_position)
            if pos_size <= 0: return None
            
            # 浣跨敤褰撳墠鐘舵€佺殑灞傛暟浣滀负鍩哄噯
            total_layers = max(1, self.state.current_layers)
            
            # 濡傛灉瑕佸崠鍑虹殑灞傛暟 >= 褰撳墠鎬诲眰鏁帮紝鎴栬€呮槸鏈€鍚庝竴灞傦紝鐩存帴娓呯┖
            if layers >= total_layers:
                qty = pos_size
            else:
                # 鎸夋瘮渚嬪噺浠擄紝渚嬪 3 灞傚噺 1 灞傦紝鍗栧嚭 1/3 鐨勬寔浠撴暟閲?
                qty = (layers / total_layers) * pos_size
            
            sig = Signal(
                timestamp=d.timestamp,
                symbol=self.symbol,
                side=side,
                size=qty,
                price=None,
                order_type=OrderType.MARKET,
                reason=reason,
                meta={'size_in_quote': False, 'layers': layers, 'value_usdt': layers * layer_val_usdt}
            )
            # 鏇存柊鍗栧嚭璁板繂
            self.state.last_sell_price = d.close
            self.state.last_sell_bar_ts = d.timestamp
            return sig

    def _save_mini_state(self, d: MarketData):
        self._prev_state_mini = {
            'ma5': self.state.ma5,
            'ma10': self.state.ma10,
            'histogram': self.state.histogram,
            'rsi_6': self.state.rsi_6,
            'price': d.close
        }
        self.state.last_candle = {'open': d.open, 'high': d.high, 'low': d.low, 'close': d.close, 'volume': d.volume}

    def _calculate_pivots(self) -> Dict[str, List[Dict[str, Any]]]:
        """璁＄畻灞€閮ㄦ尝娈甸珮浣庣偣 (Top 3)"""
        if len(self._data_buffer) < 15:
            return {'pivots_high': [], 'pivots_low': []}

        # 绠€鍗曡瘑鍒垎褰?(宸?鍙?)
        window = 3
        highs, lows = [], []
        data = list(self._data_buffer)
        
        for i in range(window, len(data) - window):
            curr = data[i]
            # 璇嗗埆楂樼偣
            if all(curr.high > data[i-j].high for j in range(1, window+1)) and \
               all(curr.high > data[i+j].high for j in range(1, window+1)):
                highs.append({'price': curr.high, 'time': curr.timestamp})
            # 璇嗗埆浣庣偣
            if all(curr.low < data[i-j].low for j in range(1, window+1)) and \
               all(curr.low < data[i+j].low for j in range(1, window+1)):
                lows.append({'price': curr.low, 'time': curr.timestamp})

        # 鍙栨渶杩戠殑鏈€鏄捐憲鐨?3 涓?
        pivots_high = sorted(highs, key=lambda x: x['price'], reverse=True)[:3]
        pivots_low = sorted(lows, key=lambda x: x['price'])[:3]
        return {'pivots_high': pivots_high, 'pivots_low': pivots_low}

    def get_status(self, context: StrategyContext = None) -> Dict[str, Any]:
        s, p = self.state, self.params
        # 璁＄畻缃戞牸绾夸緵 Dashboard 缁樺浘
        grid_lines = []
        if s.grid_center:
            rng = p.get('grid_range_percent', 0.04)
            up, lo = s.grid_center * (1 + rng), s.grid_center * (1 - rng)
            grid_lines = np.linspace(lo, up, p.get('max_positions', 5) + 1).tolist()

        # 杞崲瓒嬪娍寮哄害涓烘枃瀛?
        score_labels = {5: "鏋佸己鐖嗗彂", 4: "瓒嬪娍涓婅", 3: "鍋忓鏁寸悊", 2: "鍖洪棿闇囪崱", 1: "寮卞娍娑堣€?, 0: "鏋佸害浣庤糠"}
        trend_label = score_labels.get(s.trend_score, "绛夊緟鏁版嵁")

        return {
            # 绛栫暐鏍稿績鎸囨爣
            'trend_score': s.trend_score,
            'target_layers': s.target_layers,
            'position_count': s.current_layers,
            'signal_text': f"瓒嬪娍鍒?{s.trend_score} ({trend_label})",
            'signal_strength': f"{s.trend_score}/5",
            'signal_color': 'buy' if s.trend_score >= 3 else ('sell' if s.trend_score <= 1 else 'neutral'),
            
            # 鎶€鏈寚鏍囩粍浠?
            'current_rsi': s.rsi_6,
            'rsi_oversold': p.get('rsi_buy_threshold', 40),
            'rsi_overbought': p.get('rsi_sell_threshold', 65),
            'macd_trend': f"{'绾㈡煴' if s.histogram < 0 else '缁挎煴'}({s.histogram:.2f})",
            'macd': s.macd_line,
            'macdsignal': s.signal_line,
            'macdhist': s.histogram,
            'atrVal': (s.ma5 - s.ma10) if s.ma10 > 0 else 0, # 瀵归綈 Dashboard ID
            'marketRegime': "寮哄埗婊′粨妯″紡" if not s.dynamic_grid else "鍔ㄦ€佺綉鏍兼ā寮?, # 瀵归綈 Dashboard ID
            
            # 鎴愪氦閲忔墿灞?
            'current_volume': s.last_candle.get('volume', 0),
            'vol_ratio': s.vol_ratio,
            'vol_trend': f"閲忔瘮:{s.vol_ratio:.2f} ({'缂╅噺' if s.vol_ratio < 1.0 else ('鐖嗗彂' if s.vol_ratio > 1.3 else '姝ｅ父')})",
            
            # 缃戞牸鐘舵€?
            'grid_upper': grid_lines[-1] if grid_lines else 0,
            'grid_lower': grid_lines[0] if grid_lines else 0,
            'grid_lines': grid_lines,
            
            # 鎸佷粨璇︽儏鍏煎瀛楁
            'position_size': (context.positions[self.symbol].size if context and self.symbol in context.positions else 0),
            'position_avg_price': (context.positions[self.symbol].avg_price if context and self.symbol in context.positions else 0),
            'position_unrealized_pnl': (context.positions[self.symbol].unrealized_pnl if context and self.symbol in context.positions else 0),
            
            # 鍏冩暟鎹笌鍙傛暟
            'params': p,
            'param_metadata': self.param_metadata,
            'pivots': self._calculate_pivots()
        }
