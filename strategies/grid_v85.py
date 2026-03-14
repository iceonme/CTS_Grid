import os
import json
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from collections import deque

from core import (
    MarketData, Signal, Side, OrderType, 
    FillEvent, Position, StrategyContext
)
from strategies.base import BaseStrategy

class GridStrategyV85(BaseStrategy):
    """
    GridStrategy V8.5 (Jeff Huang 版)
    
    核心逻辑：
    - 6小时 (360min) "5取3" 抗插针网格中枢计算
    - 动态层数 (5层/7层) 自动切换
    - L0 缓冲观望层 (价格进入 L0 不交易)
    - 区间感应触发：下半层买入 (0-50%) / 上半层卖出 (50-100%)
    - 1/n 动态分仓：买入初始资金 1/n，卖出当前持仓 1/n
    - 2小时观察熔断期：超时后保留持仓并重算网格
    - 增强型日志：实时输出区间深度与决策详情
    """

    def __init__(self, name: str = "Grid_V85_Jeff", **params):
        super().__init__(name, **params)
        self.symbol = params.get('symbol', 'BTC-USDT')
        
        # 数据缓存 (满足 4h = 240min 的数据要求)
        self._data_1m = deque(maxlen=500)   # 冗余缓存
        self._initialized = False
        
        @dataclass
        class StrategyState:
            current_rsi: float = 50.0
            volatility: float = 0.0
            avg_gain: float = 0.0          # 已废弃，保留兼容性
            avg_loss: float = 0.0          # 已废弃，保留兼容性
            gain_dq: deque = field(default_factory=lambda: deque(maxlen=14))
            loss_dq: deque = field(default_factory=lambda: deque(maxlen=14))
            gain_sum: float = 0.0
            loss_sum: float = 0.0
            base_top: float = 0.0           # 网格顶部 (中枢)
            base_bottom: float = 0.0        # 网格底部 (中枢)
            active_layers_mode: int = 5     # 5 或 7
            grid_lines: List[float] = field(default_factory=list)
            
            # RSI 动态阈值
            dynamic_rsi_buy: float = 25.0
            dynamic_rsi_sell: float = 75.0
            
            # 熔断观察状态
            is_observing: bool = False
            observe_start_time: Optional[datetime] = None
            observe_trigger_price: float = 0.0
            
            # 记录上次重算时间
            last_rebalance_time: Optional[datetime] = None
            
            # 记录上次价格 (用于 Crossing Logic)
            last_marker_price: float = 0.0
            
            # 记录层级持仓锁定 (防复吸)
            layer_holdings: Dict[int, bool] = field(default_factory=dict)

        self.state = StrategyState()
        
        # 策略可调参数
        self.rsi_period = params.get('rsi_period', 14)
        self.observe_hours = params.get('observe_hours', 2.0)
        self.max_position_pct = params.get('max_position_pct', 0.8)
        self.lookback_hours = params.get('lookback_hours', 4.0) # 新增：支持 2h/4h/6h 回看
        self.unlock_mode = params.get('unlock_mode', 'fifo')    # 新增：'fifo' 或 'lifo'
        self.range_multiplier = params.get('range_multiplier', 1.0) # 新增：网格宽度缩放系数
        self.verbose = params.get('verbose', False)            # 新增：控制日志输出
        
        # 资金管理参数
        self.initial_capital = params.get('initial_capital', 10000.0)
        self.initialize()
        
        # 决策追踪 (Trace Log): {timestamp_ms: [msg1, msg2, ...]}
        self.decision_trace = {}

    def initialize(self):
        """[标准接口] 初始化/重置策略状态"""
        super().initialize()
        self._data_1m.clear()
        self.decision_trace.clear()
        
        # 重新初始化 StrategyState (避免旧网格和持仓干扰)
        @dataclass
        class StrategyState:
            current_rsi: float = 50.0
            volatility: float = 0.0
            avg_gain: float = 0.0          # 已废弃，保留兼容性
            avg_loss: float = 0.0          # 已废弃，保留兼容性
            gain_dq: deque = field(default_factory=lambda: deque(maxlen=14))
            loss_dq: deque = field(default_factory=lambda: deque(maxlen=14))
            gain_sum: float = 0.0
            loss_sum: float = 0.0
            base_top: float = 0.0           # 网格顶部 (中枢)
            base_bottom: float = 0.0        # 网格底部 (中枢)
            active_layers_mode: int = 5     # 5 或 7
            grid_lines: List[float] = field(default_factory=list)
            
            # RSI 动态阈值
            dynamic_rsi_buy: float = 25.0
            dynamic_rsi_sell: float = 75.0
            
            # 熔断观察状态
            is_observing: bool = False
            observe_start_time: Optional[datetime] = None
            observe_trigger_price: float = 0.0
            
            # 记录上次重算时间
            last_rebalance_time: Optional[datetime] = None
            
            # 记录上次价格 (用于 Crossing Logic)
            last_marker_price: float = 0.0
            
            # 记录层级持仓锁定 (防复吸)
            layer_holdings: Dict[int, bool] = field(default_factory=dict)
            
        self.state = StrategyState()
        if self.verbose:
            print(f"[V8.5] 策略内部状态已重置")

    def on_data(self, data: MarketData, context: Optional[StrategyContext]) -> List[Signal]:
        # 1. 数据对齐与缓存
        self._data_1m.append(data)
        
        # 2. 计算指标 (即使在预热期也计算，以便 Dashboard 有数据)
        self._calculate_indicators()
        
        # 仅在整分时打一个心跳 trace
        if data.timestamp.second == 0 and data.timestamp.minute % 5 == 0:
            ts_ms = int(data.timestamp.timestamp() * 1000)
            self._trace(ts_ms, f"Tick: {data.close:.2f} | RSI: {self.state.current_rsi:.1f}")
        
        # 预热检查 (240min)
        if len(self._data_1m) < 240:
            if self.verbose and len(self._data_1m) % 60 == 0:
                print(f"[V8.5] 数据预热中: {len(self._data_1m)}/240")
            return []

        # 记录基础状态 Trace (即使没有任何信号)
        ts_ms = int(data.timestamp.timestamp() * 1000)
        self._trace(ts_ms, f"Price: {data.close:.1f} | RSI: {self.state.current_rsi:.1f}")

        # 3. 网格重算逻辑 (每 6 小时或初次或熔断恢复)
        self._rebalance_grid_logic(data, context)

        if not self.state.grid_lines:
            return []

        # 4. 熔断观察期处理
        if self.state.is_observing:
            return self._handle_observation(data, context)

        # 5. 交易逻辑
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
        
        # 更新队列长度（如果参数改变）
        if self.state.gain_dq.maxlen != self.rsi_period:
            self.state.gain_dq = deque(list(self.state.gain_dq), maxlen=self.rsi_period)
            self.state.loss_dq = deque(list(self.state.loss_dq), maxlen=self.rsi_period)

        # 增量更新 SMA
        if len(self.state.gain_dq) == self.rsi_period:
            self.state.gain_sum -= self.state.gain_dq.popleft()
            self.state.loss_sum -= self.state.loss_dq.popleft()
        
        self.state.gain_dq.append(gain)
        self.state.loss_dq.append(loss)
        self.state.gain_sum += gain
        self.state.loss_sum += loss
        
        # 计算 RSI (SMA Based - Cutler's RSI)
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
        # 每 6 小时重算一次，或者初次运行
        if (self.state.last_rebalance_time is None or 
            (now - self.state.last_rebalance_time).total_seconds() >= 6 * 3600):
            self._calculate_5_take_3_grid(data, context)
            self.state.last_rebalance_time = now

    def _calculate_5_take_3_grid(self, data: MarketData, context: Optional[StrategyContext] = None):
        """核心: 5取3抗插针算法"""
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
        
        # 核心：去掉 1 个最高，去掉 1 个最低，取中间 3 个均值
        h_trimmed = h_points[1:4]
        l_trimmed = l_points[1:4]
        
        self.state.base_top = sum(h_trimmed) / 3
        self.state.base_bottom = sum(l_trimmed) / 3
        
        # 波动率判定
        vol = (self.state.base_top - self.state.base_bottom) / self.state.base_bottom
        self.state.volatility = vol
        
        # 5层 vs 7层 判定 (>1.2% 为 7 层)
        if vol > 0.012:
            self.state.active_layers_mode = 7
        else:
            self.state.active_layers_mode = 5
            
        # 动态 RSI 阈值
        if vol > 0.02: # 高波动
            self.state.dynamic_rsi_buy, self.state.dynamic_rsi_sell = 20, 80
        elif vol < 0.012: # 低波动
            self.state.dynamic_rsi_buy, self.state.dynamic_rsi_sell = 30, 70
        else: # 正常
            self.state.dynamic_rsi_buy, self.state.dynamic_rsi_sell = 25, 75
            
        # 构建完整刻度 (包含 2 层虚拟)
        self._build_grid_lines()
        
        # 核心优化：持仓继承 (Position Inheritance)
        # 不再 simple clear，而是根据当前持仓数量反向推算锁定层级
        self.state.layer_holdings.clear() 
        if context:
            pos = context.positions.get(self.symbol)
            if pos and pos.size > 0:
                current_capital = context.total_value
                unit_val = (current_capital * self.max_position_pct) / self.state.active_layers_mode
                # 计算大约持有多少份 (层)
                pos_in_layers = round((pos.size * data.close) / unit_val)
                if pos_in_layers > 0:
                    # 核心修复 3：持仓继承避开 L0 禁区
                    v_lower_count = 2
                    n = self.state.active_layers_mode
                    l0_idx = v_lower_count + (n // 2)
                    locked_count = 0
                    current_idx = v_lower_count # 从最底层的实体层开始

                    while locked_count < pos_in_layers and current_idx < len(self.state.grid_lines) - 1:
                        # 必须跳过 L0 禁区和卖出层 (只锁买入层，即索引小于 l0_idx)
                        if current_idx < l0_idx:
                            self.state.layer_holdings[current_idx] = True
                            locked_count += 1
                        current_idx += 1
                    if self.verbose:
                        print(f"[V8.5 INHERIT] 检测到持仓 {pos.size:.4f} BTC，自动继承锁定新网格底部的 {locked_count} 个实体买入层")
        
        # 增强日志
        if self.verbose:
            print(f"\n>>>> [V8.5 GRID RECALC] {data.timestamp} <<<<")
            print(f"| 原始高点: {[f'{x:.1f}' for x in h_points]} -> 保留: {[f'{x:.1f}' for x in h_trimmed]}")
            print(f"| 原始低点: {[f'{x:.1f}' for x in l_points]} -> 保留: {[f'{x:.1f}' for x in l_trimmed]}")
            print(f"| 中枢顶部: {self.state.base_top:.2f} | 底部: {self.state.base_bottom:.2f}")
            print(f"| 波动率: {vol*100:.2f}% -> 模式: {self.state.active_layers_mode}层 | RSI: {self.state.dynamic_rsi_buy}/{self.state.dynamic_rsi_sell}")
            print(f"| 核心网格范围: {self.state.grid_lines[0]:.1f} - {self.state.grid_lines[-1]:.1f}\n")

    def _build_grid_lines(self):
        """构建包含 2 层虚拟层的价格刻度"""
        n = self.state.active_layers_mode
        h = ((self.state.base_top - self.state.base_bottom) / n) * self.range_multiplier
        
        lines = []
        # 下方 2 层虚拟: V-2, V-1
        lines.append(self.state.base_bottom - 2 * h)
        lines.append(self.state.base_bottom - 1 * h)
        
        # 实体层: 包含 base_bottom (共 n+1 条线，围成 n 个区间)
        for i in range(n + 1):
            lines.append(self.state.base_bottom + i * h)
            
        # 上方 2 层虚拟: V+1, V+2
        lines.append(self.state.base_top + 1 * h)
        lines.append(self.state.base_top + 2 * h)
            
        self.state.grid_lines = lines

    def _handle_observation(self, data: MarketData, context: Optional[StrategyContext] = None) -> List[Signal]:
        elapsed = (data.timestamp - self.state.observe_start_time).total_seconds()
        
        # 核心修复 4：熔断解除条件对齐 (包含虚拟层)
        ts_ms = int(data.timestamp.timestamp() * 1000)
        if self.state.grid_lines[0] <= data.close <= self.state.grid_lines[-1]:
            msg = f"熔断解除: 价格 {data.close:.2f} 回归区间 (耗时 {elapsed/60:.1f}min)"
            if self.verbose:
                print(f"[V8.5] {msg}")
            self._trace(ts_ms, msg)
            self.state.is_observing = False
            return []
        else:
            # 记录熔断中的偏离状态
            grid_center = (self.state.grid_lines[0] + self.state.grid_lines[-1]) / 2
            deviation = (data.close - grid_center) / grid_center * 100
            self._trace(ts_ms, f"熔断观察中: 价格 {data.close:.1f} 偏离中枢 {deviation:+.2f}%")
            
        # 满 N 小时未回归
        if elapsed >= self.observe_hours * 3600:
            if self.verbose:
                print(f"[V8.5] 熔断超时 ({self.observe_hours}h): 启动网格重算 (保留持仓)")
            self.state.is_observing = False
            # 熔断重算也需要 context 来处理持仓继承
            self._calculate_5_take_3_grid(data, context) 
            self.state.last_rebalance_time = data.timestamp
            
        return []

    def _generate_signals(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        price = data.close
        lines = self.state.grid_lines
        
        # 检查是否突破整网格边缘 (进入观察期)
        if price < lines[0] or price > lines[-1]:
            ts_ms = int(data.timestamp.timestamp() * 1000)
            msg = f"触发熔断观察: 价格 {price:.2f} 溢出边界 [{lines[0]:.1f}, {lines[-1]:.1f}]"
            if self.verbose:
                print(f"[V8.5] {msg}")
            self._trace(ts_ms, msg)
            self.state.is_observing = True
            self.state.observe_start_time = data.timestamp
            self.state.observe_trigger_price = price
            return []

        # 定位当前所在层级
        layer_idx = -1
        for i in range(len(lines) - 1):
            if lines[i] <= price <= lines[i+1]:
                layer_idx = i
                break
        
        if layer_idx == -1: return []
        
        # 映射层级属性
        # lines 结构: [V-2, V-1, L(-n), ..., L(0), ..., L(n), V1, V2]
        # 总共有 n + 4 层区间
        n = self.state.active_layers_mode
        v_lower_count = 2
        
        # L0 索引计算：
        # lines 结构 (举例 n=5): [0:V-2, 1:V-1, 2:B, 3:L1, 4:L2, 5:L3, 6:L4, 7:T, 8:V+1, 9:V+2]
        # 有 9 个区间。中间区间 (L0) 应该是第 [4, 5] 条线构成的区间，索引为 4。
        # 公式: v_lower_count + (n // 2) 刚好指向 index=2 + 2 = 4 (即区间 [lines[4], lines[5]])
        l0_idx = v_lower_count + (n // 2)
        rel_idx = layer_idx - l0_idx
        
        # 1. L0 缓冲禁区
        ts_ms = int(data.timestamp.timestamp() * 1000)
        if rel_idx == 0:
            self._trace(ts_ms, f"位置: L0 缓冲禁区 ({price:.1f}) | 观望中")
            return []
            
        # 2. 判断实体/虚拟
        is_virtual_buy = layer_idx < v_lower_count
        is_virtual_sell = layer_idx >= v_lower_count + n
        
        layer_name = f"L{rel_idx}"
        if is_virtual_buy or is_virtual_sell:
            layer_name = f"虚拟层 {layer_name}"
        else:
            layer_name = f"实体层 {layer_name}"
            
        self._trace(ts_ms, f"位置: {layer_name} | Price: {price:.1f}")
        
        # 3. 计算区间深度 (0-100%)
        bounds = (lines[layer_idx], lines[layer_idx+1])
        depth = (price - bounds[0]) / (bounds[1] - bounds[0])
        
        # 4. 判定买卖
        signals = []
        pos = context.positions.get(self.symbol)
        pos_size = float(pos.size) if pos else 0.0
        
        # 获取上次价格
        last_price = self.state.last_marker_price if self.state.last_marker_price > 0 else price
        self.state.last_marker_price = price # 更新记录
        
        # 触发中位线 (每一层的 50% 处)
        trigger_line = bounds[0] + (bounds[1] - bounds[0]) * 0.5
        
        # 买入逻辑 (rel_idx < 0): 必须是由上向下穿过触发线
        if rel_idx < 0:
            # Crossing Logic: 上次价格在触发线上方，且当前价格在触发线下方 (或等于)
            is_crossing_down = (last_price > trigger_line and price <= trigger_line)
            
            if is_crossing_down:
                # 只有当该层没有锁定时才买入 (防复吸)
                if layer_idx in self.state.layer_holdings:
                    self._trace(ts_ms, f"跳过买入: {layer_name} 已被锁定 (防复吸保护)")
                else:
                    if is_virtual_buy and self.state.current_rsi > self.state.dynamic_rsi_buy:
                        self._trace(ts_ms, f"跳过买入: {layer_name} RSI({self.state.current_rsi:.1f}) > 阈值({self.state.dynamic_rsi_buy})")
                        return []
                        
                    # 核心修正：1/n 动态分仓（基于当前可用 USDT 资金）
                    # 用户要求：买入仓位需要是当前所拥有的资金USDT的1/n
                    buy_val = context.cash / n
                    self.state.layer_holdings[layer_idx] = True
                    msg = f"成交买入: L({rel_idx}) 价格 {price:.1f} 量 {buy_val:.1f} USDT"
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
                    self._trace(ts_ms, f"等待买入: 价格已在触发线 ({trigger_line:.1f}) 下方，等待反弹穿越或下个周期")
                else:
                    dist = price - trigger_line
                    self._trace(ts_ms, f"等待买入: 距 {layer_name} 触发线还差 {dist:.1f} USDT")
                    
        # 卖出逻辑 (rel_idx > 0): 必须是由下向上穿过触发线
        elif rel_idx > 0:
            is_crossing_up = (last_price < trigger_line and price >= trigger_line)
            
            if is_crossing_up:
                if pos_size <= 0:
                    self._trace(ts_ms, f"跳过卖出: {layer_name} 触发，但当前无持仓")
                else:
                    # 核心修复 5：均价保护机制 (Cost Basis Protection)
                    avg_cost = float(pos.avg_price) if hasattr(pos, 'avg_price') else 0.0
                    # 如果当前价格低于持仓均价，拒绝卖出（防止网格下移导致的割肉）
                    if avg_cost > 0 and price < avg_cost:
                        if self.verbose:
                            print(f"[V8.5 PROTECT] 触发卖出信号但价格({price:.2f})低于均价({avg_cost:.2f})，拒绝割肉。")
                        self._trace(ts_ms, f"保护跳过: 价格({price:.2f}) < 均价({avg_cost:.2f})")
                        return []

                    if is_virtual_sell and self.state.current_rsi < self.state.dynamic_rsi_sell:
                        self._trace(ts_ms, f"跳过卖出: {layer_name} RSI({self.state.current_rsi:.1f}) < 阈值({self.state.dynamic_rsi_sell})")
                        return []
                    
                    # 核心修复 1：1/n 卖出算法优化 (处理芝诺的乌龟)
                    current_capital = context.total_value
                    target_sell_val = (current_capital * self.max_position_pct) / n
                    sell_qty = target_sell_val / price

                    # 兜底与精度保护：防止卖出量超过实际持仓，或处理尾仓
                    if sell_qty > pos_size or (pos_size - sell_qty) * price < 10.0:
                        sell_qty = pos_size  # 如果剩余尾仓价值小于 10 U，直接清仓

                # 最小下单额度拦截 (假设交易所要求单笔至少 5 USDT)
                if sell_qty * price < 5.0:
                    self._trace(ts_ms, f"跳过卖出: 下单金额 {sell_qty*price:.1f} 过小")
                    return [] 
                
                # 核心修复 2：解锁逻辑优化 (支持 FIFO/LIFO)
                if self.state.layer_holdings:
                    # 解锁逻辑
                    if self.unlock_mode == 'lifo':
                        # LIFO: 解锁最近买入的（通常是价格最低的层级）
                        target_key = max(self.state.layer_holdings.keys()) # 注意：LIFO应该解最高key(最深买入)
                        mode_label = "LIFO"
                    else:
                        # FIFO (Default): 解锁最早买入的（通常是价格最高的层级）
                        target_key = min(self.state.layer_holdings.keys())
                        mode_label = "FIFO"
                        
                    self.state.layer_holdings.pop(target_key)
                    if self.verbose:
                        print(f"[V8.5 DEBUG] 使用 {mode_label} 成功解锁层级 L({target_key - l0_idx})")
                
                msg = f"成交卖出: L({rel_idx}) 价格 {price:.1f} 量 {sell_qty:.4f}"
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
                    self._trace(ts_ms, f"等待卖出: 价格已在触发线 ({trigger_line:.1f}) 上方，等待回调穿越或下个周期")
                else:
                    dist = trigger_line - price
                    self._trace(ts_ms, f"等待卖出: 距 {layer_name} 触发线还差 {dist:.1f} USDT")

        return signals

    def _trace(self, ts_ms: int, msg: str):
        """记录决策追踪日志"""
        if ts_ms not in self.decision_trace:
            self.decision_trace[ts_ms] = []
        self.decision_trace[ts_ms].append(msg)

    def get_status(self, context: Optional[StrategyContext] = None) -> Dict[str, Any]:
        # 判定当前信号文本和颜色
        signal_text = "等待信号"
        signal_color = "neutral"
        if self.state.is_observing:
            signal_text = "熔断观察中"
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
            'marketRegime': f"{self.state.active_layers_mode} 层模式",
            'vol_trend': "上升" if self.state.volatility > 0.01 else "平稳", 
            'grid_lower': self.state.base_bottom,
            'grid_upper': self.state.base_top,
            'layers_mode': self.state.active_layers_mode,
            'state_label': "观察期" if self.state.is_observing else "运行中",
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
        
        # 补充参数信息供 Dashboard 显示
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
