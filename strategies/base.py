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
    策略基类 (Architecture 2.0)
    """
    
    def __init__(self, name: str = "unnamed", **params):
        """初始化"""
        self.name = name
        self.params = params
        self._initialized = False
        self.logger = None 
        
    def set_logger(self, logger):
        """注入日志器"""
        self.logger = logger
        
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

    def warmup(self, data_list: List[MarketData]):
        """
        [标准接口] 批量预热数据。
        引擎在启动前会调用此方法，将历史 K 线批量喂给策略。
        子类应在此处更新指标、初始化状态，而不应依赖引擎去更新策略私有缓存。
        """
        for data in data_list:
            # 默认调用 initialize() 确保初始化
            if not self._initialized:
                self.initialize()
            # 默认调用上下文为空的 on_data（仅用于更新指标）
            # 注意：实际策略重写时应优化此处的计算开销
            self.on_data(data, None)

    def get_ui_manifest(self) -> Dict[str, Any]:
        """
        [预研接口] 返回策略所需的 UI 组件规格。
        多策略 Dashboard 将根据此配置动态渲染面板（如：神经网络热力图、特定技术指标）。
        """
        return {
            'charts': [
                {'type': 'candle_volume', 'name': '主图'},
                {'type': 'oscillator', 'name': 'RSI'}
            ]
        }
    
    def log(self, message: str, level: str = "info"):
        """标准日志接口"""
        if self.logger:
            if level == "info": self.logger.info(message)
            elif level == "error": self.logger.error(message)
            elif level == "warning": self.logger.warning(message)
        else:
            # 静默模式
            pass

    def to_dict(self) -> Dict[str, Any]:
        """导出配置"""
        return {
            "name": self.name,
            "class": self.__class__.__name__,
            "params": self.params
        }
