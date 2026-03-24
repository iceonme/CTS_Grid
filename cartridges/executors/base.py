"""
执行器基类
统一接口：模拟执行、实盘执行都实现此接口
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Callable, Any
from datetime import datetime
import asyncio

from console.core import Order, FillEvent, Position, OrderStatus
from console.runner.base_skill import BaseSkill
from console.protocol import SignalRequestEvent, ExecutionReportEvent


class BaseExecutor(BaseSkill, ABC):
    """
    成交执行服务 (Microservice)
    
    职责：
    1. 监听总线上的信号请求
    2. 执行订单并返回执行报告
    """
    
    def __init__(self, name: str = "executor"):
        super().__init__(name=name)

    def on_init(self):
        """订阅信号"""
        self.subscribe("signal_request", self._handle_signal)

    async def _handle_signal(self, event: SignalRequestEvent):
        """响应信号：转为订单并提交"""
        sig = event.signal
        print(f"[Executor:{self.name}] 接收到交易请求: {sig.side.value} {sig.symbol}")
        
        order = Order(
            order_id="",
            symbol=sig.symbol,
            side=sig.side,
            size=sig.size,
            order_type=sig.order_type,
            price=sig.price,
            timestamp=datetime.now(),
            meta=sig.meta
        )
        
        order_id = self.submit_order(order)
        
        # 简单同步反馈（这里假设提交即成交，或者后续由 executor 自身的监听逻辑推送到总线）
        if self.bus:
            # 在一个异步系统里，这里应该是监听底层成交后再发 ExecutionReport
            # 此处演示先同步发回
            await self.bus.emit("execution_report", ExecutionReportEvent(
                order=order, status=order.status
            ))

    @abstractmethod
    def submit_order(self, order: Order) -> str:
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        pass
    
    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        pass
    
    @abstractmethod
    def get_all_positions(self) -> List[Position]:
        pass
    
    @abstractmethod
    def get_cash(self) -> float:
        pass
    
    async def start(self):
        """执行器服务主任务"""
        print(f"[Executor:{self.name}] 执行队列监听已启动...")
        self._running = True
        while self._running:
            await asyncio.sleep(1)
