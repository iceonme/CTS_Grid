"""
执行器基类
统一接口：模拟执行、实盘执行都实现此接口
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Callable
from datetime import datetime

from core import Order, FillEvent, Position, OrderStatus


class BaseExecutor(ABC):
    """
    执行器基类
    
    职责：
    1. 接收订单，发送到市场（模拟或真实）
    2. 返回订单ID
    3. 当订单成交时，通过回调通知引擎
    """
    
    def __init__(self):
        self._fill_callbacks: List[Callable[[FillEvent], None]] = []
        
    def register_fill_callback(self, callback: Callable[[FillEvent], None]):
        """注册成交回调"""
        self._fill_callbacks.append(callback)
    
    def _notify_fill(self, fill: FillEvent):
        """通知所有监听者成交事件"""
        for callback in self._fill_callbacks:
            callback(fill)
    
    @abstractmethod
    def submit_order(self, order: Order) -> str:
        """
        提交订单
        
        Args:
            order: 订单信息（不含order_id）
            
        Returns:
            str: 订单ID
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        取消订单
        
        Args:
            order_id: 订单ID
            
        Returns:
            bool: 是否成功
        """
        pass
    
    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        """
        查询持仓
        
        Args:
            symbol: 交易对
            
        Returns:
            Position or None
        """
        pass
    
    @abstractmethod
    def get_all_positions(self) -> List[Position]:
        """
        获取所有持仓
        
        Returns:
            List[Position]
        """
        pass
    
    @abstractmethod
    def get_cash(self) -> float:
        """
        获取可用资金
        
        Returns:
            float: 可用资金
        """
        pass
    
    def get_order_status(self, order_id: str) -> Optional[OrderStatus]:
        """
        查询订单状态（可选实现）
        
        Args:
            order_id: 订单ID
            
        Returns:
            OrderStatus or None
        """
        return None
    
    def update_market_data(self, timestamp: datetime, price: float):
        """
        更新市场数据（用于模拟执行器）
        
        Args:
            timestamp: 当前时间
            price: 当前价格
        """
        pass
