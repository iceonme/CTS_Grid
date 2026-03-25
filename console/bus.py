"""
EventBus - 系统内部事件总线
支持组件间的异步/同步通信，实现微服务化的“供电即运行”架构。
"""

import asyncio
from typing import Dict, List, Any, Callable, Type
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Event:
    """所有系统事件的基类"""
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

class EventBus:
    """
    轻量级内建事件总线
    支持基于主题(Topic)或类型(Type)的发布/订阅模式。
    """
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._loop = asyncio.get_event_loop()
        self._queue = asyncio.Queue()
        self._running = False

    def subscribe(self, event_type: str, callback: Callable):
        """订阅事件类型"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        print(f"[EventBus] 注册订阅者: {event_type} -> {callback.__name__ if hasattr(callback, '__name__') else callback}")

    def publish(self, event_type: str, data: Any):
        """发布同步事件（立即触发回调）"""
        if event_type in self._subscribers:
            for callback in self._subscribers[event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.create_task(callback(data))
                    else:
                        callback(data)
                except Exception as e:
                    print(f"[EventBus] 回调异常 [{event_type}]: {e}")

    async def emit(self, event_type: str, data: Any):
        """发布异步事件（存入队列，异步处理）"""
        await self._queue.put((event_type, data))

    async def start(self):
        """启动事件处理循环"""
        self._running = True
        print("[EventBus] 事件总线已上线")
        while self._running:
            try:
                event_type, data = await self._queue.get()
                # 特别打印：只看关键握手信号，不看高频行情，避免刷屏
                if event_type in ["history_request", "market_history_update", "ui_snapshot_request"]:
                    print(f"[EventBus:BUS] 捕获关键信号: {event_type}")
                self.publish(event_type, data)
                self._queue.task_done()
            except Exception as e:
                print(f"[EventBus] 处理模块异常: {e}")

    def stop(self):
        """停止事件总线"""
        self._running = False
