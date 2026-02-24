"""
数据接口基类
"""

from abc import ABC, abstractmethod
from typing import Iterator, List, Optional, Callable
from datetime import datetime

from core import MarketData


class BaseDataFeed(ABC):
    """
    数据接入基类
    
    职责：
    1. 提供市场数据流（历史或实时）
    2. 支持同步迭代和回调两种模式
    """
    
    def __init__(self, symbols: List[str]):
        self.symbols = symbols if isinstance(symbols, list) else [symbols]
        self._data_callbacks: List[Callable[[MarketData], None]] = []
        self._running = False
        
    def register_data_callback(self, callback: Callable[[MarketData], None]):
        """注册数据回调"""
        self._data_callbacks.append(callback)
    
    def _notify_data(self, data: MarketData):
        """通知所有监听者"""
        for callback in self._data_callbacks:
            callback(data)
    
    @abstractmethod
    def stream(self, start: Optional[datetime] = None, 
               end: Optional[datetime] = None) -> Iterator[MarketData]:
        """
        获取数据流
        
        Args:
            start: 开始时间（可选）
            end: 结束时间（可选）
            
        Yields:
            MarketData
        """
        pass
    
    def get_historical_data(self, start: datetime, end: datetime) -> List[MarketData]:
        """
        获取历史数据（默认实现通过stream）
        
        Args:
            start: 开始时间
            end: 结束时间
            
        Returns:
            List[MarketData]
        """
        return list(self.stream(start, end))
    
    def stop(self):
        """停止数据流"""
        self._running = False
