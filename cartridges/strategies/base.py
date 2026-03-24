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
from console.protocol import MarketUpdateEvent, AccountUpdateEvent, SignalRequestEvent


class BaseStrategy(BaseSkill, ABC):
    """
    策略服务 (Microservice)
    
    职责：
    1. 监听总线上的行情和账户更新
    2. 进行决策并发布交易信号事件
    """
    
    def __init__(self, name: str = "unnamed", **params):
        super().__init__(name=name)
        self.params = params
        self._initialized = False
        self.warmup_bars: int = 0
        
        # 内部缓存最新状态（由总线更新）
        self._last_data: Optional[MarketData] = None
        self._last_account: Optional[AccountUpdateEvent] = None

    def on_init(self):
        """初始化订阅"""
        self.subscribe("market_update", self._on_market_event)
        self.subscribe("account_update", self._on_account_event)
        self.subscribe("execution_report", self._on_execution_report)

    async def _on_market_event(self, event: MarketUpdateEvent):
        """响应行情更新"""
        self._last_data = event.data
        if not self._initialized:
            self.initialize()
            self._initialized = True
        
        # 构建 context (使用本地缓存的最新账户状态)
        context = self._build_context()
        signals = self.on_data(event.data, context)
        
        # 发布信号
        if signals and self.bus:
            for sig in signals:
                await self.bus.emit("signal_request", SignalRequestEvent(
                    signal=sig, strategy_id=self.name
                ))

    async def _on_account_event(self, event: AccountUpdateEvent):
        """响应账户更新（同步本地缓存）"""
        self._last_account = event

    async def _on_execution_report(self, event: Any):
        """响应执行反馈"""
        if event.fill:
            self.on_fill(event.fill)

    def _build_context(self) -> StrategyContext:
        """从缓存数据构建策略所需的上下文内容"""
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
        """传统的策略计算逻辑"""
        pass

    def on_fill(self, fill: FillEvent):
        """成交回调"""
        pass

    async def start(self):
        """策略服务主任务：主要由事件回调驱动，只需维持运行"""
        print(f"[Strategy:{self.name}] 策略引擎已上线，正在监听总线信号...")
        self._running = True
        while self._running:
            await asyncio.sleep(1)

    def initialize(self):
        pass

    def get_state(self) -> Dict[str, Any]:
        return {}

    def set_state(self, state: Dict[str, Any]):
        pass
    
    def on_start(self):
        pass
    
    def on_stop(self):
        pass

    def log(self, message: str, level: str = "info"):
        print(f"[{level.upper()}] {self.name}: {message}")
