"""
动态网格 RSI 策略 V5.2 - 全新重写版
5分钟趋势确认 + 强制满仓 + 动态止盈 + 多重反转保护
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
from core import (
    Signal, MarketData, StrategyContext, FillEvent,
    Side, OrderType, MarketRegime
)
from .base import BaseStrategy

# ============================================================
# 1. 状态与常量
# ============================================================

@dataclass
class StrategyState:
    # 核心持仓状态
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
    
    # 历史记录 (用于 RSI 骤降判断等)
    history_rsi_6: deque = field(default_factory=lambda: deque(maxlen=20))
    trend_score: int = 0
    target_layers: int = 0
    
    # 交易记录
    last_trade_ts: float = 0.0
    last_candle: Dict[str, Any] = field(default_factory=dict)
    
    # 【兼容性补全】: 供 LiveEngine 预热与画图使用
    grid_upper: float = 0.0
    grid_lower: float = 0.0
    grid_prices: List[float] = field(default_factory=list)
    last_grid_update: int = 0
    
    # 信号抑制状态
    last_buy_price: float = 0.0
    last_buy_bar_ts: Optional[datetime] = None
    last_sell_price: float = 0.0
    last_sell_bar_ts: Optional[datetime] = None
    
    @property
    def current_rsi(self) -> float:
        return self.rsi_6

# ============================================================
# 2. 高性能 O(1) 增量指标引擎
# ============================================================

class IncrementalIndicatorsV52:
    """增量计算 MACD, 多周期 RSI, MA, 成交量 MA"""
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
        
        # MA (5, 10) & Volume MA 20 - 使用 deque 维护窗口和
        self.win_ma5 = deque(maxlen=5)
        self.win_ma10 = deque(maxlen=10)
        self.win_vol20 = deque(maxlen=20)
        self.sum_ma5 = 0.0
        self.sum_ma10 = 0.0
        self.sum_ma10 = 0.0
        self.sum_vol20 = 0.0

        # MACD 系数预计算 (避免 update 中重复计算)
        self.alpha_12 = 2.0 / (12 + 1)
        self.alpha_26 = 2.0 / (26 + 1)
        self.alpha_sig = 2.0 / (9 + 1)

    def update(self, d: MarketData, s: StrategyState, commit: bool = True):
        """
        计算并更新指标。
        commit=True: 永久推进指标曲线 (用于 Bar 切换)
        commit=False: 仅计算当前预览值并填入 s，不改变类内部的 EMA/MA 状态 (用于 Tick 更新)
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
            # 计算预览平均涨跌
            tmp_gain = (item['gain'] * (period - 1) + gain) / period
            tmp_loss = (item['loss'] * (period - 1) + loss) / period
            rs = tmp_gain / tmp_loss if tmp_loss > 1e-9 else 100.0
            val = 100.0 - (100.0 / (1.0 + rs)) if tmp_loss > 1e-9 else 100.0
            tmp_rsi_results.append(val)
        
        # 3. MA (5, 10, 20)
        # 注意: 此处 MA 预览简化处理，使用当前值替代窗口最旧值计算
        tmp_ma5 = s.ma5 if not commit else 0 # 占位
        tmp_ma10 = s.ma10 if not commit else 0 # 占位
        
        # 写入状态 (预览)
        s.macd_line, s.signal_line, s.histogram = tmp_macd, tmp_sig, tmp_macd - tmp_sig
        s.rsi_6, s.rsi_12, s.rsi_24 = tmp_rsi_results
        
        # 如果是 commit 模式，则永久更新内部状态
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
        return self.count >= 25 # 覆盖最长 RSI 24

# ============================================================
# 3. 核心逻辑引擎 (Scorer, Risk, Grid)
# ============================================================

class TrendScorerV52:
    @staticmethod
    def calculate(s: StrategyState, p: Dict[str, Any]) -> int:
        score = 0
        
        # 1. MACD (文档逻辑: MACD > Signal 且 MACD > 0 积 2 分; 仅 MACD > Signal 积 1 分)
        if s.macd_line > s.signal_line:
            if s.macd_line > 0:
                score += 2
            else:
                score += 1
                
        # 2. RSI 分层 (文档逻辑: RSI1 < 40 积 2 分; RSI1 < 50 积 1 分; RSI3 > 50 额外积 1 分)
        # 注意: 文档中 RSI1 对应 short (6), RSI3 对应 long (24)
        if s.rsi_6 < 40:
            score += 2
        elif s.rsi_6 < 50:
            score += 1
            
        if s.rsi_24 > 50:
            score += 1
            
        # 3. 成交量 (文档逻辑: Vol > MA20 * 1.3 积 1 分)
        vol_thr = p.get('volume_threshold', 1.3)
        if s.vol_ratio > vol_thr:
            score += 1
            
        return min(score, 5)

