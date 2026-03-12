import os
import json
import numpy as np
import pandas as pd
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from collections import deque

from core import (
    MarketData, Signal, Side, OrderType, 
    FillEvent, Position, StrategyContext
)
from strategies.base import BaseStrategy

# ============================================================
# V6.0-Revival 高性能增量指标引擎 (1m / 5m)
# ============================================================

class IncrementalIndicatorsV6:
    def __init__(self, p: dict):
        self.p = p
        self.count_1m = 0
        self.count_5m = 0
        
        # RSI 1m (SMA Based)
        self.rsi_period = p.get('rsi_period', 14)
        self.gain_dq = deque(maxlen=self.rsi_period)
        self.loss_dq = deque(maxlen=self.rsi_period)
        self.gain_sum = 0.0
        self.loss_sum = 0.0
        self.prev_close_1m = 0.0
        
        # MACD 1m (EMA Based - Fixed Cycle)
        self.m_fast = p.get('macd_fast', 12)
        self.m_slow = p.get('macd_slow', 26)
        self.m_sig = p.get('macd_signal', 9)
        self.ema_f = 0.0
        self.ema_s = 0.0
        self.ema_sig = 0.0
        self.count_macd = 0  # 追踪 MACD 更新次数
        self.alpha_f = 2.0 / (self.m_fast + 1)
        self.alpha_s = 2.0 / (self.m_slow + 1)
        self.alpha_sig = 2.0 / (self.m_sig + 1)

    def update_1m(self, d: MarketData, commit: bool = True):
        c = d.close
        if self.count_1m == 0:
            if commit:
                self.prev_close_1m = c
                self.count_1m += 1
            return 50.0

        diff = c - self.prev_close_1m
        gain = max(diff, 0); loss = max(-diff, 0)

        def get_sma(dq, cur_sum, val, p):
            count = len(dq)
            if count == 0: return val
            s = cur_sum + val - (dq[0] if count == p else 0)
            return s / (count if count < p else p)

        rsi_g = get_sma(self.gain_dq, self.gain_sum, gain, self.rsi_period)
        rsi_l = get_sma(self.loss_dq, self.loss_sum, loss, self.rsi_period)
        rs = rsi_g / rsi_l if rsi_l > 1e-9 else 100.0
        rsi = 100.0 - (100.0 / (1.0 + rs)) if rsi_l > 1e-9 else 100.0
        
        if commit:
            if len(self.gain_dq) == self.rsi_period: self.gain_sum -= self.gain_dq.popleft()
            self.gain_dq.append(gain); self.gain_sum += gain
            if len(self.loss_dq) == self.rsi_period: self.loss_sum -= self.loss_dq.popleft()
            self.loss_dq.append(loss); self.loss_sum += loss
            self.prev_close_1m = c
            self.count_1m += 1
            
        return rsi

    def update_1m_macd(self, close: float, commit: bool = True):
        """
        MACD 1m 实时指标计算
        """
        if self.count_macd == 0:
            if commit:
                self.ema_f = self.ema_s = close
                self.count_macd += 1
            return 0.0, 0.0, 0.0

        f = close * self.alpha_f + self.ema_f * (1 - self.alpha_f)
        s = close * self.alpha_s + self.ema_s * (1 - self.alpha_s)
        macd = f - s
        
        # 核心修复：信号线初始化
        # 如果是第一次计算出 macd (count=1)，信号线应直接等于 macd，而不是从 0 开始平滑
        if self.count_macd == 1:
            sig = macd
        else:
            sig = macd * self.alpha_sig + self.ema_sig * (1 - self.alpha_sig)
            
        hist = macd - sig

        if commit:
            self.ema_f, self.ema_s, self.ema_sig = f, s, sig
            self.count_macd += 1
            
        return macd, sig, hist


# ============================================================
# V6.0-Revival 网格计算与熔断
# ============================================================

