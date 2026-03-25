"""
ATSEngine - 交易系统核心引擎 (v3.1)
职责：
1. 维护事件总线 (EventBus)
2. 管理组件 (Skills) 生命周期
3. 内建“黑匣子”日志系统，记录全系统事件
"""

import asyncio
import os
import json
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import datetime

from console.bus import EventBus
from console.runner.base_skill import BaseSkill

@dataclass
class StrategySlot:
    """策略运行槽：组合 DataFeed, Strategy, Executor"""
    slot_id: str
    display_name: str
    feed: BaseSkill
    strategy: BaseSkill
    executor: BaseSkill
    
    def set_bus(self, bus: EventBus):
        self.feed.set_bus(bus)
        self.strategy.set_bus(bus)
        self.executor.set_bus(bus)

class ATSEngine:
    """
    ATS 核心引擎 - 系统的“心脏”与“总线枢纽”。
    """
    
    def __init__(self, log_dir: str = "logs/trading"):
        self.bus = EventBus()
        self.log_dir = log_dir
        self._slots: Dict[str, StrategySlot] = {}
        self._skills: List[BaseSkill] = []
        self._tasks: List[asyncio.Task] = []
        self._running = False
        
        # 初始化黑匣子日志文件
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        self.log_file = os.path.join(self.log_dir, f"ats_engine_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl")
        
        # 引擎内建：自动订阅所有关键事件进行记录
        self._setup_core_logging()

    def _setup_core_logging(self):
        """核心日志挂接：监听总线上的所有协议事件"""
        event_types = [
            "market_update", "account_update", "signal_request", "execution_report", "control_request",
            "history_request", "market_history_update", "ui_update", "ui_history_update", "ui_snapshot_request"
        ]
        for event_type in event_types:
            self.bus.subscribe(event_type, self._record_event)

    async def _record_event(self, event: Any):
        """黑匣子记录逻辑：将事件持久化 (鲁棒型)"""
        # 提取时间戳
        ts = getattr(event, 'timestamp', None)
        event_name = event.__class__.__name__
        
        if isinstance(event, dict):
            ts = event.get('timestamp', ts)
            event_name = "GenericEvent"
            
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except:
                ts = datetime.now()
        elif not isinstance(ts, datetime):
            ts = datetime.now()

        entry = {
            "event": event_name,
            "time": ts.isoformat(),
            "payload": self._serialize(event)
        }
        
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception as e:
            print(f"[Engine] 日志录入失败: {e}")

    def _serialize(self, obj, seen=None):
        """增强版序列化，防止循环引用"""
        if seen is None: seen = set()
        
        if id(obj) in seen:
            return "<Circular Reference>"
        
        import math
        from enum import Enum
        
        if isinstance(obj, (int, float, str, bool, type(None))):
            if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
                return None
            return obj
        
        if isinstance(obj, datetime):
            return obj.isoformat()
            
        if isinstance(obj, Enum):
            return obj.value

        if isinstance(obj, (list, tuple)):
            return [self._serialize(v, seen | {id(obj)}) for v in obj]
            
        if isinstance(obj, dict):
            return {str(k): self._serialize(v, seen | {id(obj)}) for k, v in obj.items()}

        if hasattr(obj, "__dict__"):
            return {k: self._serialize(v, seen | {id(obj)}) for k, v in obj.__dict__.items() if not k.startswith('_')}
            
        return str(obj)

    def add_slot(self, slot: StrategySlot):
        """插入一个策略槽"""
        self._slots[slot.slot_id] = slot
        # 强制对齐策略名称与槽位 ID，确保 UI 协议/Socket 房间一致
        slot.strategy.name = slot.slot_id
        slot.set_bus(self.bus)
        print(f"[Engine] 已载入策略槽: {slot.display_name} ({slot.slot_id})")

    def add_skill(self, skill: BaseSkill):
        """插入一个观察者或辅助型 Skill"""
        self._skills.append(skill)
        skill.set_bus(self.bus)
        print(f"[Engine] 已载入观察者 Skill: {skill.name}")

    async def run(self):
        """全系统供电启动"""
        self._running = True
        print(f"[Engine] ATS 核心已上线，记录至: {self.log_file}")
        
        # 1. 启动事件总线
        self._tasks.append(asyncio.create_task(self.bus.start()))
        
        # 2. 启动所有业务微服务
        for slot in self._slots.values():
            self._tasks.append(asyncio.create_task(slot.executor.start()))
            self._tasks.append(asyncio.create_task(slot.feed.start()))
            self._tasks.append(asyncio.create_task(slot.strategy.start()))

        # 3. 启动所有辅助服务 (如 Dashboard)
        for skill in self._skills:
            self._tasks.append(asyncio.create_task(skill.start()))

        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def stop(self):
        """优雅关闭"""
        self._running = False
        print("[Engine] 正在关闭所有微服务...")
        for slot in self._slots.values():
            await slot.strategy.stop()
            await slot.feed.stop()
            await slot.executor.stop()
        
        for skill in self._skills:
            await skill.stop()
        
        self.bus.stop()
        for t in self._tasks:
             t.cancel()
        print("[Engine] 系统已安全关闭")
