"""
鍔ㄦ€佺綉鏍?RSI 策略 V5.2 - 全新重写鐗?
5分钟趋势确认 + 强制满仓 + 鍔ㄦ€佹鐩?+ 多重反转保护
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
# 1. 鐘舵€佷笌常量
# ============================================================

@dataclass
class StrategyState:
    # 核心持仓鐘舵€?
    current_layers: int = 0
    grid_center: Optional[float] = None
    dynamic_grid: bool = True
    
    # 指标数据
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
    
    # 历史记录 (用于 RSI 骤降判断绛?
    history_rsi_6: deque = field(default_factory=lambda: deque(maxlen=20))
    trend_score: int = 0
    target_layers: int = 0
    
    # 交易记录
    last_trade_ts: float = 0.0
    last_candle: Dict[str, Any] = field(default_factory=dict)
    
    # 【兼瀹规€цˉ鍏ㄣ€? 渚?LiveEngine 预热与画图使鐢?
    grid_upper: float = 0.0
    grid_lower: float = 0.0
    grid_prices: List[float] = field(default_factory=list)
    last_grid_update: int = 0
    
    # 信号抑制鐘舵€?
    last_buy_price: float = 0.0
    last_buy_bar_ts: Optional[datetime] = None
    last_sell_price: float = 0.0
    last_sell_bar_ts: Optional[datetime] = None
    
    @property
    def current_rsi(self) -> float:
        return self.rsi_6

# ============================================================
# 2. 楂樻€ц兘 O(1) 增量指标引擎
# ============================================================

class IncrementalIndicatorsV52:
    """增量计算 MACD, 多周鏈?RSI, MA, 成交閲?MA"""
    def __init__(self, p: dict):
        self.p = p
        self.count = 0
        self.prev_close = 0.0
        
        # MACD
        self.ema_12 = 0.0
        self.ema_26 = 0.0
        self.macd_sig = 0.0
        
        # RSI (6, 12, 24) - 使用 Wilder 平滑算法
        self.rsi_params = [
            {'p': p['rsi_period_shorter'], 'gain': 0.0, 'loss': 0.0, 'val': 50.0},
            {'p': p['rsi_period_medium'],  'gain': 0.0, 'loss': 0.0, 'val': 50.0},
            {'p': p['rsi_period_longer'],  'gain': 0.0, 'loss': 0.0, 'val': 50.0}
        ]
        
        # MA (5, 10) & Volume MA 20 - 使用 deque 维护窗口鍜?
        self.win_ma5 = deque(maxlen=5)
        self.win_ma10 = deque(maxlen=10)
        self.win_vol20 = deque(maxlen=20)
        self.sum_ma5 = 0.0
        self.sum_ma10 = 0.0
        self.sum_ma10 = 0.0
        self.sum_vol20 = 0.0

        # MACD 系数预计绠?(避免 update 中重复计绠?
        self.alpha_12 = 2.0 / (12 + 1)
        self.alpha_26 = 2.0 / (26 + 1)
        self.alpha_sig = 2.0 / (9 + 1)

    def update(self, d: MarketData, s: StrategyState, commit: bool = True):
        """
        计算并更新指鏍囥€?
        commit=True: 永久推进指标曲线 (用于 Bar 切换)
        commit=False: 仅计算当前预瑙堝€煎苟填入 s，不改变类内部的 EMA/MA 鐘舵€?(用于 Tick 更新)
        """
        c, v = d.close, d.volume
        
        # 1. MACD (12, 26, 9)
        alpha12, alpha26, alphasig = self.alpha_12, self.alpha_26, self.alpha_sig
        
        # 预览计算
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
            # 计算预览ƽ均涨跌
            tmp_gain = (item['gain'] * (period - 1) + gain) / period
            tmp_loss = (item['loss'] * (period - 1) + loss) / period
            rs = tmp_gain / tmp_loss if tmp_loss > 1e-9 else 100.0
            val = 100.0 - (100.0 / (1.0 + rs)) if tmp_loss > 1e-9 else 100.0
            tmp_rsi_results.append(val)
        
        # 3. MA (5, 10, 20)
        # 注意: 此处 MA 预览箢㻯处理，使用当前值替代窗口最鏃у€艰绠?
        tmp_ma5 = s.ma5 if not commit else 0 # 占位
        tmp_ma10 = s.ma10 if not commit else 0 # 占位
        
        # 写入鐘舵€?(预览)
        s.macd_line, s.signal_line, s.histogram = tmp_macd, tmp_sig, tmp_macd - tmp_sig
        s.rsi_6, s.rsi_12, s.rsi_24 = tmp_rsi_results
        
        # 如果鏄?commit 模式，则永久更新内部鐘舵€?
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
                
            # MA 窗口更新
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
        return self.count >= 25 # 覆盖鏈€闀?RSI 24

# ============================================================
# 3. 核心逻辑引擎 (Scorer, Risk, Grid)
# ============================================================

class TrendScorerV52:
    @staticmethod
    def calculate(s: StrategyState, p: Dict[str, Any]) -> int:
        score = 0
        
        # 1. MACD (文档逻辑: MACD > Signal 涓?MACD > 0 绉?2 鍒? 浠?MACD > Signal 绉?1 鍒?
        if s.macd_line > s.signal_line:
            if s.macd_line > 0:
                score += 2
            else:
                score += 1
                
        # 2. RSI 分层 (文档逻辑: RSI1 < 40 绉?2 鍒? RSI1 < 50 绉?1 鍒? RSI3 > 50 额外绉?1 鍒?
        # 注意: 文档涓?RSI1 对应 short (6), RSI3 对应 long (24)
        if s.rsi_6 < 40:
            score += 2
        elif s.rsi_6 < 50:
            score += 1
            
        if s.rsi_24 > 50:
            score += 1
            
        # 3. 成交閲?(文档逻辑: Vol > MA20 * 1.3 绉?1 鍒?
        vol_thr = p.get('volume_threshold', 1.3)
        if s.vol_ratio > vol_thr:
            score += 1
            
        return min(score, 5)

class RiskControllerV52:
    @staticmethod
    def check_reversal(s: StrategyState, p: Dict[str, Any], prev_s: Dict[str, Any]) -> str:
        if not prev_s: return None
        
        # 1. MA 交叉 (MA5 下穿 MA10) -> 鍑?2 灞?
        if s.ma5 < s.ma10 and prev_s.get('ma5', 0) >= prev_s.get('ma10', 0):
            return "MA5下穿MA10"
            
        # 2. MACD 死叉 (MACD < Signal 涓?MACD > 0) -> 鍑?1 灞?
        if s.macd_line < s.signal_line and s.macd_line > 0:
            # 【优化补鍏呫€? 如果当ǰ是强趋势(Score>=4)，忽鐣?MACD 死叉以免被频繁洗出，信任 MA 鍜?RSI 骤降
            if s.trend_score >= 4:
                return None
            
            if prev_s.get('macd_line', 0) >= prev_s.get('signal_line', 0):
                return "MACD死叉"
                
        # 3. RSI 骤降 (1小时鍗?2根线内跌骞?> 15) -> 鍑?2 灞?
        # 逻辑：需瑕?state 中维护历鍙?RSI。若未实װ，暂时用简化版銆?
        # 已经鍦?state 中有浜?rsi_history_1h 鐨勯€昏緫銆?
        if len(s.history_rsi_6) >= 12:
            old_rsi = s.history_rsi_6[0]
            if old_rsi - s.rsi_6 > p.get('stop_loss_rsi_drop', 15):
                return f"RSI骤降({old_rsi-s.rsi_6:.1f})"
                
        # 4. 放量下跌 (文档逻辑: 量比 > 1.5 且价格收闃?
        if s.vol_ratio > p.get('stop_loss_volume_spike', 1.5) and s.last_candle.get('close', 0) < s.last_candle.get('open', 0):
            return "放量下跌"
            
        return None

    @staticmethod
    def check_take_profit(s: StrategyState, p: dict) -> Optional[Tuple[int, int]]:
        """阶梯止盈层数判断: 返回 (卖出层数, 阶梯索引)"""
        if not p.get('take_profit_enable'): return None
        levels = p['take_profit_rsi_levels']
        layers = p['take_profit_sell_layers']
        
        # 从高到低妫€查，只触发最高的那一绾?
        for i in range(len(levels) - 1, -1, -1):
            if s.rsi_6 > levels[i]:
                return layers[i], i + 1
        return None

# ============================================================
# 5. 策略主类集成
# ============================================================

class GridRSIStrategyV5_2(BaseStrategy):
    def __init__(self, symbol: str = "BTC-USDT", config_path: str = None, **kwargs):
        super().__init__(name=kwargs.get("name", "GridRSI_V5.2_TrendForce"), **kwargs)
        self.symbol = symbol
        
        # 鍔ㄦ€佸畾位核心配置目褰?(兼容 Arena 鍜?Live 模式)
        current_file_dir = Path(__file__).parent.resolve()
        self.config_dir = current_file_dir.parent / "config"
        self.default_config_path = self.config_dir / "grid_v52_default.json"
        
        # 兼容性处理：如果 runtime 不存在，则使鐢?default
        self.runtime_config_path = self.config_dir / "grid_v52_runtime.json"
        self.active_config_path = Path(config_path) if config_path else self.runtime_config_path
        if not self.active_config_path.exists():
            self.active_config_path = self.default_config_path
            
        # 兼容别名: 渚?Runner 识别
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
        self._last_signal_time = None # 信号风暴保护: ͬһ个时间戳(Bar)只处理一次信鍙?
        self._last_bar_ts = None # Bar 切换妫€娴?
        self._last_tick_data = None
        
    def reload_config(self, force=False):
        """加载或热重载配置 (支持鐢?Runner 外部显式触发，移除轮璇?"""
        # 1. 先载入保底默认配缃?(如果存在)
        if self.default_config_path.exists():
            try:
                with open(self.default_config_path, 'r', encoding='utf-8') as f:
                    self.params.update(json.load(f))
            except: pass
        
        # 2. 载入当前活动的配缃?(runtime)
        if self.active_config_path.exists():
            try:
                mtime = self.active_config_path.stat().st_mtime
                if mtime > self._last_config_mtime or force:
                    with open(self.active_config_path, 'r', encoding='utf-8') as f:
                        self.params.update(json.load(f))
                    self._last_config_mtime = mtime

                    # 3. 载入 UI 元数鎹?
                    meta_file = self.config_dir / "grid_v52_meta.json"
                    if meta_file.exists():
                        with open(meta_file, 'r', encoding='utf-8') as f:
                            self.param_metadata = json.load(f)
                    
                    print(f"[V5.2] 配置重载成功: {self.active_config_path.name}")
            except Exception as e:
                print(f"[V5.2] 重载配置失败: {e}")

    def warmup(self, data_list: List[MarketData]):
        """[标准接口] 实现高效预热与网格初始化"""
        if not data_list: return
        
        print(f"[V5.2] 正在处理 {len(data_list)} 根历鍙?K 线进行ָ标预鐑?..")
        for data in data_list:
            # 1. 更新内部缓存 (用于 Dashboard 历史记录)
            self._data_buffer.append(data)
            # 2. 推进指标计算 (commit=True)
            self.indicators.update(data, self.state, commit=True)
            # 3. 更新迷你鐘舵€佷緵下次对比
            self._save_mini_state(data)
            
        # 4. 自动初始化网鏍?(替代鍘?Engine 中的硬编鐮侀€昏緫)
        last_price = data_list[-1].close
        rng = self.params.get('grid_range_percent', 0.04)
        self.state.grid_center = last_price
        self.state.grid_upper = last_price * (1 + rng)
        self.state.grid_lower = last_price * (1 - rng)
        
        # 计算网格鐐?(兼容旧版鐘舵€佹樉绀?
        levels = self.params.get('max_positions', 5)
        self.state.grid_prices = np.linspace(self.state.grid_lower, self.state.grid_upper, levels + 1).tolist()
        self.state.last_grid_update = len(self._data_buffer)
        
        print(f"  [OK] 指标预热完成，网格已锚定鍦? {last_price:.2f}")

    def on_data(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        signals = []
        
        # 0. 信号风暴保护 (同一涓?Tick 不发多单，保留基纭€逻辑)
        if self._last_signal_time == data.timestamp and self._tick_count > 0:
            # 注意: 如果是实鏃?Tick 内部，同涓€个秒可能收到多个鍖呫€?
            # 这里箢㵥用上一鏉?data 对象对比也可以，但为了支鎸?2s 逻辑，我们往下走銆?
            pass

        # 1. 指标引擎核心: 5m 级别演进 vs 2s 级别预览
        if self._last_bar_ts is None:
            # 启动后第涓€涓?Tick，正式初始化
            self.indicators.update(data, self.state, commit=True)
            self._last_bar_ts = data.timestamp
        elif data.timestamp > self._last_bar_ts:
            # 周期切换 (比如浠?08:55 到了 09:00)
            # 1.1 先用上一鏍?Bar 的最终数鎹?last_tick_data)正式锁定上一根指鏍?
            if self._last_tick_data:
                self.indicators.update(self._last_tick_data, self.state, commit=True)
            # 1.2 更新当前基准时间
            self._last_bar_ts = data.timestamp
            
        # 2. 无论是否切换，每涓?Tick 都进琛屸€滈览计绠椻€濓紝确保 RSI չʾ和风控是鏈€新的
        self.indicators.update(data, self.state, commit=False)
        self._last_tick_data = data
        self._tick_count += 1

        # 3. 妫€查反转保鎶?(防守优先)
        if not self.indicators.warmup_done:
            self._save_mini_state(data)
            return []
            
        # 3. 计算账户持仓与层鏁?(提前到决策前，确保互斥判断准纭?
        pos_size = context.positions[self.symbol].size if context and self.symbol in context.positions else 0
        avg_price = context.positions[self.symbol].avg_price if pos_size > 0 else data.close
        current_layers = self._get_current_pos_layers(pos_size, avg_price)
        self.state.current_layers = current_layers

        # 4. 妫€查反转保鎶?(防守优先)
        is_reversal = False
        rev_reason = RiskControllerV52.check_reversal(self.state, self.params, self._prev_state_mini)
        
        # 【互鏂ラ€昏緫】如果在同一 Bar 内已经趋势买入，屏蔽非紧急的反转卖出 (解决秒买秒卖)
        if rev_reason and self.state.last_buy_bar_ts == data.timestamp:
            if "RSI骤降" not in rev_reason and "放量下跌" not in rev_reason:
                rev_reason = None # 过滤鎺?MACD/MA 噪音
        
        # 如果妫€测到反转，强制目标仓位归闆?(防守优先)
        if rev_reason:
            self.state.target_layers = 0
            is_reversal = True
        else:
            self.state.trend_score = TrendScorerV52.calculate(self.state, self.params)
            
            # 【互鏂ラ€昏緫】如果在同一 Bar 内已经卖出（或反转卖出），除非行情剧变，否则不立即买鍥?
            if self.state.last_sell_bar_ts == data.timestamp:
                self.state.target_layers = min(self.state.target_layers, current_layers) # 不允许在这个 Bar 内增加层鏁?
            
            # 根据评分决定目标层数与网格状鎬?
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
            # A. 反转保护 (已经计算杩?rev_reason)
            if is_reversal:
                # 再次确认 rev_reason 不为绌?(防护性编绋?
                if not rev_reason:
                    is_reversal = False
                else:
                    # 减仓逻辑 (根据文档)
                    layers_to_sell = 2 if "RSI骤降" in rev_reason else 1
                    
                    # 【关键修澶嶃€? 如果当前持仓鍝€曚笉瓒?1 灞?(濡?dust)，在反转保护时Ҳ应视涓?1 层以便清绌?
                    eff_layers = max(1, current_layers)
                    actual_sell = min(layers_to_sell, eff_layers)
                    
                    if actual_sell > 0:
                        signals.append(self._make_signal(Side.SELL, actual_sell, data, f"反转保护:{rev_reason}", pos_size=pos_size))
                        current_layers -= actual_sell
        
            # B. 鍔ㄦ€佸垎批止鐩?
            tp_info = RiskControllerV52.check_take_profit(self.state, self.params)
            if tp_info and pos_size > 0:
                sell_num, idx = tp_info
                eff_layers = max(1, current_layers)
                actual_sell = min(sell_num, eff_layers)
                signals.append(self._make_signal(Side.SELL, actual_sell, data, f"阶梯止盈({idx}/3) RSI:{self.state.rsi_6:.1f}", pos_size=pos_size))
                current_layers -= actual_sell

        # 4. 趋势建仓逻辑
        if current_layers < self.state.target_layers:
            # 买入信号: 文档逻辑 - 强趋势放宽至 55，否则使用配缃?默认40)
            buy_thr = 55 if self.state.trend_score >= 4 else self.params.get('rsi_buy_threshold', 40)
            
            # 【优化补鍏呫€? 如果当ǰ是首层建浠?持仓涓?)，Ӳ性要姹?RSI < 45，避免在波峰追高冷启鍔?
            if current_layers == 0:
                buy_thr = min(buy_thr, 45)
                
            if self.state.rsi_6 < buy_thr:
                needed = self.state.target_layers - current_layers
                # 文档要求: 涓€次补齐差额的涓€鍗?(batch = max(1, needed // 2))
                batch = max(1, needed // 2)
                # 【关键修澶嶃€? 确保补仓量不超过鏈€大限鍒?
                batch = min(batch, self.params.get('max_positions', 5) - current_layers)
                
                if batch > 0:
                    # 【抑鍒堕€昏緫】检查是否在同一 Bar 且价格波动不瓒?
                    price_buff = self.params.get('signal_price_buffer', 0.005) # 默认 0.5%
                    is_duplicate = False
                    if self.state.last_buy_bar_ts == data.timestamp:
                        price_diff = abs(data.close - self.state.last_buy_price) / self.state.last_buy_price if self.state.last_buy_price > 0 else 1.0
                        if price_diff < price_buff:
                            is_duplicate = True
                    
                    if not is_duplicate:
                        signals.append(self._make_signal(Side.BUY, batch, data, f"趋势建仓(鍒?{self.state.trend_score})"))
                        current_layers += batch

        # 5. 网格辅助 (仅在震荡/中等趋势涓?
        if self.state.dynamic_grid and self.state.grid_center and not signals:
            rng = self.params.get('grid_range_percent', 0.04)
            up = self.state.grid_center * (1 + rng)
            lo = self.state.grid_center * (1 - rng)
            
            if data.close > up and pos_size > 0:
                # 卖出加锁校验
                price_buff = self.params.get('signal_price_buffer', 0.005)
                if self.state.last_sell_bar_ts != data.timestamp or \
                   (self.state.last_sell_price > 0 and abs(data.close - self.state.last_sell_price)/self.state.last_sell_price > price_buff):
                    signals.append(self._make_signal(Side.SELL, 1, data, "网格上轨止盈", pos_size=pos_size))
                    self.state.grid_center = data.close # 移动网格
            elif data.close < lo and current_layers < self.params.get('max_positions', 5):
                # 买入加锁校验
                price_buff = self.params.get('signal_price_buffer', 0.005)
                if self.state.last_buy_bar_ts != data.timestamp or \
                   (self.state.last_buy_price > 0 and abs(data.close - self.state.last_buy_price)/self.state.last_buy_price > price_buff):
                    signals.append(self._make_signal(Side.BUY, 1, data, "网格下轨补仓"))
                    self.state.grid_center = data.close

        self._save_mini_state(data)
        return signals

    def _get_current_pos_layers(self, size: float, avg_price: float) -> int:
        if size <= 0: return 0
        layer_val = self.params.get('layer_size_usdt', 2000)
        # 鐢ㄣ€愭垚鏈€戣€岄潪【现浠枫€戣算层数，因为层数代表资金占用
        total_cost = size * avg_price
        # 使用 0.8 的偏移来降低因手续费导致的舍入误差，确保 0.9 层Ҳ被视涓?1 灞?
        return int((total_cost + layer_val * 0.2) // layer_val)

    def _make_signal(self, side: Side, layers: int, d: MarketData, reason: str, pos_size: float = 0) -> Signal:
        # 将层数ת换为具体的数閲?
        layer_val_usdt = self.params.get('layer_size_usdt', 2000)
        
        if side == Side.BUY:
            # 买单使用报价币金棰?(USDT)，设缃?size_in_quote=True
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
            # 更新买入记忆
            self.state.last_buy_price = d.close
            self.state.last_buy_bar_ts = d.timestamp
            return sig
        else:
            # 卖单: 比例减仓逻辑 (修复 insufficient_position)
            if pos_size <= 0: return None
            
            # 使用当前鐘舵€佺殑层数作为基准
            total_layers = max(1, self.state.current_layers)
            
            # 如果要卖出的层数 >= 当前总层数，鎴栬€呮槸鏈€后一层，直接清空
            if layers >= total_layers:
                qty = pos_size
            else:
                # 按比例减仓，例如 3 层减 1 层，卖出 1/3 的持仓数閲?
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
            # 更新卖出记忆
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
        """计算屢㲿波段高低点 (Top 3)"""
        if len(self._data_buffer) < 15:
            return {'pivots_high': [], 'pivots_low': []}

        # 箢㵥ʶ别分褰?(宸?鍙?)
        window = 3
        highs, lows = [], []
        data = list(self._data_buffer)
        
        for i in range(window, len(data) - window):
            curr = data[i]
            # 识别高点
            if all(curr.high > data[i-j].high for j in range(1, window+1)) and \
               all(curr.high > data[i+j].high for j in range(1, window+1)):
                highs.append({'price': curr.high, 'time': curr.timestamp})
            # 识别低点
            if all(curr.low < data[i-j].low for j in range(1, window+1)) and \
               all(curr.low < data[i+j].low for j in range(1, window+1)):
                lows.append({'price': curr.low, 'time': curr.timestamp})

        # 取最近的鏈€显著鐨?3 涓?
        pivots_high = sorted(highs, key=lambda x: x['price'], reverse=True)[:3]
        pivots_low = sorted(lows, key=lambda x: x['price'])[:3]
        return {'pivots_high': pivots_high, 'pivots_low': pivots_low}

    def get_status(self, context: StrategyContext = None) -> Dict[str, Any]:
        s, p = self.state, self.params
        # 计算网格线供 Dashboard 绘图
        grid_lines = []
        if s.grid_center:
            rng = p.get('grid_range_percent', 0.04)
            up, lo = s.grid_center * (1 + rng), s.grid_center * (1 - rng)
            grid_lines = np.linspace(lo, up, p.get('max_positions', 5) + 1).tolist()

        # 转换趋势强度为文瀛?
        score_labels = {5: "极强爆发", 4: "趋势上行", 3: "偏多整理", 2: "区间震荡", 1: "弱势娑堣€?, 0: "极度低迷"}
        trend_label = score_labels.get(s.trend_score, "等待数据")

        return {
            # 策略核心指标
            'trend_score': s.trend_score,
            'target_layers': s.target_layers,
            'position_count': s.current_layers,
            'signal_text': f"趋势鍒?{s.trend_score} ({trend_label})",
            'signal_strength': f"{s.trend_score}/5",
            'signal_color': 'buy' if s.trend_score >= 3 else ('sell' if s.trend_score <= 1 else 'neutral'),
            
            # 鎶€术指标组浠?
            'current_rsi': s.rsi_6,
            'rsi_oversold': p.get('rsi_buy_threshold', 40),
            'rsi_overbought': p.get('rsi_sell_threshold', 65),
            'macd_trend': f"{'红柱' if s.histogram < 0 else '绿柱'}({s.histogram:.2f})",
            'macd': s.macd_line,
            'macdsignal': s.signal_line,
            'macdhist': s.histogram,
            'atrVal': (s.ma5 - s.ma10) if s.ma10 > 0 else 0, # 对齐 Dashboard ID
            'marketRegime': "强制满仓模式" if not s.dynamic_grid else "鍔ㄦ€佺綉格模寮?, # 对齐 Dashboard ID
            
            # 成交量扩灞?
            'current_volume': s.last_candle.get('volume', 0),
            'vol_ratio': s.vol_ratio,
            'vol_trend': f"量比:{s.vol_ratio:.2f} ({'缩量' if s.vol_ratio < 1.0 else ('爆发' if s.vol_ratio > 1.3 else '正常')})",
            
            # 网格鐘舵€?
            'grid_upper': grid_lines[-1] if grid_lines else 0,
            'grid_lower': grid_lines[0] if grid_lines else 0,
            'grid_lines': grid_lines,
            
            # 持仓详情兼容字段
            'position_size': (context.positions[self.symbol].size if context and self.symbol in context.positions else 0),
            'position_avg_price': (context.positions[self.symbol].avg_price if context and self.symbol in context.positions else 0),
            'position_unrealized_pnl': (context.positions[self.symbol].unrealized_pnl if context and self.symbol in context.positions else 0),
            
            # 元数据与参数
            'params': p,
            'param_metadata': self.param_metadata,
            'pivots': self._calculate_pivots()
        }
