"""
CSV 鍘嗗彶鏁版嵁鎺ュ叆
"""

import pandas as pd
from datetime import datetime
from typing import Iterator, Optional

from console.core import MarketData
from .base import BaseDataFeed


class CSVDataFeed(BaseDataFeed):
    """
    浠?CSV 鏂囦欢璇诲彇鍘嗗彶鏁版嵁
    
    CSV 鏍煎紡瑕佹眰:
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
            filepath: CSV 鏂囦欢璺緞
            symbol: 浜ゆ槗瀵瑰悕绉?
            timestamp_col: 鏃堕棿鎴冲垪鍚?
            timestamp_format: 鏃堕棿鏍煎紡锛堝彲閫夛級
        """
        super().__init__([symbol])
        self.filepath = filepath
        self.symbol = symbol
        self.timestamp_col = timestamp_col
        self.timestamp_format = timestamp_format
        self._data: Optional[pd.DataFrame] = None
        
    def _load_data(self):
        """鍔犺浇鏁版嵁"""
        if self._data is not None:
            return
            
        # 閽堝 2025 瀵煎嚭鐨勬牸寮忚繘琛屼紭鍖?
        df = pd.read_csv(self.filepath)
        
        # 瑙ｆ瀽鏃堕棿鎴?- 濡傛灉宸茬粡鏄暣鏁?ms锛岀洿鎺ヨ浆鎹㈡晥鐜囨洿楂?
        if self.timestamp_col in df.columns:
            if df[self.timestamp_col].dtype in ['int64', 'float64']:
                df[self.timestamp_col] = pd.to_datetime(df[self.timestamp_col], unit='ms')
            else:
                df[self.timestamp_col] = pd.to_datetime(df[self.timestamp_col])
            df.set_index(self.timestamp_col, inplace=True)
        
        # 纭繚鍒楀悕灏忓啓
        df.columns = [c.lower() for c in df.columns]
        
        self._data = df.sort_index()
        
    def stream(self, 
               start: Optional[datetime] = None,
               end: Optional[datetime] = None) -> Iterator[MarketData]:
        """
        楂橀€熸暟鎹祦
        """
        self._load_data()
        df = self._data
        
        if start:
            df = df[df.index >= start]
        if end:
            df = df[df.index <= end]
        
        self._running = True
        
        # 棰勫厛杞崲涓?dict 鍒楄〃鍙互鏄捐憲鎻愬崌澶у瀷寰幆閫熷害
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
            
            # 鍥炴祴妯″紡涓嬪噺灏戝洖璋冮€氱煡浠ユ彁楂橀€熷害
            # self._notify_data(data) 
            yield data