class GridCalculator:
    """网格计算器 (V6.0-Revival 分段去极值法)"""
    
    @staticmethod
    def calculate_grid(price_data: List[MarketData], period_hours: int = 6, vol_threshold: float = 0.012) -> Dict:
        """
        计算6小时（或4小时）网格
        1. 分5段，取每段最高最低点
        2. 去极值（去1最大1最小）
        3. 剩余3高3低取平均
        """
        if len(price_data) < 10:
            return None
            
        segment_size = max(1, len(price_data) // 5)
        
        highs = []
        lows = []
        
        for i in range(5):
            segment = price_data[i*segment_size : (i+1)*segment_size]
            if not segment: continue
            highs.append(max([c.high for c in segment]))
            lows.append(min([c.low for c in segment]))
        
        if len(highs) >= 5:
            # 去极值
            highs.remove(max(highs))
            highs.remove(min(highs))
            lows.remove(max(lows))
            lows.remove(min(lows))
            
        base_top = sum(highs) / len(highs)
        base_bottom = sum(lows) / len(lows)
        
        # 计算波动率定层数
        mid_price = (base_top + base_bottom) / 2
        volatility = (base_top - base_bottom) / mid_price if mid_price > 0 else 0
        n_layers = 7 if volatility >= vol_threshold else 5
        
        # 生成实体层
        layers = []
        step = (base_top - base_bottom) / n_layers if n_layers > 0 else 0
        
        for i in range(n_layers):
            layer_bottom = base_bottom + i * step
            layer_top = layer_bottom + step
            layer_mid = (layer_bottom + layer_top) / 2
            
            layers.append({
                "index": i,
                "bottom": layer_bottom,
                "top": layer_top,
                "mid": layer_mid,
                "buy_zone": layer_bottom + (layer_top - layer_bottom) * 0.5,
                "sell_zone": layer_bottom + (layer_top - layer_bottom) * 0.5,
                "locked": False,
                "position": 0.0
            })
        
        # 生成虚拟层
        virtual_step = step * 0.5
        virtual_top_1 = base_top + virtual_step
        virtual_top_2 = virtual_top_1 + virtual_step
        virtual_bottom_1 = base_bottom - virtual_step
        virtual_bottom_2 = virtual_bottom_1 - virtual_step
        
        return {
            "base_top": base_top,
            "base_bottom": base_bottom,
            "volatility": volatility,
            "n_layers": n_layers,
            "layers": layers,
            "virtual": {
                "top_1": virtual_top_1,
                "top_2": virtual_top_2,
                "bottom_1": virtual_bottom_1,
                "bottom_2": virtual_bottom_2
            },
            "created_at": datetime.now(),
            "period_used": period_hours
        }

class CircuitBreaker:
    """1小时物理熔断器"""
    def __init__(self, observation_period: int = 3600):
        self.status = "NORMAL"  # NORMAL / OBSERVING
        self.observation_start = None
        self.observation_period = observation_period
    
    def check(self, price: float, virtual_grid: Dict) -> str:
        if not virtual_grid: return "NORMAL"
        
        if self.status == "NORMAL":
            if price > virtual_grid["top_2"] or price < virtual_grid["bottom_2"]:
                self.status = "OBSERVING"
                self.observation_start = datetime.now()
                return "OBSERVING"
            return "NORMAL"
            
        elif self.status == "OBSERVING":
            if not self.observation_start:
                return "NORMAL"
            
            elapsed = (datetime.now() - self.observation_start).total_seconds()
            if virtual_grid["bottom_2"] <= price <= virtual_grid["top_2"]:
                self.status = "NORMAL"
                self.observation_start = None
                return "NORMAL"
                
            if elapsed >= self.observation_period:
                self.status = "NORMAL"
                self.observation_start = None
                return "REBUILD"
            return "OBSERVING"
        return "NORMAL"


@dataclass
class StrategyState:
    current_rsi: float = 50.0
    macd: float = 0.0
    macdsignal: float = 0.0
    macdhist: float = 0.0
    macdhist_prev: float = 0.0
    
    grid: Optional[Dict] = None
    grid_period: int = 6
    
    is_halted: bool = False
    halt_reason: str = ""
    resume_time: Optional[datetime] = None
    last_volume: float = 0.0
    grid_lines: List[float] = field(default_factory=list)


class GridMTFStrategyV6_0(BaseStrategy):
    """
    V6.0-Revival 动态网格策略
    """
    def __init__(self, name: str = "Grid_V60_Revival", **params):
        super().__init__(name, **params)
        
        current_file_dir = Path(__file__).parent.resolve()
        config_dir = current_file_dir.parent / "config"
        
        self.default_params_path = str(config_dir / 'grid_v60_default.json')
        self.params_path = str(config_dir / 'grid_v60_runtime.json')
        self.meta_path = self.params_path.replace('runtime.json', 'meta.json')
        self.symbol = params.get('symbol', 'BTCUSDT')
        self._data_1m = deque(maxlen=400)
        self._data_5m = deque(maxlen=100)
        
        self.state = StrategyState()

        self.param_metadata = {}
        self._load_params()
        
        self._last_1m_ts: Optional[datetime] = None
        self._last_5m_ts: Optional[datetime] = None
        self._last_5m_bar_close = 0.0
        self._last_1m_bar = None

        self.state = StrategyState()
        self.indicators = IncrementalIndicatorsV6(self.params)
        self.breaker = CircuitBreaker(self.params.get('observation_period', 3600))
        
        self.total_capital = self.params.get('total_capital', 10000.0)

    def _load_params(self):
        if os.path.exists(self.default_params_path):
            try:
                with open(self.default_params_path, 'r', encoding='utf-8') as f:
                    self.params.update(json.load(f))
            except Exception as e:
                print(f"[V6.0] Load default params failed: {e}")

        if os.path.exists(self.params_path):
            try:
                with open(self.params_path, 'r', encoding='utf-8') as f:
                    self.params.update(json.load(f))
            except Exception as e:
                print(f"[V6.0] Load runtime params failed: {e}")
        
        if os.path.exists(self.meta_path):
            try:
                with open(self.meta_path, 'r', encoding='utf-8') as f:
                    self.param_metadata = json.load(f)
            except Exception as e:
                print(f"[V6.0] Load meta failed: {e}")
                
        self.state.grid_period = self.params.get('grid_period_initial', 6)

    def initialize(self):
        super().initialize()
        self.state = StrategyState()
        self.indicators = IncrementalIndicatorsV6(self.params)
        self.breaker = CircuitBreaker(self.params.get('observation_period', 3600))
        self._last_1m_ts = None
        self._last_1m_bar = None
        self._data_1m.clear()
        self._data_5m.clear()
        self._last_5m_ts = None
        print(f"[V6.0-Revival] {self.name} 初始化完成")

    def on_data(self, data: MarketData, context: Optional[StrategyContext]) -> List[Signal]:
        # 0. 1m K线合并与指标更新 (RSI)
        is_new_1m_bar = (not self._last_1m_ts) or (data.timestamp > self._last_1m_ts)
        if is_new_1m_bar:
            if self._last_1m_bar:
                self.indicators.update_1m(self._last_1m_bar, commit=True)
                self.indicators.update_1m_macd(self._last_1m_bar.close, commit=True)
            self._last_1m_ts = data.timestamp
            self._update_data(data)
        self._last_1m_bar = data

        if len(self._data_1m) < 10: return []

        # 1. 指标实时预览
        rsi = self.indicators.update_1m(data, commit=False)
        self.state.current_rsi = rsi
        self.state.last_volume = data.volume

        macd, sig, hist = self.indicators.update_1m_macd(data.close, commit=False)
        self.state.macd = macd
        self.state.macdsignal = sig
        self.state.macdhist = hist

        # 2. 网格构建与熔断处理
        self._manage_grid(data)
        
        if not self.state.grid:
            return []

        breaker_status = self.breaker.check(data.close, self.state.grid["virtual"])
        
        if breaker_status == "REBUILD":
            self.state.grid_period = self.params.get('grid_period_rebuild', 4)
            self._rebuild_grid()
            self.state.grid_period = self.params.get('grid_period_initial', 6)
            return []
            
        if breaker_status == "OBSERVING":
            self.state.is_halted = True
            self.state.halt_reason = "1小时黑天鹅观察期"
            return []
            
        self.state.is_halted = False
        self.state.halt_reason = ""

        # 3. 信号生成与仓位管理
        if context:
            return self._generate_signals(data, context)
        return []

    def _update_data(self, data: MarketData):
        ts = data.timestamp
        # 1. 处理 1分钟K线
        bar_1m_ts = ts.replace(second=0, microsecond=0)
        
        if self._data_1m and self._data_1m[-1].timestamp.replace(second=0, microsecond=0) == bar_1m_ts:
            last = self._data_1m[-1]
            updated = MarketData(
                timestamp=data.timestamp,
                symbol=data.symbol,
                open=last.open,
                high=max(last.high, data.high),
                low=min(last.low, data.low),
                close=data.close,
                volume=data.volume
            )
            self._data_1m[-1] = updated
        else:
            self._data_1m.append(data)
        
        # 2. 5m重采样 (供 MACD 使用)
        period_5m_ts = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        
        if self._last_5m_ts is None or period_5m_ts > self._last_5m_ts:
            self._last_5m_ts = period_5m_ts
            self._last_5m_bar_close = data.close
            self._data_5m.append({
                'timestamp': period_5m_ts,
                'open': data.open, 'high': data.high, 
                'low': data.low, 'close': data.close, 
                'volume': data.volume
            })
        else:
            bar = self._data_5m[-1]
            bar['high'] = max(bar['high'], data.high)
            bar['low'] = min(bar['low'], data.low)
            bar['close'] = data.close
<<<<<<< HEAD
            
            vol_sum = 0
            for i in range(len(self._data_1m) - 1, -1, -1):
                d = self._data_1m[i]
                d_period = d.timestamp.replace(minute=(d.timestamp.minute // 5) * 5, second=0, microsecond=0)
                if d_period < period_5m_ts: break
                if d_period == period_5m_ts:
=======
            # 计算 15m 周期内的精确 volume：
            # 找到在当前 15m 周期内（属于这段 period_ts），但【已经完结】（不仅指最新一根正在跑的）的所有 5m K线。
            # 直接遍历 self._data_5m 从后往前找，把 timestamp 大于等于 period_ts 且与 period_ts 属于同一 15m 窗口的所有完整 5m 累加。
            vol_sum = 0
            for i in range(len(self._data_5m) - 1, -1, -1):
                d = self._data_5m[i]
                d_period_ts = d.timestamp.replace(minute=(d.timestamp.minute // 15) * 15, second=0, microsecond=0)
                if d_period_ts < period_ts:
                    break  # 已经跨越到上一个 15m 周期，停止
                if d_period_ts == period_ts:
                    # 只要是属于 this 15m 周期内的 5m K线，直接把它们内部已经整理好的 `volume` 加起来。
                    # 注意如果 `_data_5m` 已经是去重过的，那么最后一根就是包含当前 data.volume 的
>>>>>>> 5b4c418cc0d0db4c6afd0386967253223c3b26af
                    vol_sum += d.volume
            bar['volume'] = vol_sum

    def _rebuild_grid(self):
        minutes_lookback = self.state.grid_period * 60
        history = list(self._data_1m)[-minutes_lookback:]
        vol_thr = self.params.get('volatility_threshold', 0.012)
        new_grid = GridCalculator.calculate_grid(history, self.state.grid_period, vol_thr)
        if new_grid:
            self.state.grid = new_grid
            # 导出兼容 V8.5 可视化组件的 grid_lines
            lines = []
            v = new_grid["virtual"]
            lines.append(v["bottom_2"])
            lines.append(v["bottom_1"])
            for layer in new_grid["layers"]:
                lines.append(layer["bottom"])
            lines.append(new_grid["layers"][-1]["top"])
            lines.append(v["top_1"])
            lines.append(v["top_2"])
            self.state.grid_lines = lines

    def _manage_grid(self, data: MarketData):
        # 初始化网格
        if self.state.grid is None:
            # 必须攒够 6 小时 (360 根 1m K线) 才能生成符合 V6.0 要求的初始网格
            if len(self._data_1m) >= 360:
                self._rebuild_grid()

    def _generate_signals(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        signals = []
        pos = context.positions.get(self.symbol)
        pos_size = float(pos.size) if pos else 0.0
        
        self.state.macdhist_prev = self.state.macdhist
        
        price = data.close
        grid = self.state.grid
        if not grid: return signals
        
        rsi = self.state.current_rsi
        macd_golden = False
        macd_dead = False
        if len(self._data_5m) >= 2:
            sig = self.state.macdsignal
            # 金叉判定(简化版)：hist 从负变正，或者 hist 大于 0 且在增加
            # 严格按照原代码要求:
            if self.state.macdhist > 0 and self.state.macdhist_prev <= 0:
                macd_golden = True
            elif self.state.macdhist < 0 and self.state.macdhist_prev >= 0:
                macd_dead = True
                
        # 1. 确定当前所在的层和产生的信号
        buy_signals = []
        sell_signals = []
        layer_idx = -1
        
        for i, layer in enumerate(grid["layers"]):
            if layer["bottom"] <= price <= layer["top"]:
                layer_idx = i
                # 买入区 且 未被锁定
                if price <= layer["buy_zone"] and not layer["locked"]:
                    buy_signals.append("GRID")
                # 卖出区 且 持有这层的仓位
                if price >= layer["sell_zone"] and layer["position"] > 0:
                    sell_signals.append("GRID")
                break
                
        # 补充全局 RSI / MACD 信号
        rsi_buy_thr = self.params.get('rsi_buy', 25)
        rsi_sell_thr = self.params.get('rsi_sell', 75)
        rsi_extreme = self.params.get('rsi_extreme_sell', 85)
        
        if rsi < rsi_buy_thr: buy_signals.append("RSI")
        if rsi > rsi_extreme: sell_signals.append("RSI_EXTREME")
        elif rsi > rsi_sell_thr: sell_signals.append("RSI")
        
        if macd_golden: buy_signals.append("MACD")
        if macd_dead: sell_signals.append("MACD")
        
        # 2. 信号排斥处理：优先处理卖出/极端清仓，且确保同一 Bar 不会既买又卖
        if "RSI_EXTREME" in sell_signals and pos_size > 0:
            signals.append(Signal(
                timestamp=data.timestamp, symbol=self.symbol, side=Side.SELL,
                size=pos_size, reason="RSI_EXTREME(>85) 极端清仓",
                meta={
                    "rsi": self.state.current_rsi,
                    "macd_hist": self.state.macdhist,
                    "layer_idx": layer_idx,
                    "snapshot_pos": pos_size
                }
            ))
            # 全部卖出后重置网格状态
            for l in grid['layers']: l['locked'] = False; l['position'] = 0.0
            return signals # 极端清仓后直接返回，不进行后续买入
            
        # 计算需要卖出的具体数量（改为基于层的记录，更精准）
        layers_to_sell = 0
        if "GRID" in sell_signals:
            layers_to_sell = 1
            if "RSI" in sell_signals: layers_to_sell = 2
            if "MACD" in sell_signals: layers_to_sell = 4

        if layers_to_sell > 0 and pos_size > 0:
            n = grid["n_layers"]
            # 改进：优先卖出当前层所在的仓位，如果多层联动卖出，则按比例但受限于当前层记录
            if layer_idx >= 0:
                layer_pos = grid['layers'][layer_idx]['position']
                sell_size = (pos_size / n) * layers_to_sell # 保留公式但限制在真实持仓范围内
                sell_size = min(sell_size, pos_size, layer_pos if layer_pos > 0 else sell_size)
                
                if sell_size > 0:
                    signals.append(Signal(
                        timestamp=data.timestamp, symbol=self.symbol, side=Side.SELL,
                        size=sell_size, reason=f"MTF Sell: {layers_to_sell} Layers (Layer {layer_idx})",
                        meta={
                            "rsi": self.state.current_rsi,
                            "macd_hist": self.state.macdhist,
                            "layer_idx": layer_idx,
                            "snapshot_pos": pos_size,
                            "layers_to_sell": layers_to_sell
                        }
                    ))
                    # 更新层级状态
                    grid['layers'][layer_idx]['locked'] = False
                    grid['layers'][layer_idx]['position'] = max(0, grid['layers'][layer_idx]['position'] - sell_size)
                    return signals # 卖出信号触发后，不进行同 Bar 买入

        # 3. 买入逻辑 (只有在没有卖出信号时才执行)
        coef = 0.0
        if "GRID" in buy_signals:
            coef = 1.0
            if "RSI" in buy_signals: coef = 2.0
            if "MACD" in buy_signals: coef = 4.0
        else:
            if "RSI" in buy_signals: coef = 0.5
            elif "MACD" in buy_signals: coef = 0.25
            
        if coef > 0:
            n = grid["n_layers"]
            # 文档公式: base = btc_balance/n if btc_balance>0 else (current_cash/n/price)
            base = (pos_size / n) if pos_size > 0 else (context.cash / n / price)
            buy_size = base * coef
            
            # 风控限制 (MAX_SINGLE_POSITION=0.8)
            max_single_btc = (self.total_capital * self.params.get('max_single_position', 0.8)) / price
            buy_size = min(buy_size, max_single_btc)
            buy_usdt = buy_size * price
            
            if context.cash >= buy_usdt * 0.95 and buy_usdt > 10:
                # 再次检查：如果是 GRID 买入，必须确保层未锁定
                if "GRID" in buy_signals and layer_idx >= 0 and grid['layers'][layer_idx]['locked']:
                    return [] # 已锁定则跳过
                    
                signals.append(Signal(
                    timestamp=data.timestamp, symbol=self.symbol, side=Side.BUY,
                    size=buy_usdt, meta={
                        'size_in_quote': True,
                        "rsi": self.state.current_rsi,
                        "macd_hist": self.state.macdhist,
                        "layer_idx": layer_idx,
                        "snapshot_pos": pos_size,
                        "coef": coef
                    },
                    reason=f"MTF Buy: Coef={coef} Layer={layer_idx}"
                ))
                if layer_idx >= 0:
                    grid['layers'][layer_idx]['locked'] = True
                    grid['layers'][layer_idx]['position'] += buy_size

        return signals

    def get_status(self, context: Optional[StrategyContext] = None) -> Dict[str, Any]:
        is_bullish = self.state.macdhist > 0
        macd_trend = "强牛" if is_bullish and self.state.macdhist > self.state.macdhist_prev else "牛市" if is_bullish else "震荡"
        if self.state.macdhist < 0:
            macd_trend = "强熊" if self.state.macdhist < self.state.macdhist_prev else "熊市"
        
        signal_text = "等待配置"
        signal_color = "neutral"
        
        if self.state.is_halted:
            signal_text = f"熔断: {self.state.halt_reason}"
            signal_color = "sell"
        elif is_bullish:
            signal_color = "buy"
            signal_text = "趋势持有中"
            
        pos_size = 0.0
        pos_avg_price = 0.0
        pos_unrealized_pnl = 0.0
        if context and self.symbol in context.positions:
            pos = context.positions[self.symbol]
            pos_size = float(pos.size)
            pos_avg_price = float(pos.avg_price)
            pos_unrealized_pnl = float(pos.unrealized_pnl)

        grid_lower = self.state.grid["base_bottom"] if self.state.grid else 0.0
        grid_upper = self.state.grid["base_top"] if self.state.grid else 0.0
        grid_lines = []
        layers_info = []
        if self.state.grid:
            grid_lines.append(self.state.grid["layers"][0]["bottom"])
            for l in self.state.grid["layers"]:
                grid_lines.append(l["top"])
                layers_info.append(f"Layer {l['index']}: {'Locked' if l['locked'] else 'Open'} (Pos: {l['position']:.4f})")

        return {
            'name': self.name,
            'current_rsi': round(self.state.current_rsi, 2),
            'macd': round(self.state.macd, 4),
            'macdsignal': round(self.state.macdsignal, 4),
            'macdhist': round(self.state.macdhist, 4),
            'atr': 0.0,
            'atrVal': 0.0,
            'macd_trend': macd_trend,
            'signal_text': signal_text,
            'signal_color': signal_color,
            'signal_strength': "中",
            'position_size': pos_size,
            'position_avg_price': pos_avg_price,
            'position_unrealized_pnl': pos_unrealized_pnl,
            'grid_lower': round(grid_lower, 2),
            'grid_upper': round(grid_upper, 2),
            'grid_range': f"{grid_lower:.1f} - {grid_upper:.1f}",
            'grid_lines': grid_lines,
            'layers_status': layers_info,
            'rsi_oversold': self.params.get('rsi_buy', 25),
            'rsi_overbought': self.params.get('rsi_sell', 75),
            'position_count': self.state.grid["n_layers"] if self.state.grid else 0,
            'marketRegime': "上升通道" if is_bullish else "调整阶段",
            'vol_trend': "持平",
            'current_volume': round(self.state.last_volume, 2),
            'is_halted': self.state.is_halted,
            'halt_reason': self.state.halt_reason,
            'pivots': {'pivots_high': [], 'pivots_low': []},
            'params': self.params,
            'param_metadata': self.param_metadata
        }
