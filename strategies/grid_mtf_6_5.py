import os
import json
import numpy as np
import pandas as pd
<<<<<<< Updated upstream
=======
from pathlib import Path
>>>>>>> Stashed changes
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from collections import deque

from core import (
    MarketData, Signal, Side, OrderType, 
    FillEvent, Position, StrategyContext
)
from strategies.base import BaseStrategy
<<<<<<< Updated upstream

class GridStrategyV65A(BaseStrategy):
    """
    V6.5c 动态网格交易策略
    
    核心改进：去除 MACD 对交易信号的影响，采用 "RSI + 成交量 + K线形态" 三维验证模型。
    MACD 仍计算并展示在 Dashboard 上，但不参与买卖决策。
    新增：回撤熔断 (max_drawdown) 和连续亏损熔断 (max_consecutive_losses)。
    """

    def __init__(self, name: str = "Grid_V65_MTF", **params):
        super().__init__(name, **params)
        self.params_path = params.get('config_path', 'config/grid_v65_runtime.json')
        # 自动推导 meta 路径 (例如 runtime.json -> meta.json)
        self.meta_path = self.params_path.replace('runtime.json', 'meta.json')
        self.symbol = params.get('symbol', 'BTC-USDT-SWAP')
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
            # MACD 仅用于 Dashboard 展示，不参与交易决策
            macd: float = 0.0
            macdsignal: float = 0.0
            macdhist: float = 0.0
            macd_prev: float = 0.0
            macdsignal_prev: float = 0.0
            macdhist_prev: float = 0.0
            atr: float = 0.0
            atr_ma: float = 0.0
            
            # V6.5c 新增：成交量与K线形态
            volume_ma: float = 0.0
            is_bullish_candle: bool = False
            
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
            
            # V6.5c 新增：风控状态
            peak_equity: float = 0.0
            current_drawdown: float = 0.0
            consecutive_losses: int = 0
            drawdown_halted: bool = False
            loss_halted: bool = False

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

        # 3. 多层风控检测
        if self._check_halt(data, context):
            return []

        # 4. 网格管理 (边界计算与重置)
        self._manage_grid(data)

        # 5. 信号生成
=======
from strategies.grid_mtf_6_0 import IncrementalIndicatorsV6, StrategyState

# ============================================================
# V6.5 大鸡腿版：趋势捕获版 (The Profit Hunter)
# ============================================================

