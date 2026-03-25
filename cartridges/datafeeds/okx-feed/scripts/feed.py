import time
from datetime import datetime
from typing import Iterator, Optional, List, AsyncIterator
import asyncio

from console.core import MarketData, Position
from cartridges.datafeeds.base import BaseDataFeed
from console.utils.okx_api import OKXAPI

from console.protocol import MarketUpdateEvent, HistoryRequestEvent, MarketHistoryEvent

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

    def on_init(self):
        """挂载总线连接"""
        self.subscribe("history_request", self._on_history_request)

    async def _on_history_request(self, event: HistoryRequestEvent):
        """响应历史补全请求 (支持驱动预热)"""
        if event.symbol == self.symbol:
            history = self.get_history(limit=event.limit)
            if history and self.bus:
                # 一次性批量推送，不触发交易逻辑，仅填充缓存
                await self.bus.emit("market_history_update", MarketHistoryEvent(
                    symbol=self.symbol,
                    data=history
                ))

    async def stream(self, start: Optional[datetime] = None, end: Optional[datetime] = None):
        self._running = True
        bar = self._bar_map.get(self.timeframe, '1m')
        
        print(f"\n[okx-feed] >>> 启动行情数据流: {self.symbol} ({self.timeframe}) <<<", flush=True)
        print(f"[okx-feed] 轮询间隔: {self.poll_interval}s | 模拟盘: {self.api.is_demo}", flush=True)
        print(f"[okx-feed] 正在进入主循环...", flush=True)
        
        while self._running:
            try:
                df = await asyncio.to_thread(self.api.get_candles, self._inst_id, bar, limit=10)
                if df is not None and not df.empty:
                    # print(f"[okx-feed] DEBUG: 获取到数据: {len(df)} 条")
                    current = df.iloc[-1]
                    timestamp = df.index[-1]
                    
                    data = MarketData(
                        timestamp=int(timestamp.timestamp()),
                        symbol=self.symbol,
                        open=float(current['open']),
                        high=float(current['high']),
                        low=float(current['low']),
                        close=float(current['close']),
                        volume=float(current['vol'])
                    )
                    
                    # self._notify_data(data) # 移除未定义的调用
                    
                    # 录入逻辑
                    if self.record_to and timestamp != self._last_recorded_ts:
                        self._record_data(data, timestamp)
                    yield data
                else:
                    pass
                
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                print(f"[okx-feed] 错误: {e}")
                await asyncio.sleep(5)

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

    def get_account_data(self) -> dict:
        """获取账户余额与持仓"""
        try:
            # 1. 获取余额 (USDT)
            cash = self.api.get_balance("USDT")
            
            # 2. 获取持仓
            okx_positions = self.api.get_positions(instType="SWAP")
            positions = {}
            total_unrealized_pnl = 0.0
            
            for p in okx_positions:
                symbol = p['instId'].replace('-', '/')
                size = float(p['pos'])
                if size == 0: continue
                
                # 统一为多头正数/空头负数逻辑 (OKX posSide="long"/"short")
                if p['posSide'] == 'short':
                    size = -abs(size)
                
                upnl = float(p['upl'])
                total_unrealized_pnl += upnl
                
                positions[symbol] = Position(
                    symbol=symbol,
                    size=size,
                    avg_price=float(p['avgPx']),
                    entry_time=datetime.fromtimestamp(int(p['uTime'])/1000),
                    unrealized_pnl=upnl
                )
            
            return {
                'cash': cash,
                'positions': positions,
                'total_value': cash + total_unrealized_pnl # 简化计算
            }
        except Exception as e:
            print(f"[okx-feed] 获取账户数据失败: {e}")
            return {'cash': 0.0, 'positions': {}, 'total_value': 0.0}

    def get_history(self, limit: int = 100) -> List[MarketData]:
        """抓取历史 K 线数据碎片并拼装 (支持跨页抓取)"""
        print(f"[okx-feed] 正在启动分页抓取: {self.symbol} {self.timeframe} (目标总量 n={limit})...")
        bar_type = self._bar_map.get(self.timeframe, '1m')
        
        all_history = []
        after_ts = None
        
        while len(all_history) < limit:
            to_fetch = min(300, limit - len(all_history))
            # 抓取当前段
            df = self.api.get_candles(self._inst_id, bar_type, limit=to_fetch, after=after_ts)
            
            if df is None or df.empty:
                break
            
            # 将当前段转换为 MarketData 列表
            current_page = []
            for ts, row in df.iterrows():
                # 转换 ts 为 Unix 秒级整数
                ts_int = int(ts.timestamp()) if hasattr(ts, 'timestamp') else int(ts)
                current_page.append(MarketData(
                    timestamp=ts_int,
                    symbol=self.symbol,
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=float(row['vol'])
                ))
            
            # 拼接到整体历史中 (OKX 返回由新到旧排序，底层 API sort_index 后为由旧到新)
            # 我们需要确保 all_history 是由旧到新的顺序存储
            all_history = current_page + all_history
            
            # 准备下一页：取当前页最早一根的时间戳 (ms)
            after_ts = int(df.index[0].timestamp() * 1000)
            
            # 如果单次抓取量少于请求量，说明已经到底了
            if len(df) < to_fetch:
                break
        
        print(f"[okx-feed] 分页抓取完成，共获取 {len(all_history)} 根 K 线")
        return all_history

    async def stop(self):
        self._running = False
