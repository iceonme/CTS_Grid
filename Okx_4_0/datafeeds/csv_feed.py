"""
CSV 历史数据接入
"""

import pandas as pd
from datetime import datetime
from typing import Iterator, Optional

from core import MarketData
from .base import BaseDataFeed


class CSVDataFeed(BaseDataFeed):
    """
    从 CSV 文件读取历史数据
    
    CSV 格式要求:
    timestamp,open,high,low,close,volume
    2024-01-01 00:00:00,42500,42600,42400,42550,100.5
    """
    
    def __init__(self, 
                 filepath: str,
                 symbol: str = "BTC-USDT",
                 timestamp_col: str = "timestamp",
                 timestamp_format: Optional[str] = None):
        """
        Args:
            filepath: CSV 文件路径
            symbol: 交易对名称
            timestamp_col: 时间戳列名
            timestamp_format: 时间格式（可选）
        """
        super().__init__([symbol])
        self.filepath = filepath
        self.symbol = symbol
        self.timestamp_col = timestamp_col
        self.timestamp_format = timestamp_format
        self._data: Optional[pd.DataFrame] = None
        
    def _load_data(self):
        """加载数据"""
        if self._data is not None:
            return
            
        df = pd.read_csv(self.filepath)
        
        # 解析时间戳
        if self.timestamp_col in df.columns:
            if self.timestamp_format:
                df[self.timestamp_col] = pd.to_datetime(df[self.timestamp_col], 
                                                         format=self.timestamp_format)
            else:
                df[self.timestamp_col] = pd.to_datetime(df[self.timestamp_col])
            df.set_index(self.timestamp_col, inplace=True)
        
        # 确保列名小写
        df.columns = [c.lower() for c in df.columns]
        
        self._data = df.sort_index()
        
    def stream(self, 
               start: Optional[datetime] = None,
               end: Optional[datetime] = None) -> Iterator[MarketData]:
        """
        数据流
        
        Args:
            start: 开始时间
            end: 结束时间
        """
        self._load_data()
        
        df = self._data
        
        if start:
            df = df[df.index >= start]
        if end:
            df = df[df.index <= end]
        
        self._running = True
        
        for timestamp, row in df.iterrows():
            if not self._running:
                break
                
            data = MarketData.from_series(
                timestamp=timestamp,
                symbol=self.symbol,
                row=row
            )
            
            self._notify_data(data)
            yield data
