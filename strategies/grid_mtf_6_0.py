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

class GridMTFStrategyV6_0(BaseStrategy):
    """
    V6.0-MTF 多周期自适应网格策略
    
    核心特性：
    1. MTF (Multi-Timeframe): 5m 进场，15m 趋势过滤
    2. 动态网格：基于过去 6 小时 ATR 和高低点动态重置边界
    3. 非线性加仓：金字塔加仓模型
    4. 趋势自适应止盈：根据 15m MACD 强度调整卖出阈值
    5. 黑天鹅熔断：ATR 异常检测
    """

    def __init__(self, name: str = "Grid_V60_MTF", **params):
        super().__init__(name, **params)
        self.params_path = params.get('config_path', 'config/grid_v60_runtime.json')
        # 自动推导 meta 路径 (例如 runtime.json -> meta.json)
        self.meta_path = self.params_path.replace('runtime.json', 'meta.json')
        self.symbol = params.get('symbol', 'BTC-USDT-SWAP')
        self.param_metadata = {}
        self._load_params()

        # 数据缓存
        self._data_5m = deque(maxlen=200)   # 5m K线缓存
        self._data_15m = deque(maxlen=100)  # 15m 重采样缓存
        self._last_15m_ts: Optional[datetime] = None

        # 策略内部状态
        @dataclass
        class StrategyState:
            current_rsi: float = 50.0
            macd: float = 0.0
            macdsignal: float = 0.0
            macdhist: float = 0.0
            macdhist_prev: float = 0.0
            atr: float = 0.0
            atr_ma: float = 0.0
            
            grid_lower: float = 0.0
            grid_upper: float = 0.0
            grid_lines: List[float] = field(default_factory=list)
            
            is_halted: bool = False
            halt_reason: str = ""
            resume_time: Optional[datetime] = None
            
            last_grid_reset: Optional[datetime] = None

        self.state = StrategyState()

    def _load_params(self):
        """加载运行参数与元数据说明"""
        # 1. 加载运行参数
        if os.path.exists(self.params_path):
            try:
                with open(self.params_path, 'r', encoding='utf-8') as f:
                    self.params.update(json.load(f))
            except Exception as e:
                print(f"[V6.0] 加载参数失败: {e}")
        
        # 2. 加载元数据 (用于 Dashboard 说明面板)
        if os.path.exists(self.meta_path):
            try:
                with open(self.meta_path, 'r', encoding='utf-8') as f:
                    self.param_metadata = json.load(f)
            except Exception as e:
                print(f"[V6.0] 加载元数据失败: {e}")

    def initialize(self):
        super().initialize()
        print(f"[V6.0] {self.name} 初始化完成")

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
        """更新 5m 数据并执行 15m 重采样"""
        self._data_5m.append(data)
        
        # 15m 重采样逻辑 (以 0, 15, 30, 45 分钟为界)
        ts = data.timestamp
        period_ts = ts.replace(minute=(ts.minute // 15) * 15, second=0, microsecond=0)
        
        if self._last_15m_ts is None or period_ts > self._last_15m_ts:
            # 新的 15m 周期开始
            self._last_15m_ts = period_ts
            self._data_15m.append({
                'timestamp': period_ts,
                'open': data.open, 'high': data.high, 
                'low': data.low, 'close': data.close, 'volume': data.volume
            })
        else:
            # 更新当前的 15m 周期
            bar = self._data_15m[-1]
            bar['high'] = max(bar['high'], data.high)
            bar['low'] = min(bar['low'], data.low)
            bar['close'] = data.close
            bar['volume'] += data.volume

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
        self.state.macd = macd
        self.state.macdsignal = signal
        self.state.macdhist = hist

    def _manage_grid(self, data: MarketData):
        """动态网格维护"""
        now = data.timestamp
        lookback = self.params.get('grid_lookback_hours', 6)
        
        # 触发重置逻辑：无网格、超时重置、价格严重偏离
        need_reset = False
        if self.state.grid_upper == 0:
            need_reset = True
        elif self.state.last_grid_reset and (now - self.state.last_grid_reset) > timedelta(hours=lookback):
            need_reset = True
        elif abs(data.close - (self.state.grid_upper + self.state.grid_lower)/2) / ((self.state.grid_upper + self.state.grid_lower)/2) > self.params.get('grid_readjust', 0.05):
            need_reset = True

        if need_reset:
            # 采用过去 6 小时 5m K线计算
            bars = list(self._data_5m)[-int(lookback * 12):]
            if not bars: return
            
            high = max(b.high for b in bars)
            low = min(b.low for b in bars)
            buffer = self.params.get('grid_buffer', 0.02)
            
            self.state.grid_upper = high * (1 + buffer)
            self.state.grid_lower = low * (1 - buffer)
            
            # 生成网格线
            layers = self.params.get('grid_layers', 5)
            self.state.grid_lines = np.linspace(self.state.grid_lower, self.state.grid_upper, layers + 1).tolist()
            self.state.last_grid_reset = now
            print(f"[V6.0] 网格重置: {self.state.grid_lower:.2f} - {self.state.grid_upper:.2f} | 层数: {layers}")

    def _check_halt(self, data: MarketData) -> bool:
        """黑天鹅检测"""
        if self.state.is_halted:
            if self.state.resume_time and data.timestamp >= self.state.resume_time:
                self.state.is_halted = False
                print(f"[V6.0] 恢复交易")
            else:
                return True
        
        # ATR 异常检测
        if self.state.atr > self.state.atr_ma * self.params.get('atr_blackswan_mult', 3.0):
            self.state.is_halted = True
            self.state.halt_reason = "High Volatility (ATR Blackswan)"
            self.state.resume_time = data.timestamp + timedelta(minutes=self.params.get('atr_cooldown_min', 30))
            print(f"[V6.0] 触发熔断: {self.state.halt_reason}")
            return True
            
        return False

    def _generate_signals(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        signals = []
        pos = context.positions.get(self.symbol)
        pos_size = pos.size if pos else 0
        
        # 趋势强度 (15m MACD)
        is_bullish = self.state.macdhist > 0
        is_strong_bull = is_bullish and self.state.macd > 0 and self.state.macdhist > self.state.macdhist_prev if hasattr(self.state, 'macdhist_prev') else False
        self.state.macdhist_prev = self.state.macdhist

        # 1. 卖出逻辑 (趋势自适应)
        if pos_size > 0:
            sell_threshold = self.params.get('rsi_sell_threshold', 70)
            if is_strong_bull:
                sell_threshold = self.params.get('rsi_bull_adjust', 60) # 强趋势下更灵敏止盈(V6.0逻辑：强牛市提早分批)
                # 注：原 6.0 规格中极强牛市阈值为 60，震荡市为 70
            
            if self.state.current_rsi > sell_threshold:
                # 检查价格是否在网格上沿附近
                if data.close >= self.state.grid_lines[-2]:
                    # 分批卖出逻辑 (此处简化为全卖或按比例)
                    sell_ratio = 1.0 # 简化实现
                    signals.append(Signal(
                        timestamp=data.timestamp,
                        symbol=self.symbol,
                        side=Side.SELL,
                        size=pos_size * sell_ratio,
                        reason=f"MTF Sell: RSI={self.state.current_rsi:.1f} Bullish={is_bullish}"
                    ))

        # 2. 买入逻辑 (金字塔网格)
        if not signals: # 同一 bar 不做买卖
            # 趋势过滤：必须 15m MACD 多头
            if is_bullish and self.state.current_rsi < self.params.get('rsi_buy_threshold', 28):
                # 寻找当前价格所属网格层
                idx = -1
                for i in range(len(self.state.grid_lines) - 1):
                    if self.state.grid_lines[i] <= data.close < self.state.grid_lines[i+1]:
                        idx = i
                        break
                
                if idx != -1 and idx < 2: # 仅在底部的两层买入
                    # 金字塔仓位计算
                    layers = self.params.get('grid_layers', 5)
                    # 越低层(idx越小)买入越多：权重 = (layers - idx)
                    weight = (layers - idx) / sum(range(1, layers + 1))
                    buy_usdt = self.params.get('total_capital', 10000) * weight
                    
                    # 检查可用资金
                    if context.cash >= buy_usdt:
                        signals.append(Signal(
                            timestamp=data.timestamp,
                            symbol=self.symbol,
                            side=Side.BUY,
                            size=buy_usdt,
                            meta={'size_in_quote': True}, # 表示按 USDT 金额买
                            reason=f"MTF Grid Buy: Layer={idx} RSI={self.state.current_rsi:.1f}"
                        ))

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
            rsi_dist = max(0, self.params.get('rsi_buy_threshold', 28) - self.state.current_rsi)
            if self.state.current_rsi < self.params.get('rsi_buy_threshold', 28):
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
        if context and self.symbol in context.positions:
            pos = context.positions[self.symbol]
            if pos.size > 0:
                # 简单估算层数: 当前持仓对比网格单层期望
                pos_count = max(1, int(pos.size / (self.params.get('total_capital', 10000) / 70000 / 5))) 

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
            'grid_lower': round(self.state.grid_lower, 2),
            'grid_upper': round(self.state.grid_upper, 2),
            'grid_range': f"{self.state.grid_lower:.1f} - {self.state.grid_upper:.1f}",
            'grid_lines': self.state.grid_lines,
            'rsi_oversold': self.params.get('rsi_buy_threshold', 28),
            'rsi_overbought': self.params.get('rsi_sell_threshold', 70),
            'position_count': pos_count,
            'marketRegime': "上升通道" if is_bullish else "震荡下行" if self.state.macdhist < -5 else "调整阶段",
            'vol_trend': vol_trend,
            'current_volume': round(vol_current, 2),
            'is_halted': self.state.is_halted,
            'halt_reason': self.state.halt_reason,
            'pivots': {'pivots_high': [], 'pivots_low': []},
            'params': self.params,
            'param_metadata': self.param_metadata
        }
