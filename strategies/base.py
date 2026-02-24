"""
策略基类
所有策略必须继承此类
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime

from core import Signal, FillEvent, MarketData, Position, StrategyContext


class BaseStrategy(ABC):
    """
    策略基类
    
    设计原则：
    1. 策略无状态（不维护资金、持仓）
    2. 只输出信号，不关心如何执行
    3. 通过 on_fill 回调了解成交情况
    
    使用方式：
        strategy = MyStrategy(param1=1, param2=2)
        for data in market_feed:
            context = engine.get_context()  # 引擎提供当前状态
            signals = strategy.on_data(data, context)
            for signal in signals:
                engine.execute(signal)
    """
    
    def __init__(self, name: str = "unnamed", **params):
        """
        初始化策略参数
        
        Args:
            name: 策略名称
            **params: 策略参数（如 rsi_period=14）
        """
        self.name = name
        self.params = params
        self._initialized = False
        
    def initialize(self):
        """
        策略初始化（子类可重写）
        在第一次 on_data 调用前执行
        """
        self._initialized = True
    
    @abstractmethod
    def on_data(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        """
        接收市场数据，返回交易信号
        
        Args:
            data: 市场数据（K线或Tick）
            context: 当前账户状态
            
        Returns:
            List[Signal]: 交易信号列表（可能为空）
        """
        pass
    
    def on_fill(self, fill: FillEvent):
        """
        成交回调（可选重写）
        当订单成交时，引擎调用此方法通知策略
        
        Args:
            fill: 成交详情
        """
        pass
    
    def on_start(self):
        """策略开始运行前调用（可选重写）"""
        pass
    
    def on_stop(self):
        """策略停止时调用（可选重写）"""
        pass
    
    def get_param(self, key: str, default: Any = None) -> Any:
        """获取策略参数"""
        return self.params.get(key, default)
