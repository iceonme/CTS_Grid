"""
数据接口基类
"""

from abc import ABC, abstractmethod
from typing import Iterator, List, Optional, Callable, Dict, Any
from datetime import datetime
import asyncio

from console.core import MarketData, Position
from console.runner.base_skill import BaseSkill
from console.protocol import MarketUpdateEvent, AccountUpdateEvent


class BaseDataFeed(BaseSkill, ABC):
    """
    数据接入服务 (Microservice)
    
    职责：
    1. 提供行情数据流 (Public Market Data)
    2. 提供账户状态流 (Account & Position Data)
    """
    
    def __init__(self, symbols: List[str], name: str = "datafeed"):
        super().__init__(name=name)
        self.symbols = symbols if isinstance(symbols, list) else [symbols]
        self._running = False
        
    @abstractmethod
    async def stream(self, start: Optional[datetime] = None, 
                     end: Optional[datetime] = None):
        """异步数据流迭代器 (Async Generator)"""
        yield None

    @abstractmethod
    def get_account_data(self) -> Dict[str, Any]:
        """
        [NEW] 获取账户私有数据 (仓位、余额)
        返回格式: {'cash': float, 'positions': Dict[str, Position]}
        """
        return {'cash': 0.0, 'positions': {}}

    async def start(self):
        """主运行循环：推送行情与账户更新"""
        self._running = True
        print(f"[DataFeed:{self.name}] 正在启动数据推送服务...")
        
        # 核心：使用 async for 驱动异步行情流
        async for data in self.stream():
            if not self._running:
                break
            
            if data is None: continue

            # 1. 发送行情更新
            if self.bus:
                await self.bus.emit("market_update", MarketUpdateEvent(data=data))
            
            # 2. 定期发送账户更新
            account = self.get_account_data()
            if self.bus:
                await self.bus.emit("account_update", AccountUpdateEvent(
                    cash=account.get('cash', 0.0),
                    positions=account.get('positions', {}),
                    total_value=account.get('total_value', 0.0)
                ))
            
            # 让出控制权，确保总线能处理其他任务
            await asyncio.sleep(0.001)

    async def stop(self):
        self._running = False