class RiskControllerV52:
    @staticmethod
    def check_reversal(s: StrategyState, p: Dict[str, Any], prev_s: Dict[str, Any]) -> str:
        if not prev_s: return None
        
        # 1. MA 交叉 (MA5 下穿 MA10) -> 减 2 层
        if s.ma5 < s.ma10 and prev_s.get('ma5', 0) >= prev_s.get('ma10', 0):
            return "MA5下穿MA10"
            
        # 2. MACD 死叉 (MACD < Signal 且 MACD > 0) -> 减 1 层
        if s.macd_line < s.signal_line and s.macd_line > 0:
            # 【优化补充】: 如果当前是强趋势(Score>=4)，忽略 MACD 死叉以免被频繁洗出，信任 MA 和 RSI 骤降
            if s.trend_score >= 4:
                return None
            
            if prev_s.get('macd_line', 0) >= prev_s.get('signal_line', 0):
                return "MACD死叉"
                
        # 3. RSI 骤降 (1小时即12根线内跌幅 > 15) -> 减 2 层
        # 逻辑：需要 state 中维护历史 RSI。若未实装，暂时用简化版。
        # 已经在 state 中有了 rsi_history_1h 的逻辑。
        if len(s.history_rsi_6) >= 12:
            old_rsi = s.history_rsi_6[0]
            if old_rsi - s.rsi_6 > p.get('stop_loss_rsi_drop', 15):
                return f"RSI骤降({old_rsi-s.rsi_6:.1f})"
                
        # 4. 放量下跌 (文档逻辑: 量比 > 1.5 且价格收阴)
        if s.vol_ratio > p.get('stop_loss_volume_spike', 1.5) and s.last_candle.get('close', 0) < s.last_candle.get('open', 0):
            return "放量下跌"
            
        return None

    @staticmethod
    def check_take_profit(s: StrategyState, p: dict) -> Optional[Tuple[int, int]]:
        """阶梯止盈层数判断: 返回 (卖出层数, 阶梯索引)"""
        if not p.get('take_profit_enable'): return None
        levels = p['take_profit_rsi_levels']
        layers = p['take_profit_sell_layers']
        
        # 从高到低检查，只触发最高的那一级
        for i in range(len(levels) - 1, -1, -1):
            if s.rsi_6 > levels[i]:
                return layers[i], i + 1
        return None

# ============================================================
# 5. 策略主类集成
# ============================================================

