import os
import json
import math
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

class GridStrategyV80Opt(BaseStrategy):
    """
    GridStrategy V8.0-OPT-FINAL (Kimibigclaw)
    
    核心特性：
    - 6小时 5取3 抗插针网格中枢计算
    - 5层/7层 动态层数切换
    - 实体层直接交易 + 虚拟层 RSI(自适应) 过滤
    - 双向熔断及连续熔断封印保护
    - ATR 黑天鹅护盾防御 (逐步减仓10%)
    - 严格单层绑定锁定防复吸机制
    """

    def __init__(self, name: str = "Grid_V80_OPT", **params):
        super().__init__(name, **params)
        self.params_path = params.get('config_path', 'config/grid_v80_opt_btc_runtime.json')
        self.meta_path = self.params_path.replace('runtime.json', 'meta.json')
        self.symbol = params.get('symbol', 'BTC-USDT')
        self.param_metadata = {}
        self._load_params()

        # 数据缓存 (满足6h的数据要求)
        self._data_main = deque(maxlen=2000)   
        self._timeframe_mins = params.get('timeframe_minutes', 1) # 默认1m
        self._initialized = False
        
        # 回测与熔断监控存储
        self._circuit_breaker_history: List[datetime] = []

        @dataclass
        class StrategyState:
            current_rsi: float = 50.0
            current_atr: float = 0.0          
            atr_ma: float = 0.0               
            
            # --- 6h 计算出的核心网格属性 ---
            volatility: float = 0.0         # 6h 测算出的震幅波动率
            base_top: float = 0.0           # 6h 5取3 顶部中枢
            base_bottom: float = 0.0        # 6h 5取3 底部中枢
            active_layers_mode: int = 5     # 当前实际激活的层级模式 (5 或 7)
            
            # 实体+虚拟 完整的网格刻度线数组
            grid_lines: List[float] = field(default_factory=list)
            
            # RSI 动态阈值记录
            dynamic_rsi_buy: float = 25.0
            dynamic_rsi_sell: float = 75.0
            
            # --- 内部仓位管理 (Paper交易核心) ---
            internal_pos_size: float = 0.0      # 内部追踪的持仓数量
            internal_avg_price: float = 0.0     # 内部追踪的平均成本
            internal_cash: float = 0.0          # 内部追踪的可用现金 (初始化后设置)
            
            # 状态控制
            is_halted: bool = False
            halt_reason: str = ""
            halt_start_time: Optional[datetime] = None
            halt_trigger_price: float = 0.0
            halt_grid_bottom: float = 0.0
            halt_grid_top: float = 0.0
            use_4h_grid: bool = False  # 修正缺失的 4h 重置标记
            
            # 黑天鹅风控控制
            black_swan_mode: bool = False
            last_swan_exit_time: Optional[datetime] = None
            
            last_rebalance_time: Optional[datetime] = None
            
            # 严格防复吸占用字典: key = c_idx, value = True 表示本层已建仓且未平仓
            layer_holdings: Dict[int, bool] = field(default_factory=dict)

        self.state = StrategyState()

    def _load_params(self):
        """支持深度加载参数"""
        if os.path.exists(self.params_path):
            try:
                with open(self.params_path, 'r', encoding='utf-8') as f:
                    self.params.update(json.load(f))
            except Exception as e:
                print(f"[V8.0-OPT] 加载参数失败: {e}")
        
        if os.path.exists(self.meta_path):
            try:
                with open(self.meta_path, 'r', encoding='utf-8') as f:
                    self.param_metadata = json.load(f)
            except Exception as e:
                print(f"[V8.0-OPT] 加载元数据失败: {e}")

    def initialize(self):
        super().initialize()
        # 初始化内部现金 (从配置中获取)
        trading_cfg = self.params.get('trading', {})
        self.state.internal_cash = trading_cfg.get('initial_capital', 10000.0)
        print(f"[V8.0-OPT] {self.name} 初始化完成 | 初始资金: {self.state.internal_cash}")

    def on_fill(self, fill: FillEvent):
        """成交回调：更新内部仓位和成本，完全替代交易所同步"""
        if fill.symbol != self.symbol:
            return
            
        # 更新持仓和平均价格
        old_size = self.state.internal_pos_size
        old_avg = self.state.internal_avg_price
        fill_size = float(fill.size)
        fill_price = float(fill.price)
        
        if fill.side == Side.BUY:
            new_size = old_size + fill_size
            if new_size > 0:
                self.state.internal_avg_price = (old_size * old_avg + fill_size * fill_price) / new_size
            self.state.internal_pos_size = new_size
            self.state.internal_cash -= (fill_size * fill_price)
            print(f"[成交反馈] 买入成功 | 数量: {fill_size:.4f} @ {fill_price:.2f} | 当前总持仓: {new_size:.4f}")
        else:
            new_size = max(0.0, old_size - fill_size)
            self.state.internal_pos_size = new_size
            self.state.internal_cash += (fill_size * fill_price)
            print(f"[成交反馈] 卖出成功 | 数量: {fill_size:.4f} @ {fill_price:.2f} | 剩余持仓: {new_size:.4f}")
            
            # 卖出后，如果持仓清零，重置成本
            if new_size <= 0:
                self.state.internal_avg_price = 0.0

    def on_data(self, data: MarketData, context: Optional[StrategyContext]) -> List[Signal]:
        if not self._initialized:
            self.initialize()

        # 1. 更新内部数据堆叠 (1m 逻辑，按分钟对齐收敛)
        ts = data.timestamp
        # 对齐到当前分钟的第0秒
        bar_ts = ts.replace(second=0, microsecond=0)
        
        if self._data_main and self._data_main[-1].timestamp.replace(second=0, microsecond=0) == bar_ts:
            # 更新当前正在变动的 K 线
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
            # 新的一分钟 Bar
            self._data_main.append(data)
        
        # 6小时 = 360 根 1m 线
        min_bars = 360 
        atr_period = self.params.get('atr_period', 14)
        if len(self._data_main) < min_bars + atr_period: # 加上指标周期缓冲
            return []

        # 2. 计算短线指标 (Main RSI / ATR)
        self._calculate_indicators()

        # 3. 风控：ATR黑天鹅及双向熔断阻断
        is_risk_halted = self._check_risk_and_halt(data, context)

        # 4. 6小时 5取3 的网格重平衡计算与动态 RSI 适配
        if not is_risk_halted or self.state.black_swan_mode:
            self._rebalance_grid_if_needed(data)

        if self.state.base_top == 0.0 or len(self.state.grid_lines) == 0:
            return []

        # 5. 根据当前的实体层 / 虚拟层 及黑天鹅状态产生交易指令
        # 彻底移除对 context.positions 的依赖，改用内部状态
        if self.state.black_swan_mode:
            return self._process_black_swan_exit(data)
            
        if not is_risk_halted and not self.state.is_halted:
            return self._generate_signals(data)
                
        return []

    def _update_data(self, data: MarketData):
        """(兼容性保留，主逻辑已改用 on_data 直接 append)"""
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
        
        # ATR MA 追溯
        hist_closes = closes_main.iloc[-atr_ma_lookback:]
        hist_highs = highs_main.iloc[-atr_ma_lookback:]
        hist_lows = lows_main.iloc[-atr_ma_lookback:]
        self.state.atr_ma = self._atr(hist_highs, hist_lows, hist_closes, atr_period).mean()

    def _rebalance_grid_if_needed(self, data: MarketData):
        """执行网格核心算法与参数自适应 - 支持6小时常规模式或4小时熔断重置模式"""
        current_time = data.timestamp
        
        # 检查是否是熔断后的4小时重置模式
        use_4h_mode = getattr(self.state, 'use_4h_grid', False)
        
        if use_4h_mode:
            # 熔断后强制立即执行4小时网格计算
            self._calculate_4h_grid_with_preserve(data)
            self.state.use_4h_grid = False  # 重置标记
            return
        
        # 常规6小时网格重平衡检查
        interval_mins = self.params.get('grid', {}).get('rebalance_interval_minutes', 60)
        
        if self.state.last_rebalance_time is not None:
            if (current_time - self.state.last_rebalance_time).total_seconds() < interval_mins * 60:
                return
                
        grid_cfg = self.params.get('grid', {})
        # 计算 6 小时对应的 K 线根数
        lookback_bars = (grid_cfg.get('lookback_hours', 6) * 60) // self._timeframe_mins
        if len(self._data_main) < lookback_bars:
            return
        
        # 执行6小时网格计算
        self._calculate_grid_core(data, lookback_bars, hours_label="6h")

    def _calculate_4h_grid_with_preserve(self, data: MarketData):
        """计算4小时网格（熔断超时后的重置模式）"""
        print(f"[V8.0-OPT] 开始计算4小时网格（熔断重置模式）")
        
        # 使用4小时数据
        lookback_bars = (4 * 60) // self._timeframe_mins  # 4小时 = 240根1分钟线
        if len(self._data_main) < lookback_bars:
            print(f"[V8.0-OPT] 4小时数据不足({len(self._data_main)}/{lookback_bars})，使用全部可用数据")
            lookback_bars = len(self._data_main)
        
        # 执行4小时网格计算
        self._calculate_grid_core(data, lookback_bars, hours_label="4h")
        
        print(f"[V8.0-OPT] 4小时网格重置完成 | 保留全部持仓作为新网格底仓")

    def _calculate_grid_core(self, data: MarketData, lookback_bars: int, hours_label: str = "6h"):
        """网格核心计算 - 5取3算法"""
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
            active_layers = base_layers + 2  # 7层模式
        else:
            active_layers = base_layers      # 5层模式
            
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
            
        # BUG#1 修复：网格重算后清空旧的层级锁，防止幽灵锁阻止新网格买入
        self.state.layer_holdings.clear()
        
        self.state.last_rebalance_time = data.timestamp
        print(f"[V8.0-OPT] 重算网格完成 [{hours_label}] | Vol={volatility*100:.2f}% ({active_layers}层) RSI=[{self.state.dynamic_rsi_buy}-{self.state.dynamic_rsi_sell}]")

    def _check_risk_and_halt(self, data: MarketData, context: Optional[StrategyContext]) -> bool:
        """
        完整风控检查：双向熔断(智能观察模式) + 黑天鹅 + 连续熔断封印
        返回 True = 阻断交易
        """
        now = data.timestamp
        cb_cfg = self.params.get('circuit_breaker', {})
        bs_cfg = self.params.get('black_swan', {})
        
        # === 1. 检查是否已在某种熔断状态中 ===
        
        # 1.1 检查是否已在双向熔断观察期（智能观察模式）
        if self.state.is_halted and self.state.halt_reason and self.state.halt_reason.startswith("OBSERVE"):
            return self._handle_observation_mode(data, now)

        # 1.2 黑天鹅模式（减仓保护）
        if self.state.black_swan_mode:
            return True  # 阻断新开仓，由 _process_black_swan_exit 处理减仓
        
        # 1.3 BUG#2 修复：检查黑天鹅ATR异常（之前遗漏了此调用入口）
        if bs_cfg.get('enabled', True):
            if self._check_black_swan_trigger(data, bs_cfg):
                return True
        
        # 1.4 检查双向越界熔断（智能观察模式）
        if cb_cfg.get('enabled', True):
            if self._check_bidirectional_breaker(data, now, cb_cfg):
                return True
        
        return False

    def _check_bidirectional_breaker(self, data: MarketData, now: datetime, cb_cfg: dict) -> bool:
        """双向越界熔断 - 智能观察模式"""
        if len(self.state.grid_lines) == 0:
            return False
        
        trigger_beyond = cb_cfg.get('trigger_beyond_virtual', True)
        if not trigger_beyond:
            return False
        
        # 突破虚拟层触发
        if data.close < self.state.grid_lines[0] or data.close > self.state.grid_lines[-1]:
            direction = "DOWN" if data.close < self.state.grid_lines[0] else "UP"
            self._enter_observation_mode(now, direction, data.close)
            return True
        
        return False

    def _enter_observation_mode(self, now: datetime, direction: str, trigger_price: float):
        """进入观察期 - 持仓不变，等待价格回归或超时"""
        self.state.is_halted = True
        self.state.halt_reason = f"OBSERVE_{direction}"
        self.state.halt_start_time = now
        self.state.halt_trigger_price = trigger_price
        self.state.halt_grid_bottom = self.state.base_bottom
        self.state.halt_grid_top = self.state.base_top
        
        # 记录熔断历史
        self._circuit_breaker_history.append(now)
        
        print(f"[{now}] 熔断触发 | 方向: {direction} | 价格: {trigger_price}")
        print(f"[{now}] 进入2小时观察期 | 持仓不变 | 等待价格回归...")

    def _handle_observation_mode(self, data: MarketData, now: datetime) -> bool:
        """处理观察期逻辑 - 返回True表示继续阻断，False表示恢复交易"""
        if self.state.halt_start_time is None:
            return True
            
        elapsed = (now - self.state.halt_start_time).total_seconds()
        
        grid_bottom = self.state.halt_grid_bottom
        grid_top = self.state.halt_grid_top
        current_price = data.close
        
        # 情况1: 价格回归网格 → 提前恢复
        if grid_bottom <= current_price <= grid_top:
            self._resume_from_observation("PRICE_RETURN", elapsed, current_price)
            return False  # 不阻断，恢复交易
        
        # 情况2: 满2小时未回归 → 重置4小时网格
        cooldown_seconds = 2 * 3600  # 2小时 = 7200秒
        if elapsed >= cooldown_seconds:
            self._reset_grid_after_timeout(now)
            return False  # 新网格已生成，恢复交易
        
        # 情况3: 仍在观察中 → 阻断交易，每5分钟打印日志
        # BUG#3 修复：使用整除窗口判定，避免浮点精度导致日志漏打
        elapsed_mins = int(elapsed // 60)
        if elapsed_mins > 0 and elapsed_mins % 5 == 0 and (elapsed % 60) < 61:
            remaining = cooldown_seconds - elapsed
            print(f"[{now}] [观察中] 已过去: {elapsed/60:.1f}分钟 | 剩余: {remaining/60:.1f}分钟 | 价格: {current_price}")
        
        return True

    def _resume_from_observation(self, reason: str, elapsed_sec: float, current_price: float):
        """恢复正常运行 - 持仓完全不变"""
        self.state.is_halted = False
        self.state.halt_reason = ""
        self.state.halt_start_time = None
        
        print(f"[{datetime.now()}] 熔断解除 | 原因: {reason}")
        print(f"[{datetime.now()}] 价格: {current_price} | 观察时长: {elapsed_sec/60:.1f}分钟")
        print(f"[{datetime.now()}] 持仓不变 | 恢复正常交易")

    def _reset_grid_after_timeout(self, now: datetime):
        """2小时超时，保留持仓重置4小时网格"""
        self.state.is_halted = False
        self.state.halt_reason = ""
        self.state.halt_start_time = None
        
        print(f"[{now}] 观察期满2小时 | 价格未回归 | 重新计算网格")
        
        # BUG#5 修复：使用内部持仓状态，而非从未定义的 _last_pos_size
        pos_size = self.state.internal_pos_size
             
        print(f"[{now}] 保留全部持仓({pos_size:.4f})作为新网格底仓")
        
        # 标记需要重置网格（使用4小时数据）
        self.state.last_rebalance_time = None
        self.state.use_4h_grid = True  
        
        print(f"[{now}] 新网格已生成 | 恢复正常交易")

    def _check_black_swan_trigger(self, data: MarketData, bs_cfg: dict) -> bool:
        """检查ATR黑天鹅触发"""
        if self.state.atr_ma <= 0:
            return False
        
        if self.state.current_atr >= self.state.atr_ma * bs_cfg.get('atr_multiplier', 3.0):
            self.state.is_halted = True
            self.state.black_swan_mode = True
            self.state.halt_reason = "Black Swan (ATR Surge)"
            self.state.last_swan_exit_time = None
            self._circuit_breaker_history.append(data.timestamp)
            
            print(f"[风险告警] 触发黑天鹅熔断 | ATR: {self.state.current_atr:.2f} | 均线: {self.state.atr_ma:.2f}")
            print(f"[风险告警] 停止新开仓，启动每10分钟自动市价减仓程序")
            return True
        
        return False

    def _process_black_swan_exit(self, data: MarketData) -> List[Signal]:
        pos_size = self.state.internal_pos_size
        avg_price = self.state.internal_avg_price
        
        if pos_size <= 0:
            self.state.black_swan_mode = False
            self.state.is_halted = False
            self.state.halt_reason = ""
            print(f"[V8.0-OPT] 黑天鹅已被化解，已完成全仓清盘。等待重启。")
            return []

        # 若价格反弹超成本价 → 停止减仓，恢复正常
        if data.close >= avg_price:
            print(f"[V8.0-OPT] 黑天鹅期间强劲反弹，价格已覆盖平均成本（{avg_price:.2f}），撤销警报。")
            self.state.black_swan_mode = False
            self.state.is_halted = False
            self.state.halt_reason = ""
            return []

        # 每10分钟评估一次
        mins_interval = self.params.get('black_swan', {}).get('gradual_exit_interval_minutes', 10)
        if self.state.last_swan_exit_time is None or (data.timestamp - self.state.last_swan_exit_time).total_seconds() >= mins_interval * 60:
            self.state.last_swan_exit_time = data.timestamp
            
            # 卖出总仓位的10%
            sell_qty = pos_size * 0.1
            
            trading_cfg = self.params.get('trading', {})
            cap = trading_cfg.get('initial_capital', 10000)
            layer_val = (cap * trading_cfg.get('max_position_pct', 0.8)) / self.state.active_layers_mode
            
            # 残损金额不足以切分时直接清盘
            if pos_size * data.close < layer_val * 0.4:
                 sell_qty = pos_size
                 
            print(f"[V8.0-OPT] 黑天鹅减仓执行中: 抛售 {sell_qty:.4f}")
            return [Signal(
                timestamp=data.timestamp, symbol=self.symbol, side=Side.SELL,
                size=sell_qty, reason="Black Swan Gradual Exit (-10%)"
            )]
            
        return []

    def _sync_position_to_layers(self, context: StrategyContext, current_price: float):
        """(自 V8.0-OPT Paper 版起已停用) 严格重建目前被锁定的夹层结构"""
        pass

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


    def _generate_signals(self, data: MarketData) -> List[Signal]:
        signals = []
        pos_size = self.state.internal_pos_size
        cash = self.state.internal_cash
        
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
        
        # 严格按照文档锁死实体层编号的角色权限
        # 5层: 0(买), 1/2(缓冲), 3/4(卖)
        # 7层: 0/1(买), 2/3/4(缓冲), 5/6(卖)
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

        # ---------------- 判定卖出 (止盈) ----------------
        should_sell = False
        sell_reason = ""
        
        if pos_size > 0:
            if is_upper_virtual:
                if self.state.current_rsi >= self.state.dynamic_rsi_sell:
                    should_sell = True
                    sell_reason = f"Virtual High Zone Sell (RSI {self.state.current_rsi:.1f})"
            elif is_real and sell_allowed_in_real:
                # 只有在这两个顶层才能直接卖出
                should_sell = True
                sell_reason = f"Real Zone Top Layer Profit (Layer {c_idx})"
            
            if should_sell:
                sell_sz = min(pos_size, layer_value / data.close)
                if pos_size * data.close < layer_value * 1.5:  
                    sell_sz = pos_size
                
                # BUG#4 修复：优先解锁当前卖出触发层，若不匹配则解锁最高层
                if self.state.layer_holdings:
                    if c_idx in self.state.layer_holdings:
                        self.state.layer_holdings.pop(c_idx)
                    else:
                        highest_layer = max(self.state.layer_holdings.keys())
                        self.state.layer_holdings.pop(highest_layer)
                    
                signals.append(Signal(
                    timestamp=data.timestamp, symbol=self.symbol, side=Side.SELL,
                    size=sell_sz, reason=sell_reason
                ))
                return signals

        # ---------------- 判定买入 (建仓) ----------------
        should_buy = False
        buy_reason = ""
        
        # 严格防复吸隔离：当前区间层若被建仓过，无论距离多远都不再追高或补仓
        if c_idx in self.state.layer_holdings:
            return signals

        if pos_size * data.close + layer_value * 0.95 <= max_capital and cash >= layer_value * 0.95:
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
        signal_text = "观察 / 观望"
        signal_color = "neutral"
        
        if self.state.is_halted:
            if self.state.black_swan_mode:
                signal_text = f"黑天鹅熔断 (逐步减仓保护)"
            else:
                signal_text = f"熔断冷却中 ({self.state.halt_reason})"
            signal_color = "sell"
            
        pos_size = self.state.internal_pos_size
        pos_avg_price = self.state.internal_avg_price
        pos_count = 0
        
        # 计算持仓层数
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
            'volatility_state': f"{self.state.volatility*100:.2f}% ({self.state.active_layers_mode}层实体)",
            'marketRegime': f"模式: {self.state.active_layers_mode}层实体",
            'vol_trend': '黑天鹅防御开启' if self.state.black_swan_mode else '自适应触发',
            'current_volume': float(self._data_main[-1].volume) if self._data_main else 0.0,
            
            'signal_text': signal_text,
            'signal_color': signal_color,
            
            'position_size': pos_size,
            'position_avg_price': pos_avg_price,
            'position_unrealized_pnl': 0.0, # 内部不计算盈亏，由外部展示
            'position_count': pos_count,
            'cash': self.state.internal_cash,
            
            'grid_lower': float(np.round(lower_bound, 2)),
            'grid_upper': float(np.round(upper_bound, 2)),
            'grid_range': f"{lower_bound:.1f} - {upper_bound:.1f}" if lower_bound > 0 else "计算中...",
            'grid_lines': gl,
            'layer_holdings': list(self.state.layer_holdings.keys()),
            
            'rsi_oversold': float(np.round(self.state.dynamic_rsi_buy, 1)),
            'rsi_overbought': float(np.round(self.state.dynamic_rsi_sell, 1)),
            
            'is_halted': self.state.is_halted,
            'halt_reason': self.state.halt_reason,
            'params': self.params,
            'param_metadata': self.param_metadata
        }
