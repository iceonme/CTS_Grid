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
            
        # 针对 2025 导出的格式进行优化
        df = pd.read_csv(self.filepath)
        
        # 解析时间戳 - 如果已经是整数 ms，直接转换效率更高
        if self.timestamp_col in df.columns:
            if df[self.timestamp_col].dtype in ['int64', 'float64']:
                df[self.timestamp_col] = pd.to_datetime(df[self.timestamp_col], unit='ms')
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
        高速数据流
        """
        self._load_data()
        df = self._data
        
        if start:
            df = df[df.index >= start]
        if end:
            df = df[df.index <= end]
        
        self._running = True
        
        # 预先转换为 dict 列表可以显著提升大型循环速度
        records = df.to_dict('records')
        timestamps = df.index.tolist()
        
        for i in range(len(records)):
            if not self._running:
                break
            
            data = MarketData(
                timestamp=timestamps[i],
                symbol=self.symbol,
                open=float(records[i]['open']),
                high=float(records[i]['high']),
                low=float(records[i]['low']),
                close=float(records[i]['close']),
                volume=float(records[i]['volume'])
            )
            
            # 回测模式下减少回调通知以提高速度
            # self._notify_data(data) 
            yield data
