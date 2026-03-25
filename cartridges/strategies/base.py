"""
策略基类
所有策略必须继承此类
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncio

from console.core import Signal, FillEvent, MarketData, Position, StrategyContext
from console.runner.base_skill import BaseSkill
from console.protocol import (
    MarketUpdateEvent, AccountUpdateEvent, SignalRequestEvent,
    HistoryRequestEvent, MarketHistoryEvent
)


class BaseStrategy(BaseSkill, ABC):
    """
    策略服务 (Microservice)
    """
    
    def __init__(self, name: str = "unnamed", **params):
        super().__init__(name=name)
        self.params = params
        self._initialized = False
        self.warmup_bars: int = 0
        
        # 内部缓存
        self._last_data: Optional[MarketData] = None
        self._last_account: Optional[AccountUpdateEvent] = None

    def on_init(self):
        """初始化订阅 (双保险：兼容字符串与类名)"""
        # 1. 行情流
        self.subscribe("market_update", self._on_market_event)
        self.subscribe("MarketUpdateEvent", self._on_market_event)
        # 2. 账户/执行流
        self.subscribe("account_update", self._on_account_event)
        self.subscribe("AccountUpdateEvent", self._on_account_event)
        self.subscribe("execution_report", self._on_execution_report)
        # 3. 交互流 (历史补全)
        self.subscribe("ui_snapshot_request", self._on_snapshot_request)
        self.subscribe("market_history_update", self._on_market_history_update)
        self.subscribe("MarketHistoryEvent", self._on_market_history_update)

        # 4. [冷启动保险] 强制在 3 秒后触发初始化 (防止首根行情竞态丢失)
        asyncio.create_task(self._ensure_initialized())

    async def _ensure_initialized(self):
        """强制冷启动辅助"""
        await asyncio.sleep(3)
        if not self._initialized:
            print(f"[Base:Strategy] 收到首根行情 | 执行初始化...")
            await self.initialize()
            self._initialized = True

    async def _on_market_event(self, event: MarketUpdateEvent):
        """响应行情更新"""
        self._last_data = event.data
        if not self._initialized:
            print(f"[Base:Strategy] 收到首根行情 | 执行初始化...")
            await self.initialize()
            self._initialized = True
            # 保持 Unix 秒级整数索引，不再转换为 datetime 对象，对齐 V93 数字化逻辑
            # self.df_history.index = pd.to_datetime(self.df_history.index, unit='s')
        
        context = self._build_context()
        signals = self.on_data(event.data, context)
        
        # 发布信号
        if signals and self.bus:
            for sig in signals:
                await self.bus.emit("signal_request", SignalRequestEvent(
                    signal=sig, strategy_id=self.name
                ))

        # 广播增量更新至 UI
        await self._publish_status(context)

    async def _on_market_history_update(self, event: MarketHistoryEvent):
        """处理批量历史数据回填 (不触发逻辑)"""
        # print(f"[Strategy:{self.name}] 接收到历史回填数据: {len(event.data)} 根")
        self._fill_history(event.data)
        
        # [NEW] 数据就绪后立即向 UI 广播 360 根历史 K 线
        if self.bus:
            # print(f"!!! [BASE:EMIT] 正在向 UI 广播 {len(event.data)} 根历史数据...")
            await self.bus.emit("ui_history_update", {
                "strategy_id": self.name,
                "data": [vars(d) if hasattr(d, '__dict__') else d for d in event.data]
            })

    async def _on_snapshot_request(self, event: Dict[str, Any]):
        """响应全量快照请求 (HDMI 握手)"""
        sid = event.get("strategy_id")
        if sid == self.name:
            context = self._build_context()
            
            # 1. 首先推送历史 K 线 (History Channel)
            history = self.get_history()
            if history and self.bus:
                await self.bus.emit("ui_history_update", {
                    "strategy_id": self.name,
                    "data": history
                })
            
            # 2. 紧接着推送当前状态快照 (Update Channel)
            await self._publish_status(context)

    async def _publish_status(self, context: StrategyContext):
        """发布 UI 增量/状态更新"""
        if not self.bus: return
        
        status = self.get_status(context)
        if not status: return
        
        await self.bus.emit("ui_update", {
            "strategy_id": self.name,
            "data": status,
            "timestamp": int(datetime.now().timestamp())
        })

    async def _on_account_event(self, event: AccountUpdateEvent):
        self._last_account = event

    async def _on_execution_report(self, event: Any):
        if event.fill:
            self.on_fill(event.fill)

    async def request_history(self, symbol: str, limit: int = 360):
        """向总线索要历史数据"""
        if self.bus:
            # print(f"[Strategy:{self.name}] 正在请求历史预热: {symbol} (limit={limit})")
            await self.bus.emit("history_request", HistoryRequestEvent(
                symbol=symbol,
                limit=limit,
                strategy_id=self.name
            ))

    def _build_context(self) -> StrategyContext:
        if not self._last_account:
            return StrategyContext(datetime.now(), 0.0, {}, {})
        
        return StrategyContext(
            timestamp=self._last_data.timestamp if self._last_data else datetime.now(),
            cash=self._last_account.cash,
            positions=self._last_account.positions,
            current_prices={self._last_data.symbol: self._last_data.close} if self._last_data else {}
        )

    @abstractmethod
    def on_data(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        pass

    def on_fill(self, fill: FillEvent):
        pass

    def get_status(self, context: StrategyContext) -> Dict[str, Any]:
        return {}
        
    def get_history(self) -> List[Dict[str, Any]]:
        return []

    def _fill_history(self, candles: List[MarketData]):
        """子类需重写此方法以填充自己的缓存"""
        pass

    async def start(self):
        print(f"[Strategy:{self.name}] 策略引擎已上线，正在监听总线信号...")
        self._running = True
        while self._running:
            await asyncio.sleep(1)

    def initialize(self):
        """首次行情进入时触发，可用于请求历史"""
        pass

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_state(self, state: Dict[str, Any]):
        pass

    def log(self, message: str, level: str = "info"):
        print(f"[{level.upper()}] {self.name}: {message}")
