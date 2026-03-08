import os
import json
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from collections import deque

from core import (
    MarketData, Signal, Side, OrderType, 
    FillEvent, Position, StrategyContext
)
from strategies.base import BaseStrategy

class GridStrategyV65B(BaseStrategy):
    """
    V6.5B 动态网格交易策略 (DOGE-PRO)
    
    基于 V6.5A 架构，针对 DOGE 等高波动币种优化：
    - 放宽 RSI 阈值，提高参与度
    - 缩短冷却时间，捕捉快速机会
    - 减少最大持仓层数，控制极端风险
    """

    def __init__(self, name: str = "Grid_V65B_DOGE", **params):
        super().__init__(name, **params)
        self.params_path = params.get('config_path', 'config/grid_v65b_doge_runtime.json')
        # 自动推导 meta 路径 (例如 runtime.json -> meta.json)
        self.meta_path = self.params_path.replace('runtime.json', 'meta.json')
        self.symbol = params.get('symbol', 'DOGE-USDT')
        self.param_metadata = {}
        self._load_params()

        # 数据缓存
        self._data_5m = deque(maxlen=400)   # 5m K线缓存 (约33小时，确保能看到完整日结构)
        self._data_15m = deque(maxlen=200)  # 15m 重采样缓存
        self._last_15m_ts: Optional[datetime] = None

        # 策略内部状态
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
        """加载运行参数与元数据说明"""
        # 1. 加载运行参数
        if os.path.exists(self.params_path):
            try:
                with open(self.params_path, 'r', encoding='utf-8') as f:
                    self.params.update(json.load(f))
            except Exception as e:
                print(f"[V6.5B] 加载参数失败: {e}")
        
        # 2. 加载元数据 (用于 Dashboard 说明面板)
        if os.path.exists(self.meta_path):
            try:
                with open(self.meta_path, 'r', encoding='utf-8') as f:
                    self.param_metadata = json.load(f)
            except Exception as e:
                print(f"[V6.5B] 加载元数据失败: {e}")

    def initialize(self):
        super().initialize()
        print(f"[V6.5B] {self.name} 初始化完成")

    def on_data(self, data: MarketData, context: Optional[StrategyContext]) -> List[Signal]:
        if not self._initialized:
            self.initialize()

        # 1. 更新数据与重采样 (5m -> 15m)
        self._update_data(data)
        
        # 指标计算需要足够数据
        if len(self._data_5m) < 30 or len(self._data_15m) < 30:
            return []

        # 2. 计算指标
        self._calculate_indicators()

        # 3. 熔断检测 (黑天鹅)
        if self._check_halt(data):
            return []

        # 4. 网格管理 (边界计算与重置)
        self._manage_grid(data)

        # 5. 信号生成
        if context:
            return self._generate_signals(data, context)
        return []

    def _update_data(self, data: MarketData):
        """更新 5m 数据并执行 15m 重采样
        
        关键：OKX 数据流每2秒推送一次同一根5分钟K线的最新状态，
        必须将同一5分钟周期的多次推送合并为一条记录，
        否则 _data_5m 里存的是2秒快照而非5分钟K线，所有指标计算都会错误。
        """
        ts = data.timestamp
        # 按5分钟取整作为当前K线的标识时间
        bar_ts = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        
        if self._data_5m and self._data_5m[-1].timestamp.replace(
                minute=(self._data_5m[-1].timestamp.minute // 5) * 5, 
                second=0, microsecond=0) == bar_ts:
            # 同一根5分钟K线：更新最后一条的 high/low/close/volume
            last = self._data_5m[-1]
            updated = MarketData(
                timestamp=data.timestamp,  # 用最新时间戳
                symbol=data.symbol,
                open=last.open,            # open 保持不变（该K线第一次的开盘价）
                high=max(last.high, data.high),
                low=min(last.low, data.low),
                close=data.close,          # close 用最新价
                volume=data.volume         # OKX每次推送的已经是这根5mK线的累计量，故直接覆盖
            )
            self._data_5m[-1] = updated
        else:
            # 新的5分钟周期：追加新记录
            self._data_5m.append(data)
        
        # 15m 重采样逻辑 (以 0, 15, 30, 45 分钟为界)
        period_ts = ts.replace(minute=(ts.minute // 15) * 15, second=0, microsecond=0)
        
        if self._last_15m_ts is None or period_ts > self._last_15m_ts:
            # 新的 15m 周期开始
            self._last_15m_ts = period_ts
            self._data_15m.append({
                'timestamp': period_ts,
                'open': data.open, 'high': data.high, 
                'low': data.low, 'close': data.close, 
                'volume': data.volume
            })
        else:
            # 更新当前的 15m 周期
            bar = self._data_15m[-1]
            bar['high'] = max(bar['high'], data.high)
            bar['low'] = min(bar['low'], data.low)
            bar['close'] = data.close
            
            # 计算 15m 周期内的精确 volume：
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
        """计算 RSI(5m), MACD(15m), ATR(5m)"""
        # 5m RSI
        closes_5m = pd.Series([d.close for d in self._data_5m])
        self.state.current_rsi = self._rsi(closes_5m, self.params.get('rsi_period', 14))
        
        # 5m ATR
        highs = pd.Series([d.high for d in self._data_5m])
        lows = pd.Series([d.low for d in self._data_5m])
        closes = pd.Series([d.close for d in self._data_5m])
        atr_val = self._atr(highs, lows, closes, self.params.get('atr_period', 14))
        self.state.atr = atr_val
        # 统计过去 6 小时的 ATR 均值 (72 根 5m)
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

        # 波段点识别 (3高3低逻辑，集成 V4.0)
        df_5m = pd.DataFrame(list(self._data_5m))
        self._find_pivot_points(df_5m)

    def _manage_grid(self, data: MarketData):
        """以波段结构点驱动动态网格 (3高3低)"""
        now = data.timestamp
        
        # 仅在有完整波段数据时更新网格
        if not self.state.pivots_high or not self.state.pivots_low:
            # 回退到过去 6 小时 ATR 逻辑 (防止冷启动)
            lookback = self.params.get('grid_lookback_hours', 6)
            bars = list(self._data_5m)[-int(lookback * 12):]
            if not bars: return
            upper = max(b.high for b in bars)
            lower = min(b.low for b in bars)
        else:
            # 使用3高3低的极值作为网格边界
            upper = max(p['price'] for p in self.state.pivots_high)
            lower = min(p['price'] for p in self.state.pivots_low)

        # 缓冲区处理
        range_size = upper - lower
        if range_size <= 0: range_size = upper * 0.01
        buffer = self.params.get('grid_buffer', 0.02)
        
        self.state.grid_upper = upper * (1 + buffer)
        self.state.grid_lower = lower * (1 - buffer)
        
        # 生成网格线
        layers = self.params.get('grid_layers', 4)
        self.state.grid_lines = np.linspace(self.state.grid_lower, self.state.grid_upper, layers + 1).tolist()
        self.state.last_grid_reset = now

    def _check_halt(self, data: MarketData) -> bool:
        """黑天鹅检测"""
        if self.state.is_halted:
            if self.state.resume_time and data.timestamp >= self.state.resume_time:
                self.state.is_halted = False
                print(f"[V6.5B] 恢复交易")
            else:
                return True
        
        # ATR 异常检测
        if self.state.atr > self.state.atr_ma * self.params.get('atr_blackswan_mult', 3.0):
            self.state.is_halted = True
            self.state.halt_reason = "High Volatility (ATR Blackswan)"
            self.state.resume_time = data.timestamp + timedelta(minutes=self.params.get('atr_cooldown_min', 30))
            print(f"[V6.5B] 触发熔断: {self.state.halt_reason}")
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

        # --- 全局冷却锁：防连续买单与瞬时"一买就卖"异常 ---
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
                sig_type = "GOLD (MACD死叉)"
            elif self.state.current_rsi > rsi_sell_silver:
                sell_layers = 1
                sig_type = "SILVER (超买)"
                
            if sell_layers > 0:
                sell_layers = min(sell_layers, current_layers) if current_layers > 0 else 1
                sell_ratio = sell_layers / current_layers if current_layers > 0 else 1.0
                reason = f"MTF Sell [{sig_type}]: RSI={self.state.current_rsi:.1f} 抛售层数={sell_layers} 剩余持仓~={max(0, current_layers-sell_layers)}层"
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
                sig_type = "GOLD (MACD金叉)"
            else:
                buy_layers = 1
                sig_type = "SILVER (超卖)"
            
            buy_layers = min(buy_layers, self.params.get('grid_layers', 4) - current_layers)
            if buy_layers > 0:
                can_buy = True

        if can_buy:
            buy_usdt = layer_value * buy_layers
            if context.cash >= buy_usdt * 0.95:  
                reason = f"MTF Buy [{sig_type}]: RSI={self.state.current_rsi:.1f} 买入层数={buy_layers} 当前已有={current_layers}层"
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

    # --- 技术指标计算工具 (精简版) ---
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
        寻找最近的 n 个结构性波段高点和低点
        核心思路：V4.0 的"取最近 N 个转折点"，而非"取 N 个最极端价格"
        """
        if len(self._data_5m) < 30: return
        
        n = 3  # 3高3低
        # 局部确认判定窗口 (增大到 10 根 = 50 分钟，过滤短期噪点)
        window_size = 10
        
        data_list = list(self._data_5m)
        highs = df['high'].values
        lows = df['low'].values
        curr_idx = len(df) - 1
        
        all_highs = []
        all_lows = []

        # 全量扫描缓存中的所有数据
        for i in range(window_size, curr_idx + 1):
            # --- 低点检测：比左边 window_size 根都低 ---
            if lows[i] <= min(lows[i-window_size:i]):
                is_pivot = False
                if i > curr_idx - window_size:
                    # 实时区：是 i 到当前之间的最低点
                    if i == curr_idx or lows[i] <= min(lows[i+1:]):
                        is_pivot = True
                else:
                    # 确认区：比右边 window_size 根也低
                    if lows[i] < min(lows[i+1 : i+window_size+1]):
                        is_pivot = True
                
                if is_pivot:
                    all_lows.append({'price': float(lows[i]), 'time': data_list[i].timestamp.isoformat(), 'index': i})

            # --- 高点检测：比左边 window_size 根都高 ---
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

        # 取最近 n 个结构转折点 (从右向左，间隔至少 window_size 根防重叠)
        def _get_recent_n(pivots):
            res = []
            for p in reversed(pivots):  # 从最新往回取
                if not res or (res[-1]['index'] - p['index']) >= window_size:
                    res.append(p)
                if len(res) >= n:
                    break
            res.reverse()  # 恢复时间顺序
            return res

        self.state.pivots_high = _get_recent_n(all_highs)
        self.state.pivots_low = _get_recent_n(all_lows)


    def get_status(self, context: Optional[StrategyContext] = None) -> Dict[str, Any]:
        # 计算辅助显示指标
        is_bullish = self.state.macdhist > 0
        macd_trend = "强牛" if is_bullish and self.state.macdhist > self.state.macdhist_prev else "牛市" if is_bullish else "震荡"
        if self.state.macdhist < 0:
            macd_trend = "强熊" if self.state.macdhist < self.state.macdhist_prev else "熊市"
        
        # 信号状态判定 (用于 UI 显示)
        signal_text = "等待趋势"
        signal_color = "neutral"
        signal_strength = "--"

        if self.state.is_halted:
            signal_text = f"熔断: {self.state.halt_reason}"
            signal_color = "sell"
        elif is_bullish:
            signal_color = "buy"
            # 计算信号强度: 基于 RSI 接近程度和 MACD 增长
            rsi_dist = max(0, self.params.get('rsi_buy_threshold', 35) - self.state.current_rsi)
            if self.state.current_rsi < self.params.get('rsi_buy_threshold', 35):
                signal_text = "多头择时买入"
                signal_strength = "强" if rsi_dist > 5 else "高"
            else:
                signal_text = "趋势持有中"
                signal_strength = "中"
        else:
            signal_strength = "弱" if self.state.macdhist < -5 else "低"

        # 量能分析
        vol_current = 0
        vol_trend = "持平"
        if self._data_5m:
            df = pd.DataFrame(list(self._data_5m))
            vol_current = df['volume'].iloc[-1]
            vol_ma = df['volume'].rolling(20).mean().iloc[-1]
            if not np.isnan(vol_ma) and vol_ma > 0:
                ratio = vol_current / vol_ma
                if ratio > 1.5: vol_trend = "放量"
                elif ratio < 0.6: vol_trend = "缩量"

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
                # DOGE 价格较低，调整层数估算
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
            'marketRegime': "上升通道" if is_bullish else "震荡下行" if self.state.macdhist < -5 else "调整阶段",
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
