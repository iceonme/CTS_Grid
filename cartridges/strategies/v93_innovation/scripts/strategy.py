import pandas as pd
from datetime import datetime
from typing import List, Optional, Dict, Any
import asyncio
from dataclasses import asdict

from console.core import Signal, Side, OrderType, MarketData, Position, StrategyContext
from cartridges.strategies.base import BaseStrategy
from cartridges.strategies.v93_innovation.scripts.indicators import GridState, calculate_rsi, calculate_atr, lstm_trend, calculate_grids, get_current_layer, check_reset_conditions


class V93InnovationStrategy(BaseStrategy):
    """
    V9.3 Innovation 永续合约动量网格策略
    实现 3实体+2虚拟网格架构，支持无状态运行与状态持久化。
    """
    
    def __init__(self, name: str = "V9.3-Innovation", **params):
        super().__init__(name, **params)
        self.symbol = self.params.get('symbol', 'ETH-USDT-SWAP')
        self.warmup_bars = self.params.get('warmup_bars', 360)
        
        # 内部缓存
        self.price_history: List[float] = []
        self.df_history = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
        self.last_candle_ts: Optional[datetime] = None
        
        # 动态 RSI 阈值
        self.rsi_oversold = self.params.get('params', {}).get('rsi_oversold', 25.0)
        self.rsi_overbought = self.params.get('params', {}).get('rsi_overbought', 85.0)
        self.rsi_exit_oversold = self.params.get('params', {}).get('rsi_exit_oversold', 40.0)
        self.rsi_exit_overbought = self.params.get('params', {}).get('rsi_exit_overbought', 70.0)
        
        # 运行时状态 (持久化对象)
        self.state = GridState()
        self.current_leverage = self.params.get('leverage_base', 3.0)
        
        # 指标结果缓存 (供 Dashboard 使用)
        self.last_indicators = {
            'rsi': 50.0,
            'trend': 0,
            'layer': None,
            'atr_pct': 0.0
        }

    def _update_buffer(self, data: MarketData):
        """更新内部 OHLCV 缓存"""
        if self.last_candle_ts == data.timestamp:
            if self.price_history: self.price_history[-1] = data.close
            if not self.df_history.empty:
                # 按列名精准更新，防止 iloc 顺序错位
                self.df_history.loc[data.timestamp, ['open', 'high', 'low', 'close', 'volume']] = \
                    [data.open, data.high, data.low, data.close, data.volume]
        else:
            self.price_history.append(data.close)
            self.last_candle_ts = data.timestamp
            new_row = pd.DataFrame([{
                'open': data.open, 'high': data.high, 'low': data.low, 
                'close': data.close, 'volume': data.volume
            }], index=[data.timestamp])
            self.df_history = pd.concat([self.df_history, new_row]).tail(1000)
            
        if len(self.price_history) > 1000:
            self.price_history = self.price_history[-1000:]

    async def initialize(self):
        """策略启动预热：向数据源索要 360 根历史 K 线 (自动支持跨页抓取)"""
        asyncio.create_task(self.request_history(self.symbol, limit=360))

    def _fill_history(self, candles: List[MarketData]):
        """批量填充历史缓存 (从 DataFeed 补全)"""
        if not candles: return
        
        data = []
        for c in candles:
            data.append({
                'open': c.open, 'high': c.high, 'low': c.low, 
                'close': c.close, 'volume': c.volume
            })
            self.price_history.append(c.close)
            
        df_new = pd.DataFrame(data, index=[int(c.timestamp.timestamp()) if hasattr(c.timestamp, 'timestamp') else int(c.timestamp) for c in candles])
        
        # 合并、去重、排序、裁剪
        self.df_history = pd.concat([self.df_history, df_new]).sort_index()
        self.df_history = self.df_history[~self.df_history.index.duplicated(keep='last')]
        self.df_history = self.df_history.tail(1000)
        
        # 确保 price_history 与 df_history 同步 (取最新 1000 根)
        self.price_history = self.df_history['close'].tolist()
        if self.df_history is not None and not self.df_history.empty:
            # 统一使用 Unix 时间戳
            self.last_candle_ts = int(self.df_history.index[-1])
            
        # 立即计算一次指标，确保 Dashboard 取到的是热数据
        self._update_indicators()

    async def _on_market_history_update(self, event_data: Any):
        """异步历史数据到货回调：接收 360 根数据并即时推送 UI"""
        # 鲁棒性检查：兼容对象和字典格式
        symbol = event_data.symbol if hasattr(event_data, 'symbol') else event_data.get("symbol")
        candles = event_data.data if hasattr(event_data, 'data') else event_data.get("data", [])
        
        print(f"!!! [V93:DEBUG] 触发历史回调 | 收到对标: {symbol} (预期: {self.symbol}) | 条数: {len(candles)}")
        
        # 既然是策略私有的订阅，原则上直接处理
        self._fill_history(candles)
        
        # [关键修复] 数据填装完毕，立刻向总线广播，点亮 UI
        history = self.get_history()
        if history and self.bus:
            print(f"!!! [V93:DEBUG] 发送历史广播 -> ui_history_update | 数据项: {list(history.keys())}")
            await self.bus.emit("ui_history_update", {
                "strategy_id": self.name,
                "data": history
            })
        # self.log(f"预热完成：回补 {len(candles)} 根数据，当前缓存 {len(self.df_history)} 根")

    def _update_indicators(self):
        """批量更新指标缓存 (供预热触发)"""
        if self.df_history.empty: return
        
        from cartridges.strategies.v93_innovation.scripts.indicators import calculate_rsi, calculate_atr, lstm_trend, get_current_layer
        
        current_price = self.df_history.iloc[-1]['close']
        rsi = calculate_rsi(self.price_history, self.params.get('rsi_period', 14))
        atr = calculate_atr(self.df_history)
        trend = lstm_trend(self.price_history)
        atr_pct = (atr / current_price * 100) if current_price > 0 else 0
        layer = get_current_layer(current_price, self.state.entity_grids, self.state.virtual_grids)
        
        self.last_indicators.update({
            'rsi': rsi, 'trend': trend, 'layer': layer, 'atr_pct': atr_pct
        })

    def _update_dynamic_thresholds(self, trend: int):
        """动态 RSI 阈值：强趋势模式下放宽入场，收紧止盈"""
        if abs(trend) >= 1: # 强趋势
            self.rsi_oversold, self.rsi_overbought = 30.0, 80.0
            self.rsi_exit_oversold, self.rsi_exit_overbought = 45.0, 65.0
        else: # 震荡
            self.rsi_oversold, self.rsi_overbought = 25.0, 85.0
            self.rsi_exit_oversold, self.rsi_exit_overbought = 40.0, 70.0

    def on_data(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        self._update_buffer(data)
        if len(self.df_history) < 20: return []
        
        signals = []
        current_price = data.close
        current_time = data.timestamp
        
        # 1. 计算核心指标
        rsi = calculate_rsi(self.price_history, self.params.get('rsi_period', 14))
        atr = calculate_atr(self.df_history)
        trend = lstm_trend(self.price_history)
        atr_pct = (atr / current_price * 100) if current_price > 0 else 0
        
        self._update_dynamic_thresholds(trend)
        
        # 2. 网格维护逻辑
        reset_needed, reset_window = check_reset_conditions(self.state, current_price, current_time)
        if reset_needed:
            self.log(f"触发网格计算 | 原因: 突破或初始 | 窗口: {reset_window}h")
            grid_res = calculate_grids(self.df_history, window_hours=reset_window)
            if grid_res:
                self.state.grid_top = grid_res['grid_top']
                self.state.grid_bottom = grid_res['grid_bottom']
                self.state.entity_grids = grid_res['entity_grids']
                self.state.virtual_grids = grid_res['virtual_grids']
                self.state.last_grid_calc_time = grid_res['calc_time']
                
                # 触发网格归并逻辑 (如果有关联持仓)
                if context and context.positions:
                    signals.extend(self._handle_grid_merge(context, current_price, trend))

        # 3. 确定当前层级
        layer = get_current_layer(current_price, self.state.entity_grids, self.state.virtual_grids)
        
        # 缓存指标供 UI 展示
        self.last_indicators.update({
            'rsi': rsi, 'trend': trend, 'layer': layer, 'atr_pct': atr_pct
        })

        # 4. 交易逻辑
        if context:
            pos = context.positions.get(self.symbol)
            has_long = pos.size > 0 if pos else False
            has_short = pos.size < 0 if pos else False
            
            if layer is None: # 无网格/极端行情模式
                signals.extend(self._logic_no_grid(rsi, has_long, has_short, current_price, current_time, trend))
            else: # 标准网格模式
                signals.extend(self._logic_grid(layer, rsi, has_long, has_short, current_price, current_time, trend))

        # 5. 动态杠杆请求 (通过 context.meta 透传给引擎)
        if context:
            target_lev = 3.0 if atr_pct < 1.5 else (2.0 if atr_pct < 3.0 else 1.0)
            if target_lev != self.current_leverage:
                self.current_leverage = target_lev
                context.meta['requested_leverage'] = target_lev

        return signals

    def _handle_grid_merge(self, context: StrategyContext, price: float, trend: int) -> List[Signal]:
        """归并逻辑：顺势保留，逆势清算"""
        signals = []
        pos = context.positions.get(self.symbol)
        if not pos or pos.size == 0: return []
        
        is_long = pos.size > 0
        # 顺势定义：多+涨(1) 或 空+跌(-1)
        is_aligned = (is_long and trend >= 0) or (not is_long and trend <= 0)
        
        if not is_aligned:
            self.log(f"网格重置：检测到逆势持仓，执行紧急归并平仓 | 趋势:{trend}")
            signals.append(Signal(
                timestamp=datetime.now(timezone.utc),
                symbol=self.symbol,
                side=Side.SELL if is_long else Side.BUY,
                size=abs(pos.size),
                reason="grid_merge_liquidate",
                meta={'posSide': 'long' if is_long else 'short'}
            ))
        else:
            self.log(f"网格重置：检测到顺势持仓，保留并自动归并")
            
        return signals

    def _logic_grid(self, layer: int, rsi: float, has_long: bool, has_short: bool, price: float, ts: datetime, trend: int) -> List[Signal]:
        """标准 3层实体网格逻辑"""
        signals = []
        # 层级定义: -1=VL, 0=L, 1=M, 2=H, 3=VH
        
        # 入场：底层 (0) 做多
        if layer == 0 and not has_long:
            layer_mid = (self.state.entity_grids[0] + self.state.entity_grids[1]) / 2
            if price <= layer_mid and rsi <= self.rsi_oversold:
                size = self.params.get('base_position_eth', 0.05)
                if trend == 1: size *= 1.5 # 顺势加码
                signals.append(self._create_signal(ts, Side.BUY, size, price, "layer0_long", "long"))

        # 入场：高层 (2) 做空
        elif layer == 2 and not has_short:
            layer_mid = (self.state.entity_grids[2] + self.state.entity_grids[3]) / 2
            if price >= layer_mid and rsi >= self.rsi_overbought:
                size = self.params.get('base_position_eth', 0.05)
                if trend == -1: size *= 1.5
                signals.append(self._create_signal(ts, Side.SELL, size, price, "layer2_short", "short"))

        # 出场：RSI 止盈
        if has_long and layer >= 1 and rsi >= self.rsi_exit_overbought:
            signals.append(self._create_signal(ts, Side.SELL, 0, price, "rsi_exit_long", "long"))
        elif has_short and layer <= 1 and rsi <= self.rsi_exit_oversold:
            signals.append(self._create_signal(ts, Side.BUY, 0, price, "rsi_exit_short", "short"))
            
        return signals

    def _logic_no_grid(self, rsi: float, has_long: bool, has_short: bool, price: float, ts: datetime, trend: int) -> List[Signal]:
        """极值/脱离网格模式：纯 RSI 驱动"""
        signals = []
        if rsi <= (self.rsi_oversold - 5) and not has_long:
            signals.append(self._create_signal(ts, Side.BUY, self.params.get('base_position_eth', 0.05), price, "extreme_oversold", "long"))
        elif rsi >= (self.rsi_overbought + 5) and not has_short:
            signals.append(self._create_signal(ts, Side.SELL, self.params.get('base_position_eth', 0.05), price, "extreme_overbought", "short"))
            
        # 出场逻辑相同
        if has_long and rsi >= self.rsi_exit_overbought:
            signals.append(self._create_signal(ts, Side.SELL, 0, price, "extreme_exit_long", "long"))
        elif has_short and rsi <= self.rsi_exit_oversold:
            signals.append(self._create_signal(ts, Side.BUY, 0, price, "extreme_exit_short", "short"))
            
        return signals

    def _create_signal(self, ts: datetime, side: Side, size: float, price: float, reason: str, pos_side: str) -> Signal:
        return Signal(
            timestamp=ts, symbol=self.symbol, side=side, size=size, price=price,
            order_type=OrderType.MARKET, reason=reason,
            meta={'posSide': pos_side}
        )

    def get_state(self) -> Dict[str, Any]:
        return asdict(self.state)

    def set_state(self, state: Dict[str, Any]):
        for k, v in state.items():
            if hasattr(self.state, k):
                if k == 'breakout_time' and v:
                    setattr(self.state, k, datetime.fromisoformat(v))
                else:
                    setattr(self.state, k, v)

    def get_history(self) -> Dict[str, Any]:
        """实现历史补全协议：返回 K 线、指标及资产序列"""
        if self.df_history.empty:
            return {}
            
        # 1. 准备 K 线序列
        df_plot = self.df_history.tail(360)
        history_candles = []
        for ts, row in df_plot.iterrows():
            history_candles.append({
                "time": int(ts.timestamp()) if hasattr(ts, 'timestamp') else int(ts),
                "open": float(row['open']), "high": float(row['high']), 
                "low": float(row['low']), "close": float(row['close']), 
                "volume": float(row['volume'])
            })
            
        # 2. 计算 RSI 历史 (基于 360 根数据重算)
        from cartridges.strategies.v93_innovation.scripts.indicators import calculate_rsi
        prices = df_plot['close'].tolist()
        rsi_period = self.params.get('rsi_period', 14)
        history_rsi = []
        # 为了让 RSI 曲线与 K 线对齐，我们生成对应的坐标点
        for i in range(len(prices)):
            # 至少需要 rsi_period 根数据才有有效 RSI，前期补 50
            sub_prices = prices[:i+1]
            val = calculate_rsi(sub_prices, rsi_period)
            history_rsi.append({
                "time": history_candles[i]['time'],
                "value": val if val is not None else 50.0
            })
            
        # 3. 模拟资产历史 (预热阶段假设资产平稳)
        history_equity = []
        initial_value = 5000.0 # 初始模拟值
        for candle in history_candles:
            history_equity.append({
                "time": candle['time'],
                "value": initial_value
            })
            
        return {
            "history_candles": history_candles,
            "history_rsi": history_rsi,
            "history_equity": history_equity
        }

    def get_status(self, context: StrategyContext) -> Dict[str, Any]:
        """对接 Dashboard 的状态输出 (时间戳强制数字化)"""
        grid_prices = []
        if self.state.entity_grids and self.state.virtual_grids:
            grid_prices = [
                self.state.virtual_grids[1], # VH
                self.state.entity_grids[3],  # P3
                self.state.entity_grids[2],  # P2
                self.state.entity_grids[1],  # P1
                self.state.entity_grids[0],  # P0
                self.state.virtual_grids[0]  # VL
            ]
            
        # 强制数字化时间轴 (Unix 秒)
        ts = self._last_data.timestamp if self._last_data else datetime.now()
        market_ts = int(ts.timestamp()) if hasattr(ts, 'timestamp') else int(ts)
        if not isinstance(market_ts, (int, float)):
            if isinstance(ts, str):
                try: market_ts = int(datetime.fromisoformat(ts).timestamp())
                except: market_ts = int(datetime.now().timestamp())
            else:
                market_ts = int(datetime.now().timestamp())

        return {
            "strategy": {
                'name': self.name,
                'symbol': self.symbol,
                'rsi': round(self.last_indicators['rsi'], 1),
                'trend': self.last_indicators['trend'],
                'layer': self.last_indicators['layer'],
                'leverage': self.current_leverage,
                'grid_prices': grid_prices,
                'grid_range': [self.state.grid_bottom, self.state.grid_top],
                'daily_reset': self.state.daily_reset_count,
            },
            "market_data": {
                'timestamp': market_ts,
                'symbol': self.symbol,
                'open': self._last_data.open if self._last_data else 0,
                'high': self._last_data.high if self._last_data else 0,
                'low': self._last_data.low if self._last_data else 0,
                'close': self._last_data.close if self._last_data else 0,
                'volume': self._last_data.volume if self._last_data else 0
            },
            "cash": context.cash,
            "total_value": context.total_value,
            "positions": {k: {"symbol": v.symbol, "size": v.size, "avg_price": v.avg_price, "unrealized_pnl": v.unrealized_pnl} 
                          for k, v in context.positions.items()}
        }
