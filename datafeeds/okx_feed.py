"""
OKX 实时数据接入
"""

import time
from datetime import datetime
from typing import Iterator, Optional

from core import MarketData
from .base import BaseDataFeed
from config.okx_config import OKXAPI


class OKXDataFeed(BaseDataFeed):
    """
    OKX 实时数据流（轮询模式）
    """
    
    def __init__(self, 
                 symbol: str = "BTC-USDT",
                 timeframe: str = "1m",
                 api: Optional[OKXAPI] = None,
                 api_key: Optional[str] = None,
                 api_secret: Optional[str] = None,
                 passphrase: Optional[str] = None,
                 is_demo: bool = True,
                 poll_interval: float = 2.0,
                 record_to: Optional[str] = None):
        """
        Args:
            symbol: 交易对
            timeframe: 时间周期
            api: 已有的 API 实例
            api_key: API Key（用于创建新实例）
            api_secret: API Secret
            passphrase: Passphrase
            is_demo: 是否模拟盘
            poll_interval: 轮询间隔（秒）
        """
        super().__init__([symbol])
        self.symbol = symbol
        self.timeframe = timeframe
        self.poll_interval = poll_interval
        self.record_to = record_to
        self._last_recorded_ts = None
        
        if api:
            self.api = api
        else:
            self.api = OKXAPI(
                api_key=api_key,
                api_secret=api_secret,
                passphrase=passphrase,
                is_demo=is_demo
            )
        
        self._inst_id = symbol.replace('/', '-')
        self._bar_map = {'1m': '1m', '5m': '5m', '15m': '15m', 
                         '1h': '1H', '4h': '4H', '1d': '1D'}
        
    def stream(self,
               start: Optional[datetime] = None,
               end: Optional[datetime] = None) -> Iterator[MarketData]:
        """
        实时数据流（轮询模式）
        
        注意：start/end 参数在此模式中忽略
        """
        self._running = True
        bar = self._bar_map.get(self.timeframe, '1m')
        
        print(f"启动 OKX 数据流: {self.symbol} {self.timeframe}")
        
        # 初始化录制文件
        if self.record_to:
            import os
            try:
                record_path = os.path.abspath(self.record_to)
                os.makedirs(os.path.dirname(record_path), exist_ok=True)
                if not os.path.exists(record_path):
                    with open(record_path, 'w', encoding='utf-8') as f:
                        f.write("timestamp,open,high,low,close,volume\n")
                    print(f"[DataFeed] 行情录制已开启: {record_path}")
                else:
                    print(f"[DataFeed] 行情录制将追加至: {record_path}")
            except Exception as e:
                print(f"[DataFeed] 初始化录制文件失败: {e}")

        while self._running:
            try:
                # 获取最近 2 根 K 线
                df = self.api.get_candles(self._inst_id, bar, limit=2)
                
                if df is not None and len(df) > 0:
                    current = df.iloc[-1]
                    timestamp = df.index[-1]
                    
                    data = MarketData(
                        timestamp=timestamp,
                        symbol=self.symbol,
                        open=float(current['open']),
                        high=float(current['high']),
                        low=float(current['low']),
                        close=float(current['close']),
                        volume=float(current['volume'])
                    )
                    
                    self._notify_data(data)
                    
                    # 录制逻辑 (去重并追加)
                    if self.record_to and timestamp != self._last_recorded_ts:
                        try:
                            ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                            with open(self.record_to, 'a', encoding='utf-8') as f:
                                f.write(f"{ts_str},{data.open},{data.high},{data.low},{data.close},{data.volume}\n")
                            self._last_recorded_ts = timestamp
                        except Exception as e:
                            print(f"[DataFeed] 记录行情失败: {e}")

                    yield data
                
                time.sleep(self.poll_interval)
                
            except Exception as e:
                print(f"数据流错误: {e}")
                time.sleep(5)
