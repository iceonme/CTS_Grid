"""
模拟执行器
在本地模拟订单执行，支持滑点和延迟模拟
"""

import time
import uuid
from datetime import datetime
from typing import Optional, List, Dict
import numpy as np

from core import (
    Order, FillEvent, Position, OrderStatus, 
    Side, OrderType, MarketData
)
from .base import BaseExecutor


class PaperExecutor(BaseExecutor):
    """
    模拟执行器
    
    特性：
    1. 本地模拟成交
    2. 支持滑点模型（固定/自适应）
    3. 支持延迟模拟
    4. 维护虚拟资金和持仓
    """
    
    def __init__(self, 
                 initial_capital: float = 10000.0,
                 fee_rate: float = 0.001,
                 slippage_model: str = 'adaptive',  # none, fixed, adaptive
                 slippage_base: float = 0.0005,
                 latency_ms: float = 0):
        """
        Args:
            initial_capital: 初始资金
            fee_rate: 手续费率
            slippage_model: 滑点模型
            slippage_base: 基础滑点
            latency_ms: 模拟延迟（毫秒）
        """
        super().__init__()
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.fee_rate = fee_rate
        self.slippage_model = slippage_model
        self.slippage_base = slippage_base
        self.latency_ms = latency_ms
        
        # 状态
        self._positions: Dict[str, Position] = {}  # symbol -> Position
        self._orders: Dict[str, Order] = {}  # order_id -> Order
        self._current_price: float = 0.0
        self._current_time: Optional[datetime] = None
        
    def update_market_data(self, timestamp: datetime, price: float):
        """更新市场数据"""
        self._current_time = timestamp
        self._current_price = price
        
    def _calculate_slippage(self, side: Side, amount: float) -> float:
        """计算滑点"""
        if self.slippage_model == 'none':
            return 0.0
        
        if self.slippage_model == 'fixed':
            return self.slippage_base
        
        # 自适应模型
        depth_factor = 1.0
        slippage = self.slippage_base * depth_factor * (1 + np.random.normal(0, 0.3))
        return max(0.0001, min(0.005, slippage))
    
    def _simulate_latency(self):
        """模拟网络延迟"""
        if self.latency_ms > 0:
            actual_latency = self.latency_ms * (0.8 + np.random.random() * 0.4)
            time.sleep(actual_latency / 1000)
    
    def submit_order(self, order: Order) -> str:
        """
        提交订单（立即成交）
        """
        self._simulate_latency()
        
        # 生成订单ID
        order_id = str(uuid.uuid4())[:16]
        order.order_id = order_id
        order.timestamp = self._current_time or datetime.now()
        
        # 计算成交价格（含滑点）
        slippage = self._calculate_slippage(order.side, order.size)
        
        if order.side == Side.BUY:
            executed_price = self._current_price * (1 + slippage)
        else:
            executed_price = self._current_price * (1 - slippage)
        
        # 计算费用
        trade_value = order.size * executed_price
        fee = trade_value * self.fee_rate
        
        # 检查资金/持仓
        if order.side == Side.BUY:
            total_cost = trade_value + fee
            if total_cost > self.cash:
                order.status = OrderStatus.REJECTED
                self._orders[order_id] = order
                return order_id
        else:
            pos = self._positions.get(order.symbol)
            if not pos or pos.size < order.size:
                order.status = OrderStatus.REJECTED
                self._orders[order_id] = order
                return order_id
        
        # 更新资金和持仓
        if order.side == Side.BUY:
            self.cash -= (trade_value + fee)
            
            if order.symbol not in self._positions:
                self._positions[order.symbol] = Position(
                    symbol=order.symbol,
                    size=0.0,
                    avg_price=0.0,
                    entry_time=order.timestamp
                )
            
            pos = self._positions[order.symbol]
            # 更新平均成本
            total_cost = pos.size * pos.avg_price + order.size * executed_price
            pos.size += order.size
            pos.avg_price = total_cost / pos.size if pos.size > 0 else 0
            
        else:
            pos = self._positions[order.symbol]
            
            # 计算实现盈亏
            realized_pnl = (executed_price - pos.avg_price) * order.size - fee
            
            self.cash += (trade_value - fee)
            pos.size -= order.size
            
            if pos.size <= 0:
                del self._positions[order.symbol]
        
        # 更新订单状态
        order.status = OrderStatus.FILLED
        order.filled_size = order.size
        order.avg_price = executed_price
        self._orders[order_id] = order
        
        # 发送成交回报
        fill = FillEvent(
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            filled_size=order.size,
            filled_price=executed_price,
            timestamp=order.timestamp,
            fee=fee,
            pnl=realized_pnl if order.side == Side.SELL else None
        )
        self._notify_fill(fill)
        
        return order_id
    
    def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        if order_id in self._orders:
            order = self._orders[order_id]
            if order.status == OrderStatus.PENDING:
                order.status = OrderStatus.CANCELLED
                return True
        return False
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """获取持仓"""
        return self._positions.get(symbol)
    
    def get_all_positions(self) -> List[Position]:
        """获取所有持仓"""
        return list(self._positions.values())
    
    def get_cash(self) -> float:
        """获取可用资金"""
        return self.cash
    
    def get_total_value(self) -> float:
        """获取总资产"""
        position_value = sum(
            pos.size * self._current_price 
            for pos in self._positions.values()
        )
        return self.cash + position_value
    
    def reset(self):
        """重置状态"""
        self.cash = self.initial_capital
        self._positions.clear()
        self._orders.clear()
