"""
Console 协议层 - 定义微服务间通信的标准事件
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional

from console.core import (
    Side, OrderType, OrderStatus, 
    MarketData, Position, Signal, Order, FillEvent
)

@dataclass
class BaseEvent:
    """所有系统事件的基类"""
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class MarketUpdateEvent(BaseEvent):
    """市场行情更新事件"""
    data: MarketData
    symbol: str = ""

    def __post_init__(self):
        super().__post_init__()
        if not self.symbol:
            self.symbol = self.data.symbol

@dataclass
class AccountUpdateEvent(BaseEvent):
    """账户/仓位更新事件 (私有数据流)"""
    cash: float
    positions: Dict[str, Position]
    total_value: float = 0.0

@dataclass
class SignalRequestEvent(BaseEvent):
    """策略发出的下单请求信号"""
    signal: Signal
    strategy_id: str = ""

@dataclass
class ExecutionReportEvent(BaseEvent):
    """执行器生成的执行报告 (成交或拒单)"""
    order: Order
    fill: Optional[FillEvent] = None
    status: OrderStatus = OrderStatus.PENDING

    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED
