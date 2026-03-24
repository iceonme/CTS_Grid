"""
鍥炴祴寮曟搸
浜嬩欢椹卞姩鍥炴祴妗嗘灦
"""

from datetime import datetime
from typing import List, Dict, Optional, Callable, Any
import pandas as pd
import numpy as np

from console.core import (
    MarketData, Signal, Order, FillEvent, Position,
    Side, OrderType, OrderStatus, TradeRecord, PortfolioSnapshot,
    StrategyContext
)
from cartridges.strategies import BaseStrategy
from cartridges.bridge.executors import BaseExecutor, PaperExecutor
from cartridges.bridge.datafeeds import BaseDataFeed


class BacktestEngine:
    """
    鍥炴祴寮曟搸
    
    鑱岃矗锛?
    1. 椹卞姩绛栫暐杩愯锛堜簨浠跺惊鐜級
    2. 缁存姢璧勯噾鍜屾寔浠擄紙鐪熺浉鏉ユ簮锛?
    3. 璁板綍浜ゆ槗鍘嗗彶
    4. 鐢熸垚鍥炴祴鎶ュ憡
    
    浣跨敤绀轰緥锛?
        engine = BacktestEngine(strategy, executor, initial_capital=10000)
        results = engine.run(data_feed)
    """
    
    def __init__(self,
                 strategy: BaseStrategy,
                 executor: Optional[BaseExecutor] = None,
                 initial_capital: float = 10000.0):
        """
        Args:
            strategy: 绛栫暐瀹炰緥
            executor: 鎵ц鍣紙榛樿浣跨敤 PaperExecutor锛?
            initial_capital: 鍒濆璧勯噾
        """
        self.strategy = strategy
        self.executor = executor or PaperExecutor(initial_capital=initial_capital)
        self.initial_capital = initial_capital
        
        # 鐘舵€?
        self._current_time: Optional[datetime] = None
        self._current_prices: Dict[str, float] = {}
        self._trades: List[TradeRecord] = []
        self._equity_curve: List[PortfolioSnapshot] = []
        self._signals: List[Signal] = []
        self._hourly_series: List[Dict] = []  # 鏂板锛氬皬鏃剁骇闄嶉噰鏍疯褰?
        self._last_hour: int = -1
        
        # 娉ㄥ唽鍥炶皟
        self.executor.register_fill_callback(self._on_fill)
        
    def _get_context(self) -> StrategyContext:
        """鏋勫缓绛栫暐涓婁笅鏂?""
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
        """鎴愪氦鍥炶皟"""
        # 璁板綍浜ゆ槗
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
        
        # 閫氱煡绛栫暐
        self.strategy.on_fill(fill)
    
    def _execute_signals(self, signals: List[Signal]):
        """鎵ц淇″彿鍒楄〃"""
        for signal in signals:
            self._signals.append(signal)
            
            # 鍒涘缓璁㈠崟
            order = Order(
                order_id="",  # 鐢辨墽琛屽櫒濉厖
                symbol=signal.symbol,
                side=signal.side,
                size=signal.size,
                order_type=signal.order_type,
                price=signal.price,
                timestamp=signal.timestamp,
                meta=signal.meta
            )
            
            # 鎻愪氦璁㈠崟
            self.executor.submit_order(order)
    
    def _record_equity(self):
        """璁板綍鏉冪泭鏇茬嚎"""
        positions = {}
        for pos in self.executor.get_all_positions():
            # 鏇存柊鏈疄鐜扮泩浜?
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
        
        # 濡傛灉娌℃湁 get_total_value锛屾墜鍔ㄨ绠?
        if snapshot.total_value == 0:
            position_value = sum(
                pos.size * self._current_prices.get(sym, 0)
                for sym, pos in positions.items()
            )
            snapshot.total_value = snapshot.cash + position_value
        
        self._equity_curve.append(snapshot)
    
    def run(self, data_feed: BaseDataFeed, 
            start: Optional[datetime] = None,
            end: Optional[datetime] = None,
            progress_callback: Optional[Callable[[int, int], None]] = None,
            fast_mode: bool = False) -> Dict[str, Any]:
        """
        杩愯鍥炴祴
        
        Args:
            data_feed: 鏁版嵁娴?
            start: 寮€濮嬫椂闂?(鍙€?
            end: 缁撴潫鏃堕棿 (鍙€?
            progress_callback: 杩涘害鍥炶皟 (current, total)
            fast_mode: 鏋侀€熸ā寮忥紙鍏抽棴鎵€鏈?UI 淇℃伅鍜屼笉蹇呰鐨勮褰曪級
        """
        if not fast_mode:
            print(f"\n{'='*60}")
            print(f"鍥炴祴寮€濮?| 绛栫暐: {self.strategy.name}")
            print(f"鍒濆璧勯噾: ${self.initial_capital:,.2f}")
            print(f"{'='*60}\n")
        
        # 閽堝 fast_mode 浼樺寲鎵ц鍣?
        if fast_mode and hasattr(self.executor, 'fast_mode'):
            self.executor.fast_mode = True
        
        # 鍒濆鍖?
        self.strategy.initialize()
        self.strategy.on_start()
        
        # 缁熻
        data_count = 0
        
        # 浜嬩欢寰幆
        for data in data_feed.stream(start=start, end=end):
            self._current_time = data.timestamp
            self._current_prices[data.symbol] = data.close
            
            # 鏇存柊鎵ц鍣ㄥ競鍦烘暟鎹?
            self.executor.update_market_data(data.timestamp, data.close)
            
            # 鏋勫缓涓婁笅鏂囧苟璋冪敤绛栫暐
            context = self._get_context()
            signals = self.strategy.on_data(data, context)
            
            # 鎵ц淇″彿
            if signals:
                self._execute_signals(signals)
            
            # 璁板綍鍘嗗彶杞ㄨ抗 - 鏋侀€熸ā寮忎笅姣?100 姝ヨ褰曚竴娆℃垨涓嶈褰曚腑闂寸姸鎬?
            if not fast_mode or data_count % 100 == 0:
                self._record_equity()
            
            # 楂樻€ц兘闄嶉噰鏍疯褰曪細妫€娴嬪皬鏃惰法瓒?(鐢ㄤ簬鍙鍖?
            current_hour = data.timestamp.hour
            if current_hour != self._last_hour:
                self._hourly_series.append({
                    'timestamp': data.timestamp.isoformat(),
                    'equity': self.executor.get_total_value(),
                    'benchmark': data.close
                })
                self._last_hour = current_hour

            data_count += 1
            
            if not fast_mode and progress_callback and data_count % 100 == 0:
                progress_callback(data_count, 0)
        
        self.strategy.on_stop()
        
        if not fast_mode:
            print(f"\n{'='*60}")
            print(f"鍥炴祴瀹屾垚 | 鍏卞鐞?{data_count} 鏉℃暟鎹?)
            print(f"{'='*60}\n")
        
        return self._generate_report()
    
    def _generate_report(self) -> Dict[str, Any]:
        """鐢熸垚鍥炴祴鎶ュ憡"""
        if not self._equity_curve:
            return {}
        
        # 璁＄畻鎸囨爣
        initial = self.initial_capital
        final = self._equity_curve[-1].total_value
        total_return = (final - initial) / initial
        
        # 鏈€澶у洖鎾?
        equity_values = [s.total_value for s in self._equity_curve]
        peak = equity_values[0]
        max_dd = 0
        for value in equity_values:
            if value > peak:
                peak = value
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
        
        # 澶忔櫘姣旂巼锛堢畝鍖栫増锛?
        returns = pd.Series(equity_values).pct_change().dropna()
        sharpe = 0.0
        if len(returns) > 1 and returns.std() != 0:
            sharpe = returns.mean() / returns.std() * np.sqrt(525600)  # 1鍒嗛挓鏁版嵁骞村寲
        
        # 浜ゆ槗缁熻
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
            'hourly_series': self._hourly_series,  # 瀵煎嚭杞婚噺绾у皬鏃跺簭鍒?
            'trades': self._trades if not self.executor.fast_mode else [], # 鏋侀€熸ā寮忎笅绮剧畝
            'signals': self._signals if not self.executor.fast_mode else [],
            'params': self.strategy.params
        }
        
        return report
    
    def print_report(self, report: Optional[Dict] = None):
        """鎵撳嵃鍥炴祴鎶ュ憡"""
        if report is None:
            report = self._generate_report()
        
        if not report:
            print("鏃犲洖娴嬬粨鏋?)
            return
        
        print("\n" + "=" * 60)
        print(f"鍥炴祴鎶ュ憡 - {self.strategy.name}")
        print("=" * 60)
        
        print(f"\n銆愭敹鐩婃寚鏍囥€?)
        print(f"鎬绘敹鐩婄巼:   {report['total_return']*100:>10.2f}%")
        print(f"鏈€澶у洖鎾?   {report['max_drawdown']*100:>10.2f}%")
        print(f"澶忔櫘姣旂巼:   {report['sharpe_ratio']:>12.2f}")
        
        print(f"\n銆愪氦鏄撶粺璁°€?)
        print(f"鎬讳氦鏄撴鏁? {report['total_trades']:>10}")
        print(f"涔板叆娆℃暟:   {report['buy_count']:>10}")
        print(f"鍗栧嚭娆℃暟:   {report['sell_count']:>10}")
        print(f"鑳滅巼:       {report['win_rate']*100:>10.2f}%")
        print(f"鐩堜簭姣?     {report['profit_factor']:>12.2f}")
        
        print("=" * 60)