class GridMTFStrategyV6_5(BaseStrategy):
    """
    V6.5-Winner "大鸡腿"版
    针对 2025 年行情（9.3万 -> 12.6万 -> 8.7万）的专项进化：
    1. 牛市锁定 (Trend-Lock): MACD 强势期禁止 RSI 反向止盈，确保吃到 12.6 万的主升浪。
    2. 均线拦截 (MA Barrier): 价格跌破 15m MA200 后停止左侧接单，避免 Q4 的“阴跌接飞刀”。
    3. 动量分配: 根据 MACD 强度动态分配仓位。
    """
    def __init__(self, name: str = "Grid_V65_Winner", **params):
        super().__init__(name, **params)
        
        current_file_dir = Path(__file__).parent.resolve()
        config_dir = current_file_dir.parent / "config"
        
        self.default_params_path = str(config_dir / 'grid_v60_default.json')
        self.params_path = str(config_dir / 'grid_v65_runtime.json')
        
        self.symbol = params.get('symbol', 'BTCUSDT')
        self._load_params()

        # 数据缓存
        self._data_5m = deque(maxlen=600) 
        self._data_15m_closes = deque(maxlen=250)
        self._last_5m_ts = None
        self._last_bar_5m = None
        
        self.state = StrategyState()
        self.indicators = IncrementalIndicatorsV6(self.params)
        
        self._last_15m_ts: Optional[datetime] = None
        self._last_15m_bar_close = 0.0
        self.ma200_15m = 0.0

    def _load_params(self):
        if os.path.exists(self.default_params_path):
            with open(self.default_params_path, 'r', encoding='utf-8') as f:
                self.params.update(json.load(f))
        if os.path.exists(self.params_path):
            with open(self.params_path, 'r', encoding='utf-8') as f:
                self.params.update(json.load(f))

    def on_data(self, data: MarketData, context: Optional[StrategyContext]) -> List[Signal]:
        is_new_bar = (not self._last_5m_ts) or (data.timestamp > self._last_5m_ts)
        if is_new_bar:
            if self._last_bar_5m:
                self.indicators.update_5m(self._last_bar_5m, commit=True)
            self._last_5m_ts = data.timestamp
            
            # 聚合 15m
            ts = data.timestamp
            period_ts = ts.replace(minute=(ts.minute // 15) * 15, second=0, microsecond=0)
            if self._last_15m_ts is None or period_ts > self._last_15m_ts:
                if self._last_15m_ts is not None:
                    self.indicators.update_15m_macd(self._last_15m_bar_close, commit=True)
                    self._data_15m_closes.append(self._last_15m_bar_close)
                self._last_15m_ts = period_ts
                self._last_15m_bar_close = data.close
            else:
                self._last_15m_bar_close = data.close
                
        self._last_bar_5m = data
        self._data_5m.append(data)

        if len(self._data_15m_closes) < 20: return []

        rsi, atr, atr_ma = self.indicators.update_5m(data, commit=False)
        macd, sig, hist = self.indicators.update_15m_macd(data.close, commit=False)
        
        # 计算 15m MA200
        if len(self._data_15m_closes) >= 200:
            self.ma200_15m = np.mean(list(self._data_15m_closes)[-200:])
        else:
            self.ma200_15m = np.mean(list(self._data_15m_closes))

        self.state.current_rsi = rsi
        self.state.atr = atr
        self.state.atr_ma = atr_ma
        self.state.macd = macd
        self.state.macdsignal = sig
        self.state.macdhist = hist
        
        if self._check_halt(data): return []
        self._manage_grid(data)

>>>>>>> Stashed changes
        if context:
            return self._generate_signals(data, context)
        return []

<<<<<<< Updated upstream
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
            # 找到在当前 15m 周期内（属于这段 period_ts），但【已经完结】（不仅指最新一根正在跑的）的所有 5m K线。
            # 直接遍历 self._data_5m 从后往前找，把 timestamp 大于等于 period_ts 且与 period_ts 属于同一 15m 窗口的所有完整 5m 累加。
            vol_sum = 0
            for i in range(len(self._data_5m) - 1, -1, -1):
                d = self._data_5m[i]
                d_period_ts = d.timestamp.replace(minute=(d.timestamp.minute // 15) * 15, second=0, microsecond=0)
                if d_period_ts < period_ts:
                    break  # 已经跨越到上一个 15m 周期，停止
                if d_period_ts == period_ts:
                    # 只要是属于这个 15m 周期内的 5m K线，直接把它们内部已经整理好的 `volume` 加起来。
                    # 注意如果 `_data_5m` 已经是去重过的，那么最后一根就是包含当前 data.volume 的
                    vol_sum += d.volume
            
            bar['volume'] = vol_sum



    def _calculate_indicators(self):
        """计算 RSI(5m), MACD(15m 仅展示), ATR(5m), 成交量MA(5m), K线形态"""
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

        # V6.5c：成交量 MA (20根5m K线)
        volumes = pd.Series([d.volume for d in self._data_5m])
        vol_ma_period = self.params.get('volume_ma_period', 20)
        vol_ma = volumes.rolling(window=vol_ma_period).mean().iloc[-1]
        self.state.volume_ma = vol_ma if not np.isnan(vol_ma) else 0.0

        # V6.5c：K线形态（当前最新K线是否阳线）
        latest = self._data_5m[-1]
        self.state.is_bullish_candle = latest.close > latest.open

        # 15m MACD (仅用于 Dashboard 展示，不参与交易决策)
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
        layers = self.params.get('grid_layers', 5)
        self.state.grid_lines = np.linspace(self.state.grid_lower, self.state.grid_upper, layers + 1).tolist()
        self.state.last_grid_reset = now

    def _check_halt(self, data: MarketData, context: Optional[StrategyContext] = None) -> bool:
        """多层风控检测：黑天鹅 + 回撤熔断 + 连续亏损"""
        if self.state.is_halted:
            if self.state.resume_time and data.timestamp >= self.state.resume_time:
                self.state.is_halted = False
                print(f"[V6.5c] 恢复交易")
            else:
                return True
        
        # Layer 3: ATR 黑天鹅检测
        if self.state.atr > self.state.atr_ma * self.params.get('atr_blackswan_mult', 3.0):
            self.state.is_halted = True
            self.state.halt_reason = "波动风控 (ATR异常)"
            self.state.resume_time = data.timestamp + timedelta(minutes=self.params.get('atr_cooldown_min', 30))
            print(f"[V6.5c] 触发熔断: {self.state.halt_reason}")
            return True

        # Layer 2: 回撤风控
        if context:
            pos = context.positions.get(self.symbol)
            pos_val = float(pos.size) * data.close if pos else 0.0
            equity = context.cash + pos_val
            if equity > self.state.peak_equity:
                self.state.peak_equity = equity
            if self.state.peak_equity > 0:
                self.state.current_drawdown = (self.state.peak_equity - equity) / self.state.peak_equity
            
            max_dd = self.params.get('max_drawdown', 0.10)
            if self.state.current_drawdown > max_dd:
                if not self.state.drawdown_halted:
                    self.state.drawdown_halted = True
                    self.state.halt_reason = f"回撤风控 ({self.state.current_drawdown:.1%} > {max_dd:.0%})"
                    print(f"[V6.5c] 触发熔断: {self.state.halt_reason}")
                return True
            else:
                self.state.drawdown_halted = False

        # Layer 4: 连续亏损风控
        max_losses = self.params.get('max_consecutive_losses', 5)
        if self.state.consecutive_losses >= max_losses:
            if not self.state.loss_halted:
                self.state.loss_halted = True
                self.state.halt_reason = f"连续亏损风控 ({self.state.consecutive_losses}次)"
                print(f"[V6.5c] 触发熔断: {self.state.halt_reason} — 需人工确认恢复")
            return True
            
        return False

    def _generate_signals(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        """V6.5c 信号生成：RSI + 成交量 + K线形态 三维验证"""
        signals = []
        pos = context.positions.get(self.symbol)
        pos_size = float(pos.size) if pos else 0.0

        # 层数计算
        layer_value = self.params.get('total_capital', 10000) / self.params.get('grid_layers', 5)
        current_layers = int(round(pos_size * data.close / layer_value)) if pos_size > 0 else 0

        # --- 全局冷却锁 ---
        cooldown_lock = False
        cooldown_min = self.params.get('buy_cooldown_min', 15)
        if getattr(self.state, 'last_buy_time', None) is not None:
            if data.timestamp < self.state.last_buy_time + timedelta(minutes=cooldown_min):
                cooldown_lock = True

        # --- 三维条件分量 ---
        vol_threshold = self.params.get('volume_threshold', 1.3)
        current_vol = data.volume
        vol_confirmed = self.state.volume_ma > 0 and current_vol > self.state.volume_ma * vol_threshold

        # 1. 卖出逻辑：RSI超买 + 放量 + 阴线
        if pos_size > 0 and not cooldown_lock:
            rsi_sell = self.params.get('rsi_sell_threshold', 70)
            is_bearish_candle = not self.state.is_bullish_candle  # close < open

            if self.state.current_rsi > rsi_sell and vol_confirmed and is_bearish_candle:
                sell_layers = min(1, current_layers) if current_layers > 0 else 1
                sell_ratio = sell_layers / current_layers if current_layers > 0 else 1.0
                reason = (f"V6.5c Sell: RSI={self.state.current_rsi:.1f}>{rsi_sell} "
                          f"放量={current_vol:.0f}/{self.state.volume_ma:.0f}({vol_threshold}x) "
                          f"阴线 抛售{sell_layers}层 剩余~{max(0, current_layers-sell_layers)}层")
                signals.append(Signal(
                    timestamp=data.timestamp,
                    symbol=self.symbol,
                    side=Side.SELL,
                    size=pos_size * sell_ratio,
                    reason=reason
                ))
                # 卖出后判断盈亏，更新连续亏损计数
                if self.state.last_buy_price > 0:
                    if data.close < self.state.last_buy_price:
                        self.state.consecutive_losses += 1
                    else:
                        self.state.consecutive_losses = 0

        # 2. 买入逻辑：RSI超卖 + 放量 + 阳线
        rsi_buy = self.params.get('rsi_buy_threshold', 30)
        max_layers = self.params.get('grid_layers', 5)

        can_buy = (
            self.state.current_rsi < rsi_buy
            and vol_confirmed
            and self.state.is_bullish_candle
            and current_layers < max_layers
            and not cooldown_lock
            and not self.state.drawdown_halted
            and not self.state.loss_halted
        )

        if can_buy:
            buy_usdt = layer_value  # 每次固定 1 层
            if context.cash >= buy_usdt * 0.95:
                reason = (f"V6.5c Buy: RSI={self.state.current_rsi:.1f}<{rsi_buy} "
                          f"放量={current_vol:.0f}/{self.state.volume_ma:.0f}({vol_threshold}x) "
                          f"阳线 买入1层 当前={current_layers}层")
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
        if len(self._data_5m) < 20: return
        
        n = 3  # 3高3低
        # 局部确认判定窗口 (增大到 10 根 = 50 分钟，过滤短期噪点)
        window_size = 10
        
        data_list = list(self._data_5m)
        highs = df['high'].values
        lows = df['low'].values
        curr_idx = len(df) - 1
        
        if curr_idx < window_size + 1:
            return

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
                    ts = data_list[i].timestamp.isoformat()
                    all_lows.append({'price': float(lows[i]), 'time': ts, 'index': i})

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
                    ts = data_list[i].timestamp.isoformat()
                    all_highs.append({'price': float(highs[i]), 'time': ts, 'index': i})

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
        # MACD 趋势 (仅展示用)
        is_bullish = self.state.macdhist > 0
        macd_trend = "强牛" if is_bullish and self.state.macdhist > self.state.macdhist_prev else "牛市" if is_bullish else "震荡"
        if self.state.macdhist < 0:
            macd_trend = "强熊" if self.state.macdhist < self.state.macdhist_prev else "熊市"
        
        # V6.5c：三维信号状态判定
        vol_threshold = self.params.get('volume_threshold', 1.3)
        vol_ok = self.state.volume_ma > 0 and self._data_5m and self._data_5m[-1].volume > self.state.volume_ma * vol_threshold
        rsi_buy = self.params.get('rsi_buy_threshold', 30)

        signal_text = "等待信号"
        signal_color = "neutral"
        signal_strength = "--"

        if self.state.is_halted or self.state.drawdown_halted or self.state.loss_halted:
            reason = self.state.halt_reason
            if self.state.drawdown_halted:
                reason = f"回撤熔断 ({self.state.current_drawdown:.1%})"
            elif self.state.loss_halted:
                reason = f"连亏熔断 ({self.state.consecutive_losses}次)"
            signal_text = f"熔断: {reason}"
            signal_color = "sell"
        elif self.state.current_rsi < rsi_buy:
            # RSI 超卖区
            conditions_met = sum([True, vol_ok, self.state.is_bullish_candle])  # RSI 已满足
            signal_color = "buy"
            if conditions_met == 3:
                signal_text = "三维验证通过 → 买入"
                signal_strength = "强"
            elif conditions_met == 2:
                signal_text = f"RSI超卖 等待{'放量' if not vol_ok else '阳线'}"
                signal_strength = "中"
            else:
                signal_text = "RSI超卖 等待确认"
                signal_strength = "低"
        elif self.state.current_rsi > self.params.get('rsi_sell_threshold', 70):
            signal_color = "sell"
            signal_text = "RSI超买 关注卖出"
            signal_strength = "中"
        else:
            signal_text = "区间运行"
            signal_strength = "--"

        # 量能分析
        vol_current = 0
        vol_trend = "持平"
        if self._data_5m:
            vol_current = self._data_5m[-1].volume
            if self.state.volume_ma > 0:
                ratio = vol_current / self.state.volume_ma
                if ratio > 1.5: vol_trend = "放量"
                elif ratio > vol_threshold: vol_trend = "温和放量"
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
                layer_value = self.params.get('total_capital', 10000) / self.params.get('grid_layers', 5)
                pos_count = max(1, int(round(pos_size * (pos_avg_price if pos_avg_price > 0 else 1) / layer_value)))

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
            'rsi_oversold': self.params.get('rsi_buy_threshold', 30),
            'rsi_overbought': self.params.get('rsi_sell_threshold', 70),
            'position_count': pos_count,
            'marketRegime': "上升通道" if is_bullish else "震荡下行" if self.state.macdhist < -5 else "调整阶段",
            'vol_trend': vol_trend,
            'current_volume': round(vol_current, 2),
            'is_halted': self.state.is_halted or self.state.drawdown_halted or self.state.loss_halted,
            'halt_reason': self.state.halt_reason,
            'current_drawdown': round(self.state.current_drawdown, 4),
            'consecutive_losses': self.state.consecutive_losses,
            'pivots': {
                'pivots_high': getattr(self.state, 'pivots_high', []),
                'pivots_low': getattr(self.state, 'pivots_low', [])
            },
            'params': self.params,
            'param_metadata': self.param_metadata
        }
=======
    def _manage_grid(self, data: MarketData):
        now = data.timestamp
        lookback = self.params.get('grid_lookback_hours', 24) # 大版加大回看范围
        
        need_reset = False
        if self.state.grid_upper == 0:
            need_reset = True
        elif self.state.last_grid_reset and (now - self.state.last_grid_reset) > timedelta(hours=lookback):
            need_reset = True
        elif abs(data.close - (self.state.grid_upper + self.state.grid_lower)/2) / ((self.state.grid_upper + self.state.grid_lower)/2) > 0.08:
            need_reset = True

        if need_reset:
            bars = list(self._data_5m)
            if not bars: return
            high = max(b.high for b in bars)
            low = min(b.low for b in bars)
            buffer = 0.03 # 加大网格缓冲
            self.state.grid_upper = high * (1 + buffer)
            self.state.grid_lower = low * (1 - buffer)
            layers = 6
            self.state.grid_lines = np.linspace(self.state.grid_lower, self.state.grid_upper, layers + 1).tolist()
            self.state.last_grid_reset = now

    def _check_halt(self, data: MarketData) -> bool:
        if self.state.is_halted:
            if self.state.resume_time and data.timestamp >= self.state.resume_time:
                self.state.is_halted = False
            else: return True
        if self.state.atr > self.state.atr_ma * 3.5:
            self.state.is_halted = True
            self.state.resume_time = data.timestamp + timedelta(minutes=60)
            return True
        return False

    def _generate_signals(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        signals = []
        pos = context.positions.get(self.symbol)
        pos_size = pos.size if pos else 0
        
        is_bullish = self.state.macdhist > 0
        trend_strong = is_bullish and self.state.macdhist > self.state.macdsignal * 0.5
        
        self.state.macdhist_prev = getattr(self.state, 'macdhist_prev', self.state.macdhist)
        hist_growth = self.state.macdhist - self.state.macdhist_prev
        self.state.macdhist_prev = self.state.macdhist

        # 1. 卖出逻辑 (趋势锁定)
        if pos_size > 0:
            # 只有当 MACD 柱状图开始下降，或价格严重偏离 MA200 时，才允许止盈
            if self.state.current_rsi > 80:
                # 即使 RSI 很高，如果趋势还在加速 (hist_growth > 0)，我们就拿住
                if hist_growth < 0 or not is_bullish:
                   signals.append(Signal(data.timestamp, self.symbol, Side.SELL, pos_size, reason="Winner TP (Exhaustion)"))

        # 2. 买入逻辑 (均线拦截)
        if not signals:
            # 防守逻辑：处于空头趋势下 (Price < MA200) 严禁网格左侧买入
            if data.close < self.ma200_15m:
                return []
            
            # 进攻逻辑：处于多头趋势且 RSI < 35 进入网格区
            if is_bullish and self.state.current_rsi < 35:
                idx = -1
                for i in range(len(self.state.grid_lines) - 1):
                    if self.state.grid_lines[i] <= data.close < self.state.grid_lines[i+1]:
                        idx = i; break
                
                if idx != -1 and idx < 3:
                     # 波动率自适应因子
                    vol_factor = np.clip(self.state.atr_ma / (self.state.atr + 1e-9), 0.7, 1.5)
                    # 强趋势加成
                    trend_mult = 1.3 if trend_strong else 1.0
                    
                    layers = 6
                    weight = (layers - idx) / sum(range(1, layers + 1))
                    buy_usdt = self.params.get('total_capital', 10000) * weight * vol_factor * trend_mult
                    
                    if context.cash >= buy_usdt:
                        signals.append(Signal(
                            timestamp=data.timestamp,
                            symbol=self.symbol,
                            side=Side.BUY,
                            size=buy_usdt,
                            meta={'size_in_quote': True},
                            reason=f"Winner Buy: Trend={trend_strong}"
                        ))

        return signals

    def get_status(self, context=None):
        from strategies.grid_mtf_6_0 import GridMTFStrategyV6_0
        res = GridMTFStrategyV6_0.get_status(self, context)
        res['ma200_15m'] = round(self.ma200_15m, 2)
        res['price_above_ma'] = (context.current_price > self.ma200_15m) if (context and self.ma200_15m > 0) else False
        return res
>>>>>>> Stashed changes
