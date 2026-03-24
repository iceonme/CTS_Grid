"""
BaseSkill - 微服务化 Skill 组件基类
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Optional
from console.bus import EventBus

class BaseSkill(ABC):
    """
    所有 Skill (DataFeed, Strategy, Executor) 的统一基类。
    提供事件总线接入能力和异步运行接口。
    """
    
    def __init__(self, name: str = "base_skill"):
        self.name = name
        self.bus: Optional[EventBus] = None
        self._running = False

    def set_bus(self, bus: EventBus):
        """注入事件总线"""
        self.bus = bus
        self.on_init()

    def on_init(self):
        """初始化钩子（订阅事件等）"""
        pass

    def publish(self, event_type: str, data: Any):
        """快捷发布事件"""
        if self.bus:
            self.bus.publish(event_type, data)

    def subscribe(self, event_type: str, callback: callable):
        """快捷订阅事件"""
        if self.bus:
            self.bus.subscribe(event_type, callback)

    @abstractmethod
    async def start(self):
        """
        [显式启动]
        组件的事件循环或主任务逻辑。
        """
        pass

    async def stop(self):
        """停止组件"""
        self._running = False
