"""
实盘引擎
连接真实交易所运行策略
"""

import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any

from core import (
    MarketData, Signal, Order, FillEvent, Position,
    StrategyContext, PortfolioSnapshot, OrderStatus
)
from strategies import BaseStrategy
from executors import BaseExecutor
from datafeeds import BaseDataFeed


class LiveEngine:
    """
    实盘/模拟盘引擎
    
    职责：
    1. 接收实时数据
    2. 驱动策略运行
    3. 执行信号
    4. 维护状态同步
    
    与回测引擎的区别：
    - 数据是持续的、实时的
    - 支持手动停止/启动
    - 支持状态监控回调（用于Dashboard）
    """
    
    def __init__(self,
                 strategy: BaseStrategy,
                 executor: BaseExecutor,
                 data_feed: BaseDataFeed,
                 warmup_bars: int = 100):
        """
        Args:
            strategy: 策略实例
            executor: 执行器（PaperExecutor 或 OKXExecutor）
            data_feed: 数据流
            warmup_bars: 预热所需的历史数据条数
        """
        self.strategy = strategy
        self.executor = executor
        self.data_feed = data_feed
        self.warmup_bars = warmup_bars
        
        # 状态
        self.is_running = False
        self._is_warmed = False
        self._current_time: Optional[datetime] = None
        self._current_prices: Dict[str, float] = {}
        self._equity_curve: List[PortfolioSnapshot] = []
        self._trades: List[Dict] = []
        
        # 图表历史数据同步
        self._history_candles: List[Dict] = []
        
        # 监控回调
        self._status_callbacks: List[Callable[[Dict], None]] = []
        
        # 注册回调
        self.executor.register_fill_callback(self._on_fill)
        self.data_feed.register_data_callback(self._on_data)
    
    def register_status_callback(self, callback: Callable[[Dict], None]):
        """注册状态监控回调（用于Dashboard）"""
        self._status_callbacks.append(callback)
    
    def _get_context(self) -> StrategyContext:
        """构建策略上下文"""
        positions = {}
        for pos in self.executor.get_all_positions():
            positions[pos.symbol] = pos
        
        return StrategyContext(
            timestamp=self._current_time,
            cash=self.executor.get_cash(),
            positions=positions,
            current_prices=self._current_prices.copy()
        )
    
    def _on_fill(self, fill: FillEvent):
        """成交回调"""
        # 通知策略
        self.strategy.on_fill(fill)
        
        # 构建交易记录详情
        side = fill.side.value.upper()
        symbol = fill.symbol
        price = fill.filled_price
        size = fill.filled_size
        quote_amount = fill.quote_amount
        
        # 格式化显示信息
        if side == 'BUY' and quote_amount:
            # 买入：显示花费了多少USDT，买了多少BTC
            detail = f"花费 {quote_amount:.2f} USDT 买入 {size:.6f} BTC"
        elif side == 'SELL' and quote_amount:
            # 卖出：显示卖出了多少BTC，获得了多少USDT
            detail = f"卖出 {size:.6f} BTC 获得 {quote_amount:.2f} USDT"
        else:
            detail = f"数量={size:.6f} 价格={price:.2f}"
        
        # 记录交易
        trade_record = {
            'type': side,
            'symbol': symbol,
            'price': price,
            'size': size,
            'quote_amount': quote_amount,
            'pnl': fill.pnl,
            'time': fill.timestamp.isoformat(),
            'detail': detail
        }
        self._trades.append(trade_record)
        
        print(f"[成交] {side} {symbol} | {detail} | 价格=${price:.2f}")
    
    def _on_data(self, data: MarketData):
        """数据回调（用于预热）"""
        pass
    
    def _execute_signals(self, signals: List[Signal]):
        """执行信号"""
        for signal in signals:
            order = Order(
                order_id="",
                symbol=signal.symbol,
                side=signal.side,
                size=signal.size,
                order_type=signal.order_type,
                price=signal.price,
                timestamp=signal.timestamp,
                meta=signal.meta
            )
            order_id = self.executor.submit_order(order)
            if not order_id or order.status == OrderStatus.REJECTED:
                reason = order.meta.get('reject_reason', 'submit_failed_or_rejected')
                print(
                    f"[执行拒单] symbol={order.symbol} side={order.side.value} "
                    f"size={order.size} reason={reason}"
                )
    
    def _notify_status(self, data: Dict):
        """通知监控器"""
        for callback in self._status_callbacks:
            try:
                callback(data)
            except Exception as e:
                print(f"状态回调错误: {e}")
    
    def warmup(self):
        """
        预热：获取历史数据初始化策略
        在 run() 之前调用
        """
        # 每次预热前先重置策略，避免历史缓存与旧状态混杂
        self.strategy.initialize()

        print(f"正在预热策略，获取 {self.warmup_bars} 条历史数据...")
        
        # 从API获取历史数据预热
        try:
            # 尝试从数据流的API获取历史数据
            if hasattr(self.data_feed, 'api'):
                df = self.data_feed.api.get_candles(
                    self.data_feed._inst_id, 
                    self.data_feed._bar_map.get(self.data_feed.timeframe, '1m'), 
                    limit=self.warmup_bars
                )
                
                if df is not None and len(df) > 0:
                    print(f"  成功获取 {len(df)} 条历史数据")
                    
                    # 将历史数据喂给策略
                    for timestamp, row in df.iterrows():
                        from core import MarketData
                        data = MarketData(
                            timestamp=timestamp,
                            symbol=self.data_feed.symbol,
                            open=float(row['open']),
                            high=float(row['high']),
                            low=float(row['low']),
                            close=float(row['close']),
                            volume=float(row['volume'])
                        )
                        
                        # 更新策略内部状态（不生成信号）
                        self.strategy._update_buffer(data)
                        self.strategy._current_prices[data.symbol] = data.close
                    
                    # 计算初始网格
                    df_internal = self.strategy._get_dataframe()
                    if len(df_internal) > 50:
                        self.strategy.state.grid_upper, self.strategy.state.grid_lower, _ = \
                            self.strategy._calculate_dynamic_grid(df_internal)
                        self.strategy.state.grid_prices = [
                            float(p) for p in 
                            __import__('numpy', fromlist=['linspace']).linspace(
                                self.strategy.state.grid_lower, 
                                self.strategy.state.grid_upper, 
                                self.strategy.params['grid_levels']
                            )
                        ]
                        self.strategy.state.last_grid_update = len(df_internal)
                        print(f"  网格初始化: [{self.strategy.state.grid_lower:.2f}, {self.strategy.state.grid_upper:.2f}]")
                else:
                    print("  警告: 未能获取历史数据，将使用实时数据初始化")
            else:
                print("  数据流不支持API接口，将使用实时数据初始化")
                
        except Exception as e:
            print(f"  预热过程出错: {e}")
            import traceback
            traceback.print_exc()
        
        
        self._is_warmed = True
        print("预热完成")
        return True
    
    def run(self):
        """启动引擎"""
        if not self._is_warmed and not self.warmup():
            print("预热失败，无法启动")
            return
        
        self.is_running = True
        self.strategy.on_start()
        
        print(f"\n{'='*60}")
        print(f"实盘引擎启动 | 策略: {self.strategy.name}")
        print(f"{'='*60}\n")
        
        try:
            data_count = 0
            for data in self.data_feed.stream():
                if not self.is_running:
                    break
                
                data_count += 1
                self._current_time = data.timestamp
                self._current_prices[data.symbol] = data.close
                
                # 更新执行器并同步图表历史
                self.executor.update_market_data(data.timestamp, data.close)
                self._sync_history_candles(data)
                
                # 策略决策
                context = self._get_context()
                signals = self.strategy.on_data(data, context)
                
                # 执行
                if signals:
                    print(f"[引擎] 生成 {len(signals)} 个信号")
                    for sig in signals:
                        if sig.side.value == 'buy':
                            print(f"[DEBUG BUY] price={data.close:.2f} size={sig.size:.4f} reason={sig.reason} "
                                  f"rsi={self.strategy.state.current_rsi:.1f} layers={self._estimate_layers()}")
                    self._execute_signals(signals)
                
                # 发送状态更新
                status = self._build_status(data)
                self._notify_status(status)
                
                # 每 5 条数据打印一次日志
                if data_count % 5 == 0:
                    print(f"[引擎] 已处理 {data_count} 条数据 | 价格: {data.close:.2f} | 持仓: {len(status['positions'])}层")
                
        except KeyboardInterrupt:
            print("\n收到停止信号...")
        except Exception as e:
            print(f"引擎错误: {e}")
        finally:
            self.stop()
    
    def _estimate_layers(self) -> int:
        """估算当前持仓层数"""
        try:
            positions = self.executor.get_all_positions()
            cash = self.executor.get_cash()
            total = cash + sum(p.size * self._current_prices.get(p.symbol, 0) for p in positions)
            if total <= 0:
                return 0
            for pos in positions:
                if pos.symbol == self.strategy.symbol:
                    base = max(total * self.strategy.params['base_position_pct'], self.strategy.params['min_order_usdt'])
                    return max(1, int(__import__('numpy').ceil(pos.size * self._current_prices.get(pos.symbol, 0) / base)))
        except Exception:
            pass
        return 0
    
    def _build_status(self, data: MarketData) -> Dict:
        """构建状态信息"""
        positions = self.executor.get_all_positions()
        cash = self.executor.get_cash()
        if hasattr(self.executor, 'get_total_value'):
            total_value = self.executor.get_total_value()
            position_value = total_value - cash
        else:
            position_value = sum(
                pos.size * self._current_prices.get(pos.symbol, 0)
                for pos in positions
            )
            total_value = cash + position_value
        
        # 获取策略状态
        context = self._get_context()
        strategy_status = self.strategy.get_status(context)
        
        # 计算盈亏比
        initial_balance = getattr(self.executor, 'initial_capital', 10000.0)
        pnl_pct = (total_value - initial_balance) / initial_balance * 100
        
        trade_history = self._trades[-20:]
        if hasattr(self.executor, 'get_recent_trades'):
            try:
                trade_history = self.executor.get_recent_trades(
                    inst_id=data.symbol.replace('/', '-'),
                    limit=20
                )
            except Exception:
                trade_history = self._trades[-20:]

        return {
            'timestamp': data.timestamp.isoformat(),
            'symbol': data.symbol,
            'price': data.close,
            'open': data.open,
            'high': data.high,
            'low': data.low,
            # 前端图表核心：K线对象
            'candle': {
                't': int(data.timestamp.timestamp() * 1000),
                'o': data.open,
                'h': data.high,
                'l': data.low,
                'c': data.close
            },
            'cash': cash,
            'position_value': position_value,
            'total_value': total_value,
            'initial_balance': initial_balance,
            'pnl_pct': pnl_pct,
            'rsi': strategy_status.get('current_rsi', 50.0),
            'strategy': strategy_status,
            'positions': {
                p.symbol: p.size for p in positions
            },
            'trade_history': trade_history, # 统一字段名为 trade_history
            'history_candles': self._history_candles[-200:]  # 同步历史K线数据
        }
    
    def _sync_history_candles(self, data: MarketData):
        """同步历史K线数据到图表"""
        candle = {
            't': int(data.timestamp.timestamp() * 1000),
            'o': data.open,
            'h': data.high,
            'l': data.low,
            'c': data.close
        }
        # 去重：检查是否已存在相同时间戳
        if self._history_candles and self._history_candles[-1]['t'] == candle['t']:
            self._history_candles[-1] = candle  # 更新当前K线
        else:
            self._history_candles.append(candle)
        # 限制历史数据大小
        if len(self._history_candles) > 1000:
            self._history_candles = self._history_candles[-1000:]

    def stop(self):
        """停止引擎"""
        self.is_running = False
        self._is_warmed = False
        self.strategy.on_stop()
        self.data_feed.stop()
        print("\n引擎已停止")
