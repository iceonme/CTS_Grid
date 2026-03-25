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

@dataclass(kw_only=True)
class BaseEvent:
    """所有系统事件的基类"""
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """为子类提供 super().__post_init__() 支持"""
        pass

@dataclass(kw_only=True)
class MarketUpdateEvent(BaseEvent):
    """市场行情更新事件"""
    data: MarketData
    symbol: str = ""

    def __post_init__(self):
        super().__post_init__()
        if not self.symbol:
            self.symbol = self.data.symbol

@dataclass(kw_only=True)
class AccountUpdateEvent(BaseEvent):
    """账户/仓位更新事件 (私有数据流)"""
    cash: float
    positions: Dict[str, Position]
    total_value: float = 0.0

@dataclass(kw_only=True)
class SignalRequestEvent(BaseEvent):
    """策略发出的下单请求信号"""
    signal: Signal
    strategy_id: str = ""

@dataclass(kw_only=True)
class ExecutionReportEvent(BaseEvent):
    """执行器生成的执行报告 (成交或拒单)"""
    order: Order
    fill: Optional[FillEvent] = None
    status: OrderStatus = OrderStatus.PENDING
    strategy_id: str = ""

    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED

@dataclass(kw_only=True)
class HistoryRequestEvent(BaseEvent):
    """历史数据请求事件 (由策略发起)"""
    symbol: str
    limit: int = 200
    strategy_id: str = ""

@dataclass(kw_only=True)
class MarketHistoryEvent(BaseEvent):
    """批量市场历史事件 (响应请求或主动推送)"""
    symbol: str
    data: List[MarketData]

@dataclass(kw_only=True)
class ControlRequestEvent(BaseEvent):
    """通用控制指令请求 (由 UI 或总线发起)"""
    cmd: str
    strategy_id: str = ""
    data: Any = None
