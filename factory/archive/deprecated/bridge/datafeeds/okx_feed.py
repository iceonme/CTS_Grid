"""
OKX 瀹炴椂鏁版嵁鎺ュ叆
"""

import time
from datetime import datetime
from typing import Iterator, Optional

from console.core import MarketData
from .base import BaseDataFeed
from infra.config.okx_config import OKXAPI


class OKXDataFeed(BaseDataFeed):
    """
    OKX 瀹炴椂鏁版嵁娴侊紙杞妯″紡锛?
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
            symbol: 浜ゆ槗瀵?
            timeframe: 鏃堕棿鍛ㄦ湡
            api: 宸叉湁鐨?API 瀹炰緥
            api_key: API Key锛堢敤浜庡垱寤烘柊瀹炰緥锛?
            api_secret: API Secret
            passphrase: Passphrase
            is_demo: 鏄惁妯℃嫙鐩?
            poll_interval: 杞闂撮殧锛堢锛?
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
        瀹炴椂鏁版嵁娴侊紙杞妯″紡锛?
        
        娉ㄦ剰锛歴tart/end 鍙傛暟鍦ㄦ妯″紡涓拷鐣?
        """
        self._running = True
        bar = self._bar_map.get(self.timeframe, '1m')
        
        print(f"鍚姩 OKX 鏁版嵁娴? {self.symbol} {self.timeframe}")
        
        # 鍒濆鍖栧綍鍒舵枃浠?
        if self.record_to:
            import os
            try:
                record_path = os.path.abspath(self.record_to)
                os.makedirs(os.path.dirname(record_path), exist_ok=True)
                if not os.path.exists(record_path):
                    with open(record_path, 'w', encoding='utf-8') as f:
                        f.write("timestamp,open,high,low,close,volume\n")
                    print(f"[DataFeed] 琛屾儏褰曞埗宸插紑鍚? {record_path}")
                else:
                    print(f"[DataFeed] 琛屾儏褰曞埗灏嗚拷鍔犺嚦: {record_path}")
            except Exception as e:
                print(f"[DataFeed] 鍒濆鍖栧綍鍒舵枃浠跺け璐? {e}")

        while self._running:
            try:
                # 鑾峰彇鏈€杩?2 鏍?K 绾?
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
                    
                    # 褰曞埗閫昏緫 (鍘婚噸骞惰拷鍔?
                    if self.record_to and timestamp != self._last_recorded_ts:
                        try:
                            ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                            with open(self.record_to, 'a', encoding='utf-8') as f:
                                f.write(f"{ts_str},{data.open},{data.high},{data.low},{data.close},{data.volume}\n")
                            self._last_recorded_ts = timestamp
                        except Exception as e:
                            print(f"[DataFeed] 璁板綍琛屾儏澶辫触: {e}")

                    yield data
                
                time.sleep(self.poll_interval)
                
            except Exception as e:
                print(f"鏁版嵁娴侀敊璇? {e}")
                time.sleep(5)
