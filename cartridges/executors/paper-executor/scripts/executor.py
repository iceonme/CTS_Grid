import time
import uuid
import numpy as np
from datetime import datetime
from typing import Optional, List, Dict

from console.core import (
    Order, FillEvent, Position, OrderStatus, 
    Side, OrderType, MarketData
)
from cartridges.executors.base import BaseExecutor

class PaperExecutorSkill(BaseExecutor):
    """
    模拟执行器技能包封装
    """
    def __init__(self, **params):
        super().__init__()
        self.initial_capital = params.get('initial_capital', 10000.0)
        self.cash = self.initial_capital
        self.fee_rate = params.get('fee_rate', 0.001)
        self.slippage_model = params.get('slippage_model', 'adaptive')
        self.slippage_base = params.get('slippage_base', 0.0005)
        self.latency_ms = params.get('latency_ms', 0)
        self.fast_mode = params.get('fast_mode', False)
        
        # 状态
        self._positions: Dict[str, Position] = {}
        self._orders: Dict[str, Order] = {}
        self._current_price: float = 0.0
        self._current_time: Optional[datetime] = None

    def update_market_data(self, timestamp: datetime, price: float):
        self._current_time = timestamp
        self._current_price = price

    def submit_order(self, order: Order) -> str:
        self._simulate_latency()
        
        order_id = "f-order" if self.fast_mode else str(uuid.uuid4())[:16]
        order.order_id = order_id
        
        from datetime import timezone
        order.timestamp = self._current_time or datetime.now(timezone.utc)
        
        # 撮合逻辑
        slippage = self._calculate_slippage(order.side, order.size)
        executed_price = self._current_price * (1 + slippage if order.side == Side.BUY else 1 - slippage)
        
        size_in_quote = bool(order.meta.get('size_in_quote', False))
        executed_size = float(order.size)
        trade_value = executed_size * executed_price
        
        if order.side == Side.BUY and size_in_quote:
            trade_value = float(order.size)
            executed_size = trade_value / executed_price
            
        fee = trade_value * self.fee_rate
        
        # 检查风险
        if order.side == Side.BUY:
            if trade_value + fee > self.cash:
                order.status = OrderStatus.REJECTED
                return order_id
        else:
            pos = self._positions.get(order.symbol)
            if not pos or pos.size < executed_size:
                order.status = OrderStatus.REJECTED
                return order_id

        # 更新账本
        realized_pnl = None
        if order.side == Side.BUY:
            self.cash -= (trade_value + fee)
            if order.symbol not in self._positions:
                self._positions[order.symbol] = Position(order.symbol, 0, 0, order.timestamp)
            pos = self._positions[order.symbol]
            new_val = pos.size * pos.avg_price + executed_size * executed_price
            pos.size += executed_size
            pos.avg_price = new_val / pos.size if pos.size > 0 else 0
        else:
            pos = self._positions[order.symbol]
            realized_pnl = (executed_price - pos.avg_price) * executed_size - fee
            self.cash += (trade_value - fee)
            pos.size -= executed_size
            if pos.size <= 0: del self._positions[order.symbol]

        order.status = OrderStatus.FILLED
        order.filled_size = executed_size
        order.avg_price = executed_price
        order.fee = fee
        self._orders[order_id] = order
        
        fill = FillEvent(
            order_id=order_id, symbol=order.symbol, side=order.side,
            filled_size=executed_size, filled_price=executed_price,
            timestamp=order.timestamp, fee=fee, pnl=realized_pnl,
            quote_amount=trade_value
        )
        self._notify_fill(fill)
        return order_id

    def _calculate_slippage(self, side: Side, amount: float) -> float:
        if self.slippage_model == 'none': return 0.0
        if self.slippage_model == 'fixed': return self.slippage_base
        return self.slippage_base * (1 + np.random.normal(0, 0.3))

    def _simulate_latency(self):
        if not self.fast_mode and self.latency_ms > 0:
            time.sleep(self.latency_ms / 1000)

    def cancel_order(self, order_id: str) -> bool:
        if order_id in self._orders:
            order = self._orders[order_id]
            if order.status == OrderStatus.PENDING:
                order.status = OrderStatus.CANCELLED
                return True
        return False

    def reset(self):
        self.cash = self.initial_capital
        self._positions.clear()
        self._orders.clear()

    def save_state(self, filepath: str):
        import json
        import os
        state = {
            'cash': self.cash,
            'initial_capital': self.initial_capital,
            'positions': {
                symbol: {
                    'symbol': pos.symbol,
                    'size': pos.size,
                    'avg_price': pos.avg_price,
                    'entry_time': pos.entry_time.isoformat() if pos.entry_time else None
                } for symbol, pos in self._positions.items()
            }
        }
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=4)
        except Exception as e:
            print(f"[PaperExecutorSkill] 保存状态失败: {e}")

    def load_state(self, filepath: str):
        import json
        import os
        if not os.path.exists(filepath):
            return False
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.cash = data.get('cash', self.initial_capital)
            self._positions.clear()
            for symbol, pos_data in data.get('positions', {}).items():
                entry_time = None
                if pos_data.get('entry_time'):
                    entry_time = datetime.fromisoformat(pos_data['entry_time'])
                self._positions[symbol] = Position(
                    symbol=pos_data['symbol'],
                    size=float(pos_data['size']),
                    avg_price=float(pos_data['avg_price']),
                    entry_time=entry_time
                )
            return True
        except Exception as e:
            print(f"[PaperExecutorSkill] 加载状态失败: {e}")
            return False
    def get_cash(self) -> float:
        return self.cash

    def get_position(self, symbol: str) -> Optional[Position]:
        return self._positions.get(symbol)

    def get_all_positions(self) -> List[Position]:
        return list(self._positions.values())
