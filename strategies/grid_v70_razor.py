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

class GridStrategyV70Razor(BaseStrategy):
    """
    GridStrategy V7.0-Razor (Kimibigclaw)
    
    核心特性：
    - 纯 RSI 左侧动态网格（MACD 完全剔除）
    - RSI 分层响应（极端/标准）
    - ATR 动态网格间距
    - 阶梯止盈 (Ladder Take-Profit)
    - 黑天鹅护盾 (Black Swan Guard)
    - 常态网格 (RSI 28-70 V7.1 恢复)
    """

    def __init__(self, name: str = "Grid_V70_Razor", **params):
        super().__init__(name, **params)
        self.params_path = params.get('config_path', 'config/grid_v70_razor_btc_runtime.json')
        self.meta_path = self.params_path.replace('runtime.json', 'meta.json')
        self.symbol = params.get('symbol', 'BTC-USDT')
        self.param_metadata = {}
        self._load_params()

        # 数据缓存
        self._data_1m = deque(maxlen=400)   # 1m K线用于极端风控 (ATR)
        self._data_5m = deque(maxlen=400)   # 5m K线用于核心 RSI 信号与网格

        # 策略内部状态
        @dataclass
        class StrategyState:
            current_rsi: float = 50.0
            atr: float = 0.0          # 1m ATR
            atr_ma: float = 0.0       # 1m ATR 过去 x 小时均值
            
            grid_lower: float = 0.0
            grid_upper: float = 0.0
            grid_lines: List[float] = field(default_factory=list)
            
            is_halted: bool = False
            halt_reason: str = ""
            resume_time: Optional[datetime] = None
            
            last_grid_reset: Optional[datetime] = None
            last_buy_time: Optional[datetime] = None
            last_buy_price: float = 0.0
            last_trade_price: float = 0.0 # 用于常态网格移动中枢
            
            # --- 内部仓位管理 (Paper交易核心) ---
            internal_pos_size: float = 0.0      # 内部追踪的持仓数量
            internal_avg_price: float = 0.0     # 内部追踪的平均成本
            internal_cash: float = 0.0          # 内部追踪的可用现金 (初始化后设置)

        self.state = StrategyState()

    def _load_params(self):
        """加载运行参数"""
        if os.path.exists(self.params_path):
            try:
                with open(self.params_path, 'r', encoding='utf-8') as f:
                    self.params.update(json.load(f))
            except Exception as e:
                print(f"[V7.0-Razor] 加载参数失败: {e}")
        
        if os.path.exists(self.meta_path):
            try:
                with open(self.meta_path, 'r', encoding='utf-8') as f:
                    self.param_metadata = json.load(f)
            except Exception as e:
                print(f"[V7.0-Razor] 加载元数据失败: {e}")

    def initialize(self):
        super().initialize()
        # 初始化内部现金 (从配置中获取)
        trading_cfg = self.params.get('trading', {})
        self.state.internal_cash = trading_cfg.get('initial_capital', 10000.0)
        print(f"[V7.0-Razor] {self.name} 初始化完成 | 初始资金: {self.state.internal_cash}")

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
            print(f"[成交反馈(7.0)] 买入成功 | 数量: {fill_size:.4f} @ {fill_price:.2f} | 资金剩余: {self.state.internal_cash:.2f}")
        else:
            new_size = max(0.0, old_size - fill_size)
            self.state.internal_pos_size = new_size
            self.state.internal_cash += (fill_size * fill_price)
            print(f"[成交反馈(7.0)] 卖出成功 | 数量: {fill_size:.4f} @ {fill_price:.2f}")
            
            # 卖出后，如果持仓清零，重置成本
            if new_size <= 0:
                self.state.internal_avg_price = 0.0

    def on_data(self, data: MarketData, context: Optional[StrategyContext]) -> List[Signal]:
        if not self._initialized:
            self.initialize()

        # 1. 更新数据 (1m 与 5m)
        self._update_data(data)
        
        # 指标计算需要足够数据
        if len(self._data_5m) < 30 or len(self._data_1m) < 30:
            return []

        # 2. 计算纯 RSI 和 ATR
        self._calculate_indicators()

        # 3. 黑天鹅风控检测
        if self._check_halt(data, context):
            # BUG#8 修复：此处应使用内部持仓，杜绝黑天鹅时刻依赖交易所同步
            pos_size = self.state.internal_pos_size
            if self.state.is_halted and pos_size > 0:
                return [Signal(
                    timestamp=data.timestamp,
                    symbol=self.symbol,
                    side=Side.SELL,
                    size=pos_size,
                    reason=f"Black Swan Guard: ATR Surge. Emergency Sell All."
                )]
            return []

        # 4. ATR 动态网格管理
        self._manage_grid(data)

        # 5. RSI 分层响应生成信号
        # 彻底移除对 context.positions 的依赖，改用内部状态
        return self._generate_signals(data)

    def _update_data(self, data: MarketData):
        """更新 1m 和 5m 数据"""
        ts = data.timestamp
        # --- 1m K线 ---
        bar_1m_ts = ts.replace(second=0, microsecond=0)
        if self._data_1m and self._data_1m[-1].timestamp.replace(second=0, microsecond=0) == bar_1m_ts:
            last = self._data_1m[-1]
            updated = MarketData(
                timestamp=ts, symbol=data.symbol,
                open=last.open, high=max(last.high, data.high),
                low=min(last.low, data.low), close=data.close, volume=data.volume
            )
            self._data_1m[-1] = updated
        else:
            self._data_1m.append(data)

        # --- 5m K线 ---
        bar_5m_ts = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        if self._data_5m and self._data_5m[-1].timestamp.replace(
                minute=(self._data_5m[-1].timestamp.minute // 5) * 5, second=0, microsecond=0) == bar_5m_ts:
            last = self._data_5m[-1]
            updated = MarketData(
                timestamp=ts, symbol=data.symbol,
                open=last.open, high=max(last.high, data.high),
                low=min(last.low, data.low), close=data.close, volume=data.volume
            )
            self._data_5m[-1] = updated
        else:
            self._data_5m.append(data)

    def _calculate_indicators(self):
        """仅计算核心 RSI 和 动态网格必需的 ATR"""
        # 5m RSI
        closes_5m = pd.Series([d.close for d in self._data_5m])
        self.state.current_rsi = self._rsi(closes_5m, self.params.get('signals', {}).get('rsi_period', 14))
        
        # 1m ATR (用于风控)
        highs_1m = pd.Series([d.high for d in self._data_1m])
        lows_1m = pd.Series([d.low for d in self._data_1m])
        closes_1m = pd.Series([d.close for d in self._data_1m])
        # 使用 14 周期 ATR
        atr_1m_val = self._atr(highs_1m, lows_1m, closes_1m, 14)
        self.state.atr = atr_1m_val
        
        # 统计过去 6 小时 (360 分钟=360根1m K线) ATR均值
        lookback = 360
        if len(self._data_1m) >= lookback:
            # BUG#6 修复：_atr 返回的是 .iloc[-1] (标量)，不能直接 .mean()
            # 这里先获取完整的 TR 序列再算 Rolling Mean 的平均
            tr = pd.concat([highs_1m - lows_1m, 
                            abs(highs_1m - closes_1m.shift()), 
                            abs(lows_1m - closes_1m.shift())], axis=1).max(axis=1)
            self.state.atr_ma = tr.rolling(window=14).mean().iloc[-lookback:].mean()
        else:
            self.state.atr_ma = atr_1m_val

    def _manage_grid(self, data: MarketData):
        """动态计算网格范围：基于 ATR 乘数"""
        grid_params = self.params.get('grid', {})
        min_spacing = grid_params.get('min_spacing', 0.003)
        atr_mult = grid_params.get('atr_multiplier', 0.15)
        layers = self.params.get('trading', {}).get('grid_layers', 5)

        # 动态间距计算 Spacing = max(min_spacing, (ATR / Price) * multiplier)
        if data.close > 0 and self.state.atr > 0:
            atr_pct = (self.state.atr / data.close) * atr_mult
            spacing_pct = max(min_spacing, atr_pct)
        else:
            spacing_pct = min_spacing

        # 以当前价格为中枢，上下展开网格边界 (简单逻辑)，或者使用近期高低点
        # 改进：V7.1 采用上一次交易价或当前价为基准下探。
        anchor = self.state.last_trade_price if self.state.last_trade_price > 0 else data.close
        
        # 网格覆盖范围
        total_range_pct = spacing_pct * layers
        self.state.grid_upper = anchor * (1 + total_range_pct * 0.5)
        self.state.grid_lower = anchor * (1 - total_range_pct * 0.5)
        
        self.state.grid_lines = np.linspace(self.state.grid_lower, self.state.grid_upper, layers + 1).tolist()

    def _check_halt(self, data: MarketData, context: Optional[StrategyContext]) -> bool:
        """黑天鹅风控：ATR异常激增判定"""
        if self.state.is_halted:
            if self.state.resume_time and data.timestamp >= self.state.resume_time:
                self.state.is_halted = False
                self.state.halt_reason = ""
                # BUG#9 修复：补全日志时间戳
                print(f"[{data.timestamp}] [V7.0-Razor] 恢复交易")
            else:
                return True
        
        risk_params = self.params.get('risk', {})
        black_swan_mult = risk_params.get('black_swan_atr_mult', 3.0)
        
        if self.state.atr_ma > 0 and self.state.atr > self.state.atr_ma * black_swan_mult:
            self.state.is_halted = True
            self.state.halt_reason = "Black Swan (ATR Surge)"
            # 默认冷却 15 分钟
            self.state.resume_time = data.timestamp + timedelta(minutes=15)
            # BUG#9 修复：补全日志时间戳
            print(f"[{data.timestamp}] [V7.0-Razor] 触发熔断: {self.state.halt_reason}")
            return True
            
        return False

    def _generate_signals(self, data: MarketData) -> List[Signal]:
        signals = []
        pos_size = self.state.internal_pos_size
        cash = self.state.internal_cash
        
        trading_params = self.params.get('trading', {})
        signal_params = self.params.get('signals', {})
        risk_params = self.params.get('risk', {})

        total_capital = trading_params.get('initial_capital', 10000)
        max_layers = trading_params.get('grid_layers', 5)
        layer_percent = trading_params.get('layer_size_percent', 20) / 100.0
        layer_value = total_capital * layer_percent

        current_layers = int(round(pos_size * data.close / layer_value)) if pos_size > 0 else 0

        # --- 阶梯止盈逻辑 (Ladder Take-Profit) ---
        sell_ratio = 0.0
        if pos_size > 0:
            rsi_sell_normal = signal_params.get('rsi_sell_normal', 70)
            rsi_sell_extreme = signal_params.get('rsi_sell_extreme', 80)
            tp_ladder = risk_params.get('ladder_take_profit', [0.3, 0.4, 0.3])
            
            sig_type = ""
            
            # 判断抛售层级 (极度贪婪 = 卖2层/大比例，贪婪 = 卖1层/标准比例)
            if self.state.current_rsi > rsi_sell_extreme:
                # 极端贪婪：双倍卖出 (2层或剩余总量的很大比例)
                sig_type = "EXTREME GREED (极度贪婪)"
                # 尝试根据阶梯表卖出多份，简单处理为卖出 2 份比例
                if len(tp_ladder) >= 2:
                    sell_ratio = tp_ladder[0] + tp_ladder[1]
                else:
                    sell_ratio = 0.6 # fallback
                # 不超过 1.0
                sell_ratio = min(1.0, sell_ratio) 
                # 防止极其细微残留
                if pos_size * (1 - sell_ratio) * data.close < 10: 
                    sell_ratio = 1.0

            elif self.state.current_rsi > rsi_sell_normal:
                sig_type = "GREED (贪婪)"
                sell_ratio = tp_ladder[0] if tp_ladder else 0.3
                # 防止细微残留
                if pos_size * (1 - sell_ratio) * data.close < 10: 
                    sell_ratio = 1.0
                    
            if sell_ratio > 0:
                sell_amount = pos_size * sell_ratio
                reason = f"Razor Sell [{sig_type}]: RSI={self.state.current_rsi:.1f} 阶梯止盈比例={sell_ratio*100:.0f}%"
                signals.append(Signal(
                    timestamp=data.timestamp,
                    symbol=self.symbol,
                    side=Side.SELL,
                    size=sell_amount,
                    reason=reason
                ))
                self.state.last_trade_price = data.close
                # 发出卖出信号后冷却一段时间（通过过滤同向信号实现），当前由引擎频率控制，此处不做强锁

        # --- 分层买入逻辑 ---
        rsi_buy_normal = signal_params.get('rsi_buy_normal', 28)
        rsi_buy_extreme = signal_params.get('rsi_buy_extreme', 20)
        
        can_buy = False
        buy_layers_req = 0
        sig_type = ""

        # 特殊风控：DOGE 冷却或持仓上限 (在扩展子类或配置中体现)
        max_pos_percent = risk_params.get('max_position_percent', 100) / 100.0
        current_pos_value = pos_size * data.close
        if current_pos_value >= total_capital * max_pos_percent:
            # 达到持仓上限
            pass
        elif current_layers < max_layers:
            if self.state.current_rsi < rsi_buy_extreme:
                buy_layers_req = 2  # 极端恐惧，双倍买入
                sig_type = "EXTREME FEAR (极度恐惧 两倍)"
            elif self.state.current_rsi < rsi_buy_normal:
                buy_layers_req = 1  # 恐惧，标准买入
                sig_type = "FEAR (恐惧 一倍)"
            
            # 限制不能超过最大层数限制和剩余可用资金
            buy_layers_req = min(buy_layers_req, max_layers - current_layers)
            
            if buy_layers_req > 0:
                # 价格网格检查：即使 RSI 满足，若距离上次买入价格太近则不买 (强制网格间距)
                grid_params = self.params.get('grid', {})
                min_spacing = grid_params.get('min_spacing', 0.003)
                if self.state.last_buy_price > 0:
                    price_drop = (self.state.last_buy_price - data.close) / self.state.last_buy_price
                    if price_drop > min_spacing:
                        can_buy = True
                    # 或者如果是空仓，直接可以买
                    elif current_layers == 0:
                        can_buy = True
                else:
                    can_buy = True

        if can_buy:
            buy_usdt = layer_value * buy_layers_req
            if cash >= buy_usdt * 0.95:  
                reason = f"Razor Buy [{sig_type}]: RSI={self.state.current_rsi:.1f} 投入层数={buy_layers_req}"
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
                self.state.last_trade_price = data.close

        # --- 常态网格逻辑 (V7.1 RSI 28-70 之间运行) ---
        if not can_buy and sell_ratio == 0.0:
            # 意味着没有触发极端 RSI 的买入和卖出
            grid_params = self.params.get('grid', {})
            min_spacing = grid_params.get('min_spacing', 0.003)
            
            # 低吸 (跌破下轨 且 有资金有层数)
            if data.close < self.state.grid_lower:
                if current_layers < max_layers:
                    buy_usdt = layer_value
                    if cash >= buy_usdt * 0.95:
                        grid_buy_reason = f"Normal Grid Buy: 价格跌破下轨 ({data.close:.2f} < {self.state.grid_lower:.2f})"
                        signals.append(Signal(
                            timestamp=data.timestamp,
                            symbol=self.symbol,
                            side=Side.BUY,
                            size=buy_usdt,
                            meta={'size_in_quote': True},
                            reason=grid_buy_reason
                        ))
                        self.state.last_buy_time = data.timestamp
                        self.state.last_buy_price = data.close
                        self.state.last_trade_price = data.close
            
            # 高抛 (突破上轨 且 有持仓)
            elif data.close > self.state.grid_upper:
                if pos_size > 0:
                    sell_amount = pos_size / max(1, current_layers) # 卖出1层
                    # 当前价格距离上次交易太近则不卖，或者这里强制卖
                    grid_sell_reason = f"Normal Grid TP: 价格突破上轨 ({data.close:.2f} > {self.state.grid_upper:.2f})"
                    signals.append(Signal(
                        timestamp=data.timestamp,
                        symbol=self.symbol,
                        side=Side.SELL,
                        size=sell_amount,
                        reason=grid_sell_reason
                    ))
                    self.state.last_trade_price = data.close
            
            # 网格重置机制（偏离过大）
            # 例如如果价格脱离锚点超过一定距离并且没有成交发生，主动跟随
            if abs(data.close - self.state.last_trade_price) / (self.state.last_trade_price or data.close) > min_spacing * 3:
                self.state.last_trade_price = data.close
                self.state.last_grid_reset = data.timestamp

        return signals

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
        signal_text = "中性观望"
        signal_color = "neutral"
        
        rsi = self.state.current_rsi
        sp = self.params.get('signals', {})
        if self.state.is_halted:
            signal_text = f"熔断: {self.state.halt_reason}"
            signal_color = "sell"
        elif rsi < sp.get('rsi_buy_extreme', 20):
            signal_text = "极度恐惧"
            signal_color = "buy"
        elif rsi < sp.get('rsi_buy_normal', 28):
            signal_text = "恐惧"
            signal_color = "buy"
        elif rsi > sp.get('rsi_sell_extreme', 80):
            signal_text = "极度贪婪"
            signal_color = "sell"
        elif rsi > sp.get('rsi_sell_normal', 70):
            signal_text = "贪婪"
            signal_color = "sell"

        pos_count = 0
        pos_size = self.state.internal_pos_size
        pos_avg_price = self.state.internal_avg_price
        
        if pos_size > 0:
            trading_params = self.params.get('trading', {})
            total_cap = trading_params.get('initial_capital', 10000)
            layers = trading_params.get('grid_layers', 5)
            if pos_avg_price > 0:
                pos_count = max(1, int(round(pos_size * pos_avg_price / (total_cap / layers))))

        return {
            'name': self.name,
            'current_rsi': float(np.round(self.state.current_rsi, 2)),
            'atr': float(np.round(self.state.atr, 2)),
            'atr_ma': float(np.round(self.state.atr_ma, 2)),
            'atrVal': float(np.round(self.state.atr, 2)),
            'marketRegime': '震荡/未知',
            'vol_trend': '平稳',
            'current_volume': float(self._data_1m[-1].volume) if self._data_1m else 0.0,
            'signal_text': signal_text,
            'signal_color': signal_color,
            'position_size': pos_size,
            'position_avg_price': pos_avg_price,
            'position_unrealized_pnl': 0.0,
            'cash': self.state.internal_cash,
            'grid_lower': float(np.round(self.state.grid_lower, 2)),
            'grid_upper': float(np.round(self.state.grid_upper, 2)),
            'grid_range': f"{self.state.grid_lower:.1f} - {self.state.grid_upper:.1f}",
            'grid_lines': self.state.grid_lines,
            'rsi_oversold': sp.get('rsi_buy_normal', 28),
            'rsi_overbought': sp.get('rsi_sell_normal', 70),
            'position_count': pos_count,
            'is_halted': self.state.is_halted,
            'halt_reason': self.state.halt_reason,
            'params': self.params,
            'param_metadata': self.param_metadata
        }
