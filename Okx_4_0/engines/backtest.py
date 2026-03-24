"""
回测引擎
事件驱动回测框架
"""

from datetime import datetime
from typing import List, Dict, Optional, Callable, Any
import pandas as pd
import numpy as np

from core import (
    MarketData, Signal, Order, FillEvent, Position,
    Side, OrderType, OrderStatus, TradeRecord, PortfolioSnapshot,
    StrategyContext
)
from strategies import BaseStrategy
from executors import BaseExecutor, PaperExecutor
from datafeeds import BaseDataFeed


class BacktestEngine:
    """
    回测引擎
    
    职责：
    1. 驱动策略运行（事件循环）
    2. 维护资金和持仓（真相来源）
    3. 记录交易历史
    4. 生成回测报告
    
    使用示例：
        engine = BacktestEngine(strategy, executor, initial_capital=10000)
        results = engine.run(data_feed)
    """
    
    def __init__(self,
                 strategy: BaseStrategy,
                 executor: Optional[BaseExecutor] = None,
                 initial_capital: float = 10000.0):
        """
        Args:
            strategy: 策略实例
            executor: 执行器（默认使用 PaperExecutor）
            initial_capital: 初始资金
        """
        self.strategy = strategy
        self.executor = executor or PaperExecutor(initial_capital=initial_capital)
        self.initial_capital = initial_capital
        
        # 状态
        self._current_time: Optional[datetime] = None
        self._current_prices: Dict[str, float] = {}
        self._trades: List[TradeRecord] = []
        self._equity_curve: List[PortfolioSnapshot] = []
        self._signals: List[Signal] = []
        
        # 注册回调
        self.executor.register_fill_callback(self._on_fill)
        
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
        # 记录交易
        trade = TradeRecord(
            timestamp=fill.timestamp,
            symbol=fill.symbol,
            side=fill.side,
            size=fill.filled_size,
            price=fill.filled_price,
            fee=fill.fee,
            pnl=fill.pnl,
            reason=""
        )
        self._trades.append(trade)
        
        # 通知策略
        self.strategy.on_fill(fill)
    
    def _execute_signals(self, signals: List[Signal]):
        """执行信号列表"""
        for signal in signals:
            self._signals.append(signal)
            
            # 创建订单
            order = Order(
                order_id="",  # 由执行器填充
                symbol=signal.symbol,
                side=signal.side,
                size=signal.size,
                order_type=signal.order_type,
                price=signal.price,
                timestamp=signal.timestamp,
                meta=signal.meta
            )
            
            # 提交订单
            self.executor.submit_order(order)
    
    def _record_equity(self):
        """记录权益曲线"""
        positions = {}
        for pos in self.executor.get_all_positions():
            # 更新未实现盈亏
            current_price = self._current_prices.get(pos.symbol, pos.avg_price)
            unrealized = (current_price - pos.avg_price) * pos.size
            pos.unrealized_pnl = unrealized
            positions[pos.symbol] = pos
        
        snapshot = PortfolioSnapshot(
            timestamp=self._current_time,
            cash=self.executor.get_cash(),
            positions=positions,
            total_value=self.executor.get_total_value() if hasattr(self.executor, 'get_total_value') else 0
        )
        
        # 如果没有 get_total_value，手动计算
        if snapshot.total_value == 0:
            position_value = sum(
                pos.size * self._current_prices.get(sym, 0)
                for sym, pos in positions.items()
            )
            snapshot.total_value = snapshot.cash + position_value
        
        self._equity_curve.append(snapshot)
    
    def run(self, data_feed: BaseDataFeed, 
            progress_callback: Optional[Callable[[int, int], None]] = None) -> Dict[str, Any]:
        """
        运行回测
        
        Args:
            data_feed: 数据流
            progress_callback: 进度回调 (current, total)
            
        Returns:
            回测结果字典
        """
        print(f"\n{'='*60}")
        print(f"回测开始 | 策略: {self.strategy.name}")
        print(f"初始资金: ${self.initial_capital:,.2f}")
        print(f"{'='*60}\n")
        
        # 初始化
        self.strategy.initialize()
        self.strategy.on_start()
        
        # 统计
        data_count = 0
        
        # 事件循环
        for data in data_feed.stream():
            self._current_time = data.timestamp
            self._current_prices[data.symbol] = data.close
            
            # 更新执行器市场数据
            self.executor.update_market_data(data.timestamp, data.close)
            
            # 构建上下文并调用策略
            context = self._get_context()
            signals = self.strategy.on_data(data, context)
            
            # 执行信号
            if signals:
                self._execute_signals(signals)
            
            # 记录权益
            self._record_equity()
            
            data_count += 1
            
            if progress_callback and data_count % 100 == 0:
                progress_callback(data_count, 0)  # total 未知
        
        self.strategy.on_stop()
        
        print(f"\n{'='*60}")
        print(f"回测完成 | 共处理 {data_count} 条数据")
        print(f"{'='*60}\n")
        
        return self._generate_report()
    
    def _generate_report(self) -> Dict[str, Any]:
        """生成回测报告"""
        if not self._equity_curve:
            return {}
        
        # 计算指标
        initial = self.initial_capital
        final = self._equity_curve[-1].total_value
        total_return = (final - initial) / initial
        
        # 最大回撤
        equity_values = [s.total_value for s in self._equity_curve]
        peak = equity_values[0]
        max_dd = 0
        for value in equity_values:
            if value > peak:
                peak = value
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
        
        # 夏普比率（简化版）
        returns = pd.Series(equity_values).pct_change().dropna()
        sharpe = 0.0
        if len(returns) > 1 and returns.std() != 0:
            sharpe = returns.mean() / returns.std() * np.sqrt(525600)  # 1分钟数据年化
        
        # 交易统计
        buy_trades = [t for t in self._trades if t.side == Side.BUY]
        sell_trades = [t for t in self._trades if t.side == Side.SELL]
        
        winning_sells = [t for t in sell_trades if t.pnl and t.pnl > 0]
        win_rate = len(winning_sells) / len(sell_trades) if sell_trades else 0
        
        avg_win = np.mean([t.pnl for t in winning_sells]) if winning_sells else 0
        losing_sells = [t for t in sell_trades if t.pnl and t.pnl <= 0]
        avg_loss = np.mean([t.pnl for t in losing_sells]) if losing_sells else 0
        
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
        
        report = {
            'initial_capital': initial,
            'final_equity': final,
            'total_return': total_return,
            'max_drawdown': max_dd,
            'sharpe_ratio': sharpe,
            'total_trades': len(self._trades),
            'buy_count': len(buy_trades),
            'sell_count': len(sell_trades),
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'equity_curve': self._equity_curve,
            'trades': self._trades,
            'signals': self._signals,
            'params': self.strategy.params
        }
        
        return report
    
    def print_report(self, report: Optional[Dict] = None):
        """打印回测报告"""
        if report is None:
            report = self._generate_report()
        
        if not report:
            print("无回测结果")
            return
        
        print("\n" + "=" * 60)
        print(f"回测报告 - {self.strategy.name}")
        print("=" * 60)
        
        print(f"\n【收益指标】")
        print(f"总收益率:   {report['total_return']*100:>10.2f}%")
        print(f"最大回撤:   {report['max_drawdown']*100:>10.2f}%")
        print(f"夏普比率:   {report['sharpe_ratio']:>12.2f}")
        
        print(f"\n【交易统计】")
        print(f"总交易次数: {report['total_trades']:>10}")
        print(f"买入次数:   {report['buy_count']:>10}")
        print(f"卖出次数:   {report['sell_count']:>10}")
        print(f"胜率:       {report['win_rate']*100:>10.2f}%")
        print(f"盈亏比:     {report['profit_factor']:>12.2f}")
        
        print("=" * 60)
