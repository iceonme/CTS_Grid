import os
import json
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional, Any
from collections import deque
from dataclasses import dataclass, field

from console.core import (
    MarketData, Signal, Side, OrderType, 
    FillEvent, Position, StrategyContext
)
from cartridges.strategies.base import BaseStrategy

# 兼容性导入：支持 SkillLoader 动态加载和脚本独立运行
try:
    from .indicators import IncrementalIndicatorsV6, GridCalculator, CircuitBreaker
except (ImportError, ValueError):
    import sys
    import os
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    if _current_dir not in sys.path:
        sys.path.insert(0, _current_dir)
    from indicators import IncrementalIndicatorsV6, GridCalculator, CircuitBreaker

@dataclass
class StrategyState:
    current_rsi: float = 50.0
    macd: float = 0.0
    macdsignal: float = 0.0
    macdhist: float = 0.0
    macdhist_prev: float = 0.0
    grid: Optional[Dict] = None
    grid_period: int = 6
    slots: List[Dict] = field(default_factory=list)
    grid_lines: List[float] = field(default_factory=list)
    l0_idx: int = 4
    is_halted: bool = False
    halt_reason: str = ""
    resume_time: Optional[datetime] = None
    last_volume: float = 0.0
    last_marker_price: float = 0.0
    last_buy_price: float = 0.0
    last_sell_price: float = 0.0

