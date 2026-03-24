import time
from datetime import datetime
from typing import Iterator, Optional, List

from console.core import MarketData
from cartridges.datafeeds.base import BaseDataFeed
from console.utils.okx_api import OKXAPI

class OKXDataFeedSkill(BaseDataFeed):
    """
    OKX 实时数据流技能包封装
    """
    def __init__(self, **params):
        symbol = params.get('symbol', 'BTC-USDT')
        super().__init__([symbol])
        
        self.symbol = symbol
        self.timeframe = params.get('timeframe', '1m')
        self.poll_interval = params.get('poll_interval', 2.0)
        self.record_to = params.get('record_to')
        self._last_recorded_ts = None
        
        # API 初始化逻辑
        api_key = params.get('api_key')
        api_secret = params.get('api_secret')
        passphrase = params.get('passphrase')
        is_demo = params.get('is_demo', True)
        
        self.api = OKXAPI(
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            is_demo=is_demo
        )
        
        self._inst_id = self.symbol.replace('/', '-')
        self._bar_map = {
            '1m': '1m', '5m': '5m', '15m': '15m', 
            '1h': '1H', '4h': '4H', '1d': '1D'
        }
        self._running = False

    def stream(self, start: Optional[datetime] = None, end: Optional[datetime] = None) -> Iterator[MarketData]:
        self._running = True
        bar = self._bar_map.get(self.timeframe, '1m')
        
        print(f"\n[okx-feed] >>> 启动行情数据流: {self.symbol} ({self.timeframe}) <<<")
        print(f"[okx-feed] 轮询间隔: {self.poll_interval}s | 模拟盘: {self.api.is_demo}")
        print(f"[okx-feed] 正在等待第一根实时数据...\n", flush=True)
        
        while self._running:
            try:
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
                    
                    # 录入逻辑
                    if self.record_to and timestamp != self._last_recorded_ts:
                        self._record_data(data, timestamp)
                        
                    yield data
                
                time.sleep(self.poll_interval)
            except Exception as e:
                print(f"[okx-feed] 错误: {e}")
                time.sleep(5)

    def _record_data(self, data: MarketData, timestamp: datetime):
        import os
        try:
            if not os.path.exists(self.record_to):
                os.makedirs(os.path.dirname(self.record_to), exist_ok=True)
                with open(self.record_to, 'w') as f:
                    f.write("timestamp,open,high,low,close,volume\n")
            
            ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            with open(self.record_to, 'a') as f:
                f.write(f"{ts_str},{data.open},{data.high},{data.low},{data.close},{data.volume}\n")
            self._last_recorded_ts = timestamp
        except Exception as e:
            print(f"[okx-feed] 录制失败: {e}")

    def get_history(self, limit: int = 100) -> List[MarketData]:
        """抓取历史 K 线数据片段"""
        print(f"[okx-feed] 正在抓取历史数据: {self.symbol} {self.timeframe} (n={limit})...")
        bar = self._bar_map.get(self.timeframe, '1m')
        df = self.api.get_candles(self._inst_id, bar, limit=limit)
        
        history = []
        if df is not None:
            for ts, row in df.iterrows():
                history.append(MarketData(
                    timestamp=ts,
                    symbol=self.symbol,
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=float(row['volume'])
                ))
        return history

    def stop(self):
        self._running = False