class GridRSIStrategyV5_2(BaseStrategy):
    def __init__(self, symbol: str = "BTC-USDT", config_path: str = None):
        super().__init__(name="GridRSI_V5.2_TrendForce")
        self.symbol = symbol
        
        # 统一路径: 优先使用 config 目录下的 V5.2 配置文件
        # 注意：此处使用相对路径或从环境变量获取会更好，但为了稳妥先用绝对路径
        self.config_dir = Path(r"c:\CS\grid_multi\config")
        self.default_config_path = self.config_dir / "grid_v52_default.json"
        
        # 兼容性处理：如果 runtime 不存在，则使用 default
        self.runtime_config_path = self.config_dir / "grid_v52_runtime.json"
        self.active_config_path = Path(config_path) if config_path else self.runtime_config_path
        if not self.active_config_path.exists():
            self.active_config_path = self.default_config_path
            
        # 兼容别名: 供 Runner 识别
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
        self._last_signal_time = None # 信号风暴保护: 同一个时间戳(Bar)只处理一次信号
        self._last_bar_ts = None # Bar 切换检测
        self._last_tick_data = None
        
    def reload_config(self, force=False):
        """加载或热重载配置 (支持由 Runner 外部显式触发，移除轮询)"""
        # 1. 先载入保底默认配置 (如果存在)
        if self.default_config_path.exists():
            try:
                with open(self.default_config_path, 'r', encoding='utf-8') as f:
                    self.params.update(json.load(f))
            except: pass
        
        # 2. 载入当前活动的配置 (runtime)
        if self.active_config_path.exists():
            try:
                mtime = self.active_config_path.stat().st_mtime
                if mtime > self._last_config_mtime or force:
                    with open(self.active_config_path, 'r', encoding='utf-8') as f:
                        self.params.update(json.load(f))
                    self._last_config_mtime = mtime

                    # 3. 载入 UI 元数据
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
        
        print(f"[V5.2] 正在处理 {len(data_list)} 根历史 K 线进行指标预热...")
        for data in data_list:
            # 1. 更新内部缓存 (用于 Dashboard 历史记录)
            self._data_buffer.append(data)
            # 2. 推进指标计算 (commit=True)
            self.indicators.update(data, self.state, commit=True)
            # 3. 更新迷你状态供下次对比
            self._save_mini_state(data)
            
        # 4. 自动初始化网格 (替代原 Engine 中的硬编码逻辑)
        last_price = data_list[-1].close
        rng = self.params.get('grid_range_percent', 0.04)
        self.state.grid_center = last_price
        self.state.grid_upper = last_price * (1 + rng)
        self.state.grid_lower = last_price * (1 - rng)
        
        # 计算网格点 (兼容旧版状态显示)
        levels = self.params.get('max_positions', 5)
        self.state.grid_prices = np.linspace(self.state.grid_lower, self.state.grid_upper, levels + 1).tolist()
        self.state.last_grid_update = len(self._data_buffer)
        
        print(f"  [OK] 指标预热完成，网格已锚定在: {last_price:.2f}")

    def on_data(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        signals = []
        
        # 0. 信号风暴保护 (同一个 Tick 不发多单，保留基础逻辑)
        if self._last_signal_time == data.timestamp and self._tick_count > 0:
            # 注意: 如果是实时 Tick 内部，同一个秒可能收到多个包。
            # 这里简单用上一条 data 对象对比也可以，但为了支持 2s 逻辑，我们往下走。
            pass

        # 1. 指标引擎核心: 5m 级别演进 vs 2s 级别预览
        if self._last_bar_ts is None:
            # 启动后第一个 Tick，正式初始化
            self.indicators.update(data, self.state, commit=True)
            self._last_bar_ts = data.timestamp
        elif data.timestamp > self._last_bar_ts:
            # 周期切换 (比如从 08:55 到了 09:00)
            # 1.1 先用上一根 Bar 的最终数据(last_tick_data)正式锁定上一根指标
            if self._last_tick_data:
                self.indicators.update(self._last_tick_data, self.state, commit=True)
            # 1.2 更新当前基准时间
            self._last_bar_ts = data.timestamp
            
        # 2. 无论是否切换，每个 Tick 都进行“预览计算”，确保 RSI 展示和风控是最新的
        self.indicators.update(data, self.state, commit=False)
        self._last_tick_data = data
        self._tick_count += 1

        # 3. 检查反转保护 (防守优先)
        if not self.indicators.warmup_done:
            self._save_mini_state(data)
            return []
            
        # 3. 计算账户持仓与层数 (提前到决策前，确保互斥判断准确)
        pos_size = context.positions[self.symbol].size if context and self.symbol in context.positions else 0
        avg_price = context.positions[self.symbol].avg_price if pos_size > 0 else data.close
        current_layers = self._get_current_pos_layers(pos_size, avg_price)
        self.state.current_layers = current_layers

        # 4. 检查反转保护 (防守优先)
        is_reversal = False
        rev_reason = RiskControllerV52.check_reversal(self.state, self.params, self._prev_state_mini)
        
        # 【互斥逻辑】如果在同一 Bar 内已经趋势买入，屏蔽非紧急的反转卖出 (解决秒买秒卖)
        if rev_reason and self.state.last_buy_bar_ts == data.timestamp:
            if "RSI骤降" not in rev_reason and "放量下跌" not in rev_reason:
                rev_reason = None # 过滤掉 MACD/MA 噪音
        
        # 如果检测到反转，强制目标仓位归零 (防守优先)
        if rev_reason:
            self.state.target_layers = 0
            is_reversal = True
        else:
            self.state.trend_score = TrendScorerV52.calculate(self.state, self.params)
            
            # 【互斥逻辑】如果在同一 Bar 内已经卖出（或反转卖出），除非行情剧变，否则不立即买回
            if self.state.last_sell_bar_ts == data.timestamp:
                self.state.target_layers = min(self.state.target_layers, current_layers) # 不允许在这个 Bar 内增加层数
            
            # 根据评分决定目标层数与网格状态
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
            # A. 反转保护 (已经计算过 rev_reason)
            if is_reversal:
                # 再次确认 rev_reason 不为空 (防护性编程)
                if not rev_reason:
                    is_reversal = False
                else:
                    # 减仓逻辑 (根据文档)
                    layers_to_sell = 2 if "RSI骤降" in rev_reason else 1
                    
                    # 【关键修复】: 如果当前持仓哪怕不足 1 层 (如 dust)，在反转保护时也应视为 1 层以便清空
                    eff_layers = max(1, current_layers)
                    actual_sell = min(layers_to_sell, eff_layers)
                    
                    if actual_sell > 0:
                        signals.append(self._make_signal(Side.SELL, actual_sell, data, f"反转保护:{rev_reason}", pos_size=pos_size))
                        current_layers -= actual_sell
        
            # B. 动态分批止盈
            tp_info = RiskControllerV52.check_take_profit(self.state, self.params)
            if tp_info and pos_size > 0:
                sell_num, idx = tp_info
                eff_layers = max(1, current_layers)
                actual_sell = min(sell_num, eff_layers)
                signals.append(self._make_signal(Side.SELL, actual_sell, data, f"阶梯止盈({idx}/3) RSI:{self.state.rsi_6:.1f}", pos_size=pos_size))
                current_layers -= actual_sell

        # 4. 趋势建仓逻辑
        if current_layers < self.state.target_layers:
            # 买入信号: 文档逻辑 - 强趋势放宽至 55，否则使用配置(默认40)
            buy_thr = 55 if self.state.trend_score >= 4 else self.params.get('rsi_buy_threshold', 40)
            
            # 【优化补充】: 如果当前是首层建仓(持仓为0)，硬性要求 RSI < 45，避免在波峰追高冷启动
            if current_layers == 0:
                buy_thr = min(buy_thr, 45)
                
            if self.state.rsi_6 < buy_thr:
                needed = self.state.target_layers - current_layers
                # 文档要求: 一次补齐差额的一半 (batch = max(1, needed // 2))
                batch = max(1, needed // 2)
                # 【关键修复】: 确保补仓量不超过最大限制
                batch = min(batch, self.params.get('max_positions', 5) - current_layers)
                
                if batch > 0:
                    # 【抑制逻辑】检查是否在同一 Bar 且价格波动不足
                    price_buff = self.params.get('signal_price_buffer', 0.005) # 默认 0.5%
                    is_duplicate = False
                    if self.state.last_buy_bar_ts == data.timestamp:
                        price_diff = abs(data.close - self.state.last_buy_price) / self.state.last_buy_price if self.state.last_buy_price > 0 else 1.0
                        if price_diff < price_buff:
                            is_duplicate = True
                    
                    if not is_duplicate:
                        signals.append(self._make_signal(Side.BUY, batch, data, f"趋势建仓(分:{self.state.trend_score})"))
                        current_layers += batch

        # 5. 网格辅助 (仅在震荡/中等趋势下)
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
        # 用【成本】而非【现价】计算层数，因为层数代表资金占用
        total_cost = size * avg_price
        # 使用 0.8 的偏移来降低因手续费导致的舍入误差，确保 0.9 层也被视为 1 层
        return int((total_cost + layer_val * 0.2) // layer_val)

    def _make_signal(self, side: Side, layers: int, d: MarketData, reason: str, pos_size: float = 0) -> Signal:
        # 将层数转换为具体的数量
        layer_val_usdt = self.params.get('layer_size_usdt', 2000)
        
        if side == Side.BUY:
            # 买单使用报价币金额 (USDT)，设置 size_in_quote=True
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
            
            # 使用当前状态的层数作为基准
            total_layers = max(1, self.state.current_layers)
            
            # 如果要卖出的层数 >= 当前总层数，或者是最后一层，直接清空
            if layers >= total_layers:
                qty = pos_size
            else:
                # 按比例减仓，例如 3 层减 1 层，卖出 1/3 的持仓数量
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
        """计算局部波段高低点 (Top 3)"""
        if len(self._data_buffer) < 15:
            return {'pivots_high': [], 'pivots_low': []}

        # 简单识别分形 (左3右3)
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

        # 取最近的最显著的 3 个
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

        # 转换趋势强度为文字
        score_labels = {5: "极强爆发", 4: "趋势上行", 3: "偏多整理", 2: "区间震荡", 1: "弱势消耗", 0: "极度低迷"}
        trend_label = score_labels.get(s.trend_score, "等待数据")

        return {
            # 策略核心指标
            'trend_score': s.trend_score,
            'target_layers': s.target_layers,
            'position_count': s.current_layers,
            'signal_text': f"趋势分:{s.trend_score} ({trend_label})",
            'signal_strength': f"{s.trend_score}/5",
            'signal_color': 'buy' if s.trend_score >= 3 else ('sell' if s.trend_score <= 1 else 'neutral'),
            
            # 技术指标组件
            'current_rsi': s.rsi_6,
            'rsi_oversold': p.get('rsi_buy_threshold', 40),
            'rsi_overbought': p.get('rsi_sell_threshold', 65),
            'macd_trend': f"{'红柱' if s.histogram < 0 else '绿柱'}({s.histogram:.2f})",
            'macd': s.macd_line,
            'macdsignal': s.signal_line,
            'macdhist': s.histogram,
            'atrVal': (s.ma5 - s.ma10) if s.ma10 > 0 else 0, # 对齐 Dashboard ID
            'marketRegime': "强制满仓模式" if not s.dynamic_grid else "动态网格模式", # 对齐 Dashboard ID
            
            # 成交量扩展
            'current_volume': s.last_candle.get('volume', 0),
            'vol_ratio': s.vol_ratio,
            'vol_trend': f"量比:{s.vol_ratio:.2f} ({'缩量' if s.vol_ratio < 1.0 else ('爆发' if s.vol_ratio > 1.3 else '正常')})",
            
            # 网格状态
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