class GridMTFStrategyV6_0(BaseStrategy):
    """
    V6.0-Revival 动态网格策略 (Skill 标准版)
    """
    def __init__(self, name: str = "grid-v60", **params):
        super().__init__(name, **params)
        self.symbol = params.get('symbol', 'BTC-USDT')
        self._data_1m = deque(maxlen=400)
        self._data_5m = deque(maxlen=100)
        
        self.state = StrategyState()
        self.decision_trace = {}
        self.warmup_bars = 400   # 明确声明需要 400 根数据预热

        # 参数初始化
        self.state.grid_period = params.get('grid_period_initial', 6)
        self.indicators = IncrementalIndicatorsV6(params)
        self.breaker = CircuitBreaker(params.get('observation_period', 3600))
        self.total_capital = params.get('total_capital', 10000.0)
        
        self._last_1m_ts: Optional[datetime] = None
        self._last_5m_ts: Optional[datetime] = None
        self._last_5m_bar_close = 0.0
        self._last_1m_bar = None

    def initialize(self):
        super().initialize()
        self.decision_trace.clear()
        self.state = StrategyState()
        self.indicators = IncrementalIndicatorsV6(self.params)
        self.breaker = CircuitBreaker(self.params.get('observation_period', 3600))
        self._last_1m_ts = None
        self._last_1m_bar = None
        self._data_1m.clear()
        self._data_5m.clear()
        self._last_5m_ts = None
        print(f"[grid-v60] {self.name} 初始化完成")

    def on_data(self, data: MarketData, context: Optional[StrategyContext]) -> List[Signal]:
        is_new_1m_bar = (not self._last_1m_ts) or (data.timestamp > self._last_1m_ts)
        if is_new_1m_bar:
            if self._last_1m_bar:
                self.indicators.update_1m(self._last_1m_bar, commit=True)
                _, _, hist_commit = self.indicators.update_1m_macd(self._last_1m_bar.close, commit=True)
                self.state.macdhist_prev = hist_commit 
            self._last_1m_ts = data.timestamp
            self._update_data(data)
        self._last_1m_bar = data

        ts_ms = int(data.timestamp.timestamp() * 1000)
        if len(self._data_1m) < 10: return []

        rsi = self.indicators.update_1m(data, commit=False)
        self.state.current_rsi = rsi
        self.state.last_volume = data.volume

        macd, sig, hist = self.indicators.update_1m_macd(data.close, commit=False)
        self.state.macd, self.state.macdsignal, self.state.macdhist = macd, sig, hist

        self._trace(ts_ms, f"Price: {data.close:.1f} | RSI: {rsi:.1f} | MACD: {hist:+.4f}")

        macd_golden = (self.state.macdhist > 0 and self.state.macdhist_prev <= 0)
        macd_dead = (self.state.macdhist < 0 and self.state.macdhist_prev >= 0)
        self._macd_golden, self._macd_dead = macd_golden, macd_dead

        self._manage_grid(data)
        if not self.state.grid: return []
            
        grid = self.state.grid
        v_bounds = {"top_2": grid["layers"][-1]["top"], "bottom_2": grid["layers"][0]["bottom"]}
        breaker_status = self.breaker.check(data.close, v_bounds)
        
        if breaker_status in ["REBUILD_DOWN", "REBUILD_UP"]:
            if (breaker_status == "REBUILD_DOWN" and not macd_golden) or \
               (breaker_status == "REBUILD_UP" and not macd_dead):
                self.state.grid_period = self.params.get('grid_period_rebuild', 4)
                self._trace(ts_ms, f"⚠️ 破位重置网格 ({breaker_status})")
                self._rebuild_grid()
            else:
                self.state.is_halted = True
                self.state.halt_reason = "破位但指标对冲，等待中"
                self._trace(ts_ms, f"🛑 熔断: {self.state.halt_reason}")
            return []
            
        if breaker_status in ["OBSERVING_UP", "OBSERVING_DOWN"]:
            self.state.is_halted = True
            self.state.halt_reason = f"观察期 ({breaker_status})"
            self._trace(ts_ms, f"👀 {self.state.halt_reason}")
            return []
            
        self.state.is_halted, self.state.halt_reason = False, ""
        if context: return self._generate_signals(data, context, ts_ms)
        return []

    def _update_data(self, data: MarketData):
        ts = data.timestamp
        bar_1m_ts = ts.replace(second=0, microsecond=0)
        if self._data_1m and self._data_1m[-1].timestamp.replace(second=0, microsecond=0) == bar_1m_ts:
            last = self._data_1m[-1]
            self._data_1m[-1] = MarketData(
                timestamp=data.timestamp, symbol=data.symbol, open=last.open,
                high=max(last.high, data.high), low=min(last.low, data.low),
                close=data.close, volume=data.volume
            )
        else:
            self._data_1m.append(data)
        
        period_5m_ts = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        if self._last_5m_ts is None or period_5m_ts > self._last_5m_ts:
            self._last_5m_ts = period_5m_ts
            self._data_5m.append({'timestamp': period_5m_ts, 'open': data.open, 'high': data.high, 'low': data.low, 'close': data.close, 'volume': data.volume})
        else:
            bar = self._data_5m[-1]
            bar['high'], bar['low'], bar['close'] = max(bar['high'], data.high), min(bar['low'], data.low), data.close

    def _rebuild_grid(self):
        minutes_lookback = self.state.grid_period * 60
        history = list(self._data_1m)[-minutes_lookback:]
        vol_thr = self.params.get('volatility_threshold', 0.012)
        
        # 记录旧网格的锁定状态以便继承
        old_locks = {}
        if self.state.grid and "layers" in self.state.grid:
            for l in self.state.grid["layers"]:
                if l.get("locked"):
                    old_locks[l["index"]] = l.get("position", 0)

        new_grid = GridCalculator.calculate_grid(history, self.state.grid_period, vol_thr)
        if new_grid:
            self.state.grid = new_grid
            lines = [new_grid["layers"][0]["bottom"]]
            for l in new_grid["layers"]: lines.append(l["top"])
            self.state.grid_lines = lines
            self.state.l0_idx = next((i for i, l in enumerate(new_grid["layers"]) if l["type"] == "BUFFER"), 0)
            
            # [核心修复] 锁继承：如果新网格的层索引在旧网格中是锁定的，且当前槽位中确有对应，则继承锁定
            # 这样可以防止重构瞬间产生的重复买入
            active_layers = {s["layer_idx"] for s in self.state.slots}
            for l in self.state.grid["layers"]:
                if l["index"] in active_layers:
                    l["locked"] = True
                    # 尝试从 slots 中累加该层的持仓量
                    l["position"] = sum(s["size"] for s in self.state.slots if s["layer_idx"] == l["index"])

    def _manage_grid(self, data: MarketData):
        if self.state.grid is None and len(self._data_1m) >= 360:
            self._rebuild_grid()

    def _generate_signals(self, data: MarketData, context: StrategyContext, ts_ms: int) -> List[Signal]:
        signals = []
        pos = context.positions.get(self.symbol)
        pos_size = float(pos.size) if pos else 0.0
        price, grid = data.close, self.state.grid
        if not grid or not grid.get('layers'): return signals
        
        current_layer = next((l for l in grid["layers"] if l["bottom"] <= price <= l["top"]), None)
        if not current_layer or current_layer["index"] == 0: return signals
        
        layer_idx = current_layer["index"]
        price_buff = self.params.get('price_buffer_pct', 0.0002)

        if layer_idx > 0 and pos_size > 0 and self.state.slots:
            is_triggered = False
            if price >= current_layer["mid"]:
                if current_layer["type"] == "VIRTUAL":
                    if self.state.current_rsi > self.params.get('rsi_sell', 75) or self._macd_dead:
                        is_triggered = True
                else: is_triggered = True
            
            if is_triggered:
                if self.state.last_sell_price > 0 and abs(price - self.state.last_sell_price) / self.state.last_sell_price < price_buff:
                    return signals
                target_slot = self.state.slots.pop()
                sell_size = min(target_slot["size"], pos_size)
                if sell_size > 0:
                    signals.append(Signal(timestamp=data.timestamp, symbol=self.symbol, side=Side.SELL, size=sell_size, reason=f"LIFO Sell L({layer_idx}) match L({target_slot['layer_idx']})"))
                    buy_layer = next((l for l in grid["layers"] if l["index"] == target_slot["layer_idx"]), None)
                    if buy_layer: buy_layer['locked'], buy_layer['position'] = False, max(0, buy_layer['position'] - sell_size)
                    self.state.last_sell_price = price
                    self._trace(ts_ms, f"卖出: L({layer_idx}) 匹配 L({target_slot['layer_idx']})")

        if layer_idx < 0:
            is_triggered = False
            if price <= current_layer["mid"] and not current_layer["locked"]:
                if current_layer["type"] == "VIRTUAL":
                    if self.state.current_rsi < self.params.get('rsi_buy', 25) or self._macd_golden:
                        is_triggered = True
                else: is_triggered = True
            
            if is_triggered:
                if self.state.last_buy_price > 0 and abs(price - self.state.last_buy_price) / self.state.last_buy_price < price_buff:
                    return signals
                buy_usdt = (self.total_capital / grid["n_layers"]) * (2.0 if current_layer["type"] == "VIRTUAL" else 1.0)
                if context.cash >= buy_usdt * 0.98:
                    signals.append(Signal(timestamp=data.timestamp, symbol=self.symbol, side=Side.BUY, size=buy_usdt, meta={'size_in_quote': True, "layer_idx": layer_idx}))
                    self.state.last_buy_price = price
                    self.state.slots.append({"size": buy_usdt / price, "buy_price": price, "layer_idx": layer_idx, "ts": data.timestamp})
                    current_layer['locked'] = True
                    current_layer['position'] += (buy_usdt / price)
                    self._trace(ts_ms, f"买入: L({layer_idx}) | {buy_usdt:.1f} USDT")

        return signals

    def _trace(self, ts_ms: int, msg: str):
        """记录决策追踪日志"""
        if ts_ms not in self.decision_trace:
            self.decision_trace[ts_ms] = []
        self.decision_trace[ts_ms].append(msg)

    def get_state(self) -> Dict[str, Any]:
        """导出策略核心内存状态"""
        serialized_slots = []
        for s in self.state.slots:
            s_copy = s.copy()
            if isinstance(s_copy.get('ts'), datetime):
                s_copy['ts'] = s_copy['ts'].isoformat()
            serialized_slots.append(s_copy)
            
        # 处理网格配置中的 datetime
        grid_config = self.state.grid.copy() if self.state.grid else None
        if grid_config and isinstance(grid_config.get('created_at'), datetime):
            grid_config['created_at'] = grid_config['created_at'].isoformat()
            
        return {
            'slots': serialized_slots,
            'last_buy_price': self.state.last_buy_price,
            'last_sell_price': self.state.last_sell_price,
            'grid_period': self.state.grid_period,
            'grid_config': grid_config
        }

    def set_state(self, state: Dict[str, Any]):
        """恢复策略核心内存状态"""
        if not state: return
        
        raw_slots = state.get('slots', [])
        recovered_slots = []
        for s in raw_slots:
            if s.get('ts') and isinstance(s['ts'], str):
                try: s['ts'] = datetime.fromisoformat(s['ts'])
                except: pass
            recovered_slots.append(s)
        self.state.slots = recovered_slots
        
        self.state.last_buy_price = state.get('last_buy_price', 0.0)
        self.state.last_sell_price = state.get('last_sell_price', 0.0)
        self.state.grid_period = state.get('grid_period', 6)
        
        if state.get('grid_config'):
            self.state.grid = state['grid_config']
            # 恢复 grid 中的 datetime
            if self.state.grid.get('created_at') and isinstance(self.state.grid['created_at'], str):
                try:
                    self.state.grid['created_at'] = datetime.fromisoformat(self.state.grid['created_at'])
                except:
                    pass
            
            lines = [self.state.grid["layers"][0]["bottom"]]
            for l in self.state.grid["layers"]: lines.append(l["top"])
            self.state.grid_lines = lines
            self.state.l0_idx = next((i for i, l in enumerate(self.state.grid["layers"]) if l["type"] == "BUFFER"), 0)

        print(f"[grid-v60] 已恢复策略状态: {len(self.state.slots)} 个活跃槽位")

    def get_status(self, context: Optional[StrategyContext] = None) -> Dict[str, Any]:
        """返回适配 Dashboard v60 的完整状态字典"""
        is_bullish = self.state.macdhist > 0
        grid_lower = self.state.grid["base_bottom"] if self.state.grid else 0.0
        grid_upper = self.state.grid["base_top"] if self.state.grid else 0.0
        
        # 计算持仓层数
        pos_count = len(self.state.slots)
        
        # 构造 6.0 模板所需的完整字段
        return {
            'name': self.name,
            'current_rsi': round(self.state.current_rsi, 2),
            'rsi_oversold': self.params.get('rsi_buy', 25.0),
            'rsi_overbought': self.params.get('rsi_sell', 75.0),
            
            # MACD 原始值 (供 Runner 构造 history_macd)
            'macd': self.state.macd,
            'macdsignal': self.state.macdsignal,
            'macdhist': self.state.macdhist,
            'macd_trend': "牛市" if is_bullish else "熊市",
            
            # 信号箱显示
            'signal_text': f"熔断: {self.state.halt_reason}" if self.state.is_halted else "运行中",
            'signal_color': 'sell' if self.state.macdhist < 0 else 'buy',
            'signal_strength': f"{abs(self.state.macdhist)*100:.2f}",
            
            # 市场深度面板 (部分依赖 indicators)
            'atrVal': 0.0, # 当前 V6 indicators 未实现 ATR，保留占位
            'marketRegime': "稳定" if abs(self.state.macdhist) < 0.0001 else ("波动" if is_bullish else "下行"),
            'vol_trend': "放量" if self.state.last_volume > self.params.get('vol_ma', 0) else "缩量",
            'current_volume': self.state.last_volume,
            
            # 网格状态
            'grid_range': f"{grid_lower:.1f} - {grid_upper:.1f}",
            'grid_lower': grid_lower,
            'grid_upper': grid_upper,
            'grid_lines': self.state.grid_lines,
            'position_count': pos_count,
            
            # 账户摘要 (Dashboard 会优先使用 context 数据，这里提供备份)
            'position_size': sum(s['size'] for s in self.state.slots),
            'params': self.params,
            
            # 活跃槽位详情 (适配 v60 看板的 [买入槽位追踪])
            'slots': [
                {
                    'idx': s.get('layer_idx'),
                    'price': s.get('buy_price'),
                    'size': s.get('size'),
                    'time': int(s.get('ts').timestamp() * 1000) if s.get('ts') else None
                } for s in self.state.slots
            ],

            # 波段参考 (如果有的话)
            'pivots': getattr(self.indicators, 'pivots', {'pivots_high': [], 'pivots_low': []})
        }
