"""
瀹炵洏寮曟搸
杩炴帴鐪熷疄浜ゆ槗鎵€杩愯绛栫暐
"""

import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any

from console.core import (
    MarketData, Signal, Order, FillEvent, Position,
    StrategyContext, PortfolioSnapshot, OrderStatus
)
from cartridges.strategies import BaseStrategy
from cartridges.bridge.executors import BaseExecutor
from cartridges.bridge.datafeeds import BaseDataFeed


class LiveEngine:
    """
    瀹炵洏/妯℃嫙鐩樺紩鎿?
    
    鑱岃矗锛?
    1. 鎺ユ敹瀹炴椂鏁版嵁
    2. 椹卞姩绛栫暐杩愯
    3. 鎵ц淇″彿
    4. 缁存姢鐘舵€佸悓姝?
    
    涓庡洖娴嬪紩鎿庣殑鍖哄埆锛?
    - 鏁版嵁鏄寔缁殑銆佸疄鏃剁殑
    - 鏀寔鎵嬪姩鍋滄/鍚姩
    - 鏀寔鐘舵€佺洃鎺у洖璋冿紙鐢ㄤ簬Dashboard锛?
    """
    
    def __init__(self,
                 strategy: BaseStrategy,
                 executor: BaseExecutor,
                 data_feed: BaseDataFeed,
                 warmup_bars: int = 100):
        """
        Args:
            strategy: 绛栫暐瀹炰緥
            executor: 鎵ц鍣紙PaperExecutor 鎴?OKXExecutor锛?
            data_feed: 鏁版嵁娴?
            warmup_bars: 棰勭儹鎵€闇€鐨勫巻鍙叉暟鎹潯鏁?
        """
        self.strategy = strategy
        self.executor = executor
        self.data_feed = data_feed
        self.warmup_bars = warmup_bars
        
        # 鐘舵€?
        self.is_running = False
        self._is_warmed = False
        self._current_time: Optional[datetime] = None
        self._current_prices: Dict[str, float] = {}
        self._equity_curve: List[PortfolioSnapshot] = []
        self._trades: List[Dict] = []
        
        # 鍥捐〃鍘嗗彶鏁版嵁鍚屾
        self._history_candles: List[Dict] = []
        self._history_rsi: List[Dict] = []
        self._history_macd: List[Dict] = []
        
        # 鐩戞帶鍥炶皟
        self._status_callbacks: List[Callable[[Dict], None]] = []
        
        # 娉ㄥ唽鍥炶皟
        self.executor.register_fill_callback(self._on_fill)
        self.data_feed.register_data_callback(self._on_data)
    
    def register_status_callback(self, callback: Callable[[Dict], None]):
        """娉ㄥ唽鐘舵€佺洃鎺у洖璋冿紙鐢ㄤ簬Dashboard锛?""
        self._status_callbacks.append(callback)
    
    def _get_context(self) -> StrategyContext:
        """鏋勫缓绛栫暐涓婁笅鏂?""
        positions = {}
        for pos in self.executor.get_all_positions():
            # 瀹炴椂璁＄畻娴姩鐩堜簭
            if pos.symbol in self._current_prices:
                pos.unrealized_pnl = (self._current_prices[pos.symbol] - pos.avg_price) * pos.size
            positions[pos.symbol] = pos
        
        return StrategyContext(
            timestamp=self._current_time,
            cash=self.executor.get_cash(),
            positions=positions,
            current_prices=self._current_prices.copy()
        )
    
    def _on_fill(self, fill: FillEvent):
        """鎴愪氦鍥炶皟"""
        # 閫氱煡绛栫暐
        self.strategy.on_fill(fill)
        
        # 鏋勫缓浜ゆ槗璁板綍璇︽儏
        side = fill.side.value.upper()
        symbol = fill.symbol
        price = fill.filled_price
        size = fill.filled_size
        quote_amount = fill.quote_amount
        
        # 鏍煎紡鍖栨樉绀轰俊鎭?
        if side == 'BUY' and quote_amount:
            # 涔板叆锛氭樉绀鸿姳璐逛簡澶氬皯USDT锛屼拱浜嗗灏態TC
            detail = f"鑺辫垂 {quote_amount:.2f} USDT 涔板叆 {size:.6f} BTC"
        elif side == 'SELL' and quote_amount:
            # 鍗栧嚭锛氭樉绀哄崠鍑轰簡澶氬皯BTC锛岃幏寰椾簡澶氬皯USDT
            detail = f"鍗栧嚭 {size:.6f} BTC 鑾峰緱 {quote_amount:.2f} USDT"
        else:
            detail = f"鏁伴噺={size:.6f} 浠锋牸={price:.2f}"
        
        # 璁板綍浜ゆ槗
        trade_record = {
            'type': side,
            'symbol': symbol,
            'price': price,
            'size': size,
            'quote_amount': quote_amount,
            'pnl': fill.pnl,
            'time': fill.timestamp.isoformat(),
            'detail': detail
        }
        self._trades.append(trade_record)
        
        print(f"[鎴愪氦] {side} {symbol} | {detail} | 浠锋牸=${price:.2f}")
    
    def _on_data(self, data: MarketData):
        """鏁版嵁鍥炶皟锛堢敤浜庨鐑級"""
        pass
    
    def _execute_signals(self, signals: List[Signal]):
        """鎵ц淇″彿"""
        for signal in signals:
            order = Order(
                order_id="",
                symbol=signal.symbol,
                side=signal.side,
                size=signal.size,
                order_type=signal.order_type,
                price=signal.price,
                timestamp=signal.timestamp,
                meta=signal.meta
            )
            order_id = self.executor.submit_order(order)
            if not order_id or order.status == OrderStatus.REJECTED:
                reason = order.meta.get('reject_reason', 'submit_failed_or_rejected')
                print(
                    f"[鎵ц鎷掑崟] symbol={order.symbol} side={order.side.value} "
                    f"size={order.size} reason={reason}"
                )
    
    def _notify_status(self, data: Dict):
        """閫氱煡鐩戞帶鍣?""
        for callback in self._status_callbacks:
            try:
                callback(data)
            except Exception as e:
                print(f"鐘舵€佸洖璋冮敊璇? {e}")
    
    def warmup(self):
        """
        棰勭儹锛氳幏鍙栧巻鍙叉暟鎹垵濮嬪寲绛栫暐
        鍦?run() 涔嬪墠璋冪敤
        """
        # 姣忔棰勭儹鍓嶅厛閲嶇疆绛栫暐锛岄伩鍏嶅巻鍙茬紦瀛樹笌鏃х姸鎬佹贩鏉?
        self.strategy.initialize()

        print(f"姝ｅ湪棰勭儹绛栫暐锛岃幏鍙?{self.warmup_bars} 鏉″巻鍙叉暟鎹?..")
        
        # 浠嶢PI鑾峰彇鍘嗗彶鏁版嵁棰勭儹
        try:
            # 灏濊瘯浠庢暟鎹祦鐨凙PI鑾峰彇鍘嗗彶鏁版嵁
            if hasattr(self.data_feed, 'api'):
                df = self.data_feed.api.get_candles(
                    self.data_feed._inst_id, 
                    self.data_feed._bar_map.get(self.data_feed.timeframe, '1m'), 
                    limit=self.warmup_bars
                )
                
                if df is not None and len(df) > 0:
                    print(f"  鎴愬姛鑾峰彇 {len(df)} 鏉″巻鍙叉暟鎹?)
                    
                    # 鏋勫缓鏍囧噯鏁版嵁鍒楄〃骞堕鐑?
                    data_list = []
                    for timestamp, row in df.iterrows():
                        from console.core import MarketData
                        data = MarketData(
                            timestamp=timestamp,
                            symbol=self.data_feed.symbol,
                            open=float(row['open']),
                            high=float(row['high']),
                            low=float(row['low']),
                            close=float(row['close']),
                            volume=float(row['volume'])
                        )
                        data_list.append(data)
                        self._current_prices[data.symbol] = data.close
                    
                    # 1. 璋冪敤鏍囧噯鍖栭鐑帴鍙?(Runner 2.0 濂戠害)
                    self.strategy.warmup(data_list)
                    print(f"  绛栫暐棰勭儹涓庢牳蹇冪姸鎬佸垵濮嬪寲瀹屾垚")
                else:
                    print("  璀﹀憡: 鏈兘鑾峰彇鍘嗗彶鏁版嵁锛屽皢浣跨敤瀹炴椂鏁版嵁鍒濆鍖?)
            else:
                print("  鏁版嵁娴佷笉鏀寔API鎺ュ彛锛屽皢浣跨敤瀹炴椂鏁版嵁鍒濆鍖?)
                
        except Exception as e:
            print(f"  棰勭儹杩囩▼鍑洪敊: {e}")
            import traceback
            traceback.print_exc()
        
        if self.warmup_bars > 0 and len(self.strategy._data_1m) == 0:
            print("  閿欒: 棰勭儹鏈垚鍔燂紝鏈兘濉厖鍘嗗彶鏁版嵁")
            return False
            
        self._is_warmed = True
        print("棰刜鐑畬鎴?)
        return True
    
    def run(self):
        """鍚姩寮曟搸"""
        if not self._is_warmed and not self.warmup():
            print("棰勭儹澶辫触锛屾棤娉曞惎鍔?)
            return
        
        self.is_running = True
        self.strategy.on_start()
        
        print(f"\n{'='*60}")
        print(f"瀹炵洏寮曟搸鍚姩 | 绛栫暐: {self.strategy.name}")
        print(f"{'='*60}\n")
        
        try:
            data_count = 0
            for data in self.data_feed.stream():
                if not self.is_running:
                    break
                
                # 閲嶆柊棰勭儹妫€娴嬶紙鏀寔杩愯涓噸缃級
                if not self._is_warmed:
                    print("[寮曟搸] 鎺ユ敹鍒伴噸缃俊鍙凤紝閲嶆柊寮€濮嬮鐑?..")
                    self.warmup()
                    data_count = 0
                    # 鍙戦€佺┖鐘舵€佺粰鐩戞帶鍣?
                    # self._notify_status(self._build_status(data))
                    continue
                
                data_count += 1
                self._current_time = data.timestamp
                self._current_prices[data.symbol] = data.close
                
                # 鏇存柊鎵ц鍣ㄥ苟鍚屾鍥捐〃鍘嗗彶
                self.executor.update_market_data(data.timestamp, data.close)
                self._sync_history_candles(data)
                
                # 绛栫暐鍐崇瓥
                context = self._get_context()
                signals = self.strategy.on_data(data, context)
                
                # 鎵ц
                if signals:
                    print(f"[寮曟搸] 鐢熸垚 {len(signals)} 涓俊鍙?)
                    for sig in signals:
                        if sig.side.value == 'buy':
                            print(f"[DEBUG BUY] price={data.close:.2f} size={sig.size:.4f} reason={sig.reason} "
                                  f"rsi={self.strategy.state.current_rsi:.1f} layers={self._estimate_layers()}")
                    self._execute_signals(signals)
                
                # 鍙戦€佺姸鎬佹洿鏂?
                status = self._build_status(data)
                self._notify_status(status)
                
                # 姣?5 鏉℃暟鎹墦鍗颁竴娆℃棩蹇?
                if data_count % 5 == 0:
                    print(f"[寮曟搸] 宸插鐞?{data_count} 鏉℃暟鎹?| 浠锋牸: {data.close:.2f} | 鎸佷粨: {len(status['positions'])}灞?)
                
        except KeyboardInterrupt:
            print("\n鏀跺埌鍋滄淇″彿...")
        except Exception as e:
            print(f"寮曟搸閿欒: {e}")
        finally:
            self.stop()
    
    def _estimate_layers(self) -> int:
        """浼扮畻褰撳墠鎸佷粨灞傛暟"""
        try:
            positions = self.executor.get_all_positions()
            cash = self.executor.get_cash()
            total = cash + sum(p.size * self._current_prices.get(p.symbol, 0) for p in positions)
            if total <= 0:
                return 0
            for pos in positions:
                if pos.symbol == self.strategy.symbol:
                    base = max(total * self.strategy.params['base_position_pct'], self.strategy.params['min_order_usdt'])
                    return max(1, int(__import__('numpy').ceil(pos.size * self._current_prices.get(pos.symbol, 0) / base)))
        except Exception:
            pass
        return 0
    
    def _build_status(self, data: MarketData) -> Dict:
        """鏋勫缓鐘舵€佷俊鎭?""
        positions = self.executor.get_all_positions()
        cash = self.executor.get_cash()
        if hasattr(self.executor, 'get_total_value'):
            total_value = self.executor.get_total_value()
            position_value = total_value - cash
        else:
            position_value = sum(
                pos.size * self._current_prices.get(pos.symbol, 0)
                for pos in positions
            )
            total_value = cash + position_value
        
        # 鑾峰彇绛栫暐鐘舵€?
        context = self._get_context()
        strategy_status = self.strategy.get_status(context)
        
        # 璁＄畻鐩堜簭姣?
        initial_balance = getattr(self.executor, 'initial_capital', 10000.0)
        pnl_pct = (total_value - initial_balance) / initial_balance * 100
        
        # 杩斿洖鎵€鏈変氦鏄撹褰曪紙鍒嗛〉鐢卞墠绔鐞嗭級
        trade_history = self._trades

        # 鍚屾瀹炴椂鐨?RSI 鍜?MACD 鍥捐〃杞ㄨ抗
        timestamp_ms = int(data.timestamp.timestamp() * 1000)
        
        # 鍚屾澧為噺 RSI
        rsi_val = strategy_status.get('current_rsi', 50.0)
        if hasattr(self, '_history_rsi'):
            # 瑙ｅ喅鍚屼竴鏍筀绾挎椂闂存埑鍘婚噸闂
            if not self._history_rsi or self._history_rsi[-1]['time'] < timestamp_ms:
                self._history_rsi.append({'time': timestamp_ms, 'value': rsi_val})
            else:
                self._history_rsi[-1] = {'time': timestamp_ms, 'value': rsi_val}
            if len(self._history_rsi) > 3000: self._history_rsi = self._history_rsi[-3000:]
            
        # 鍚屾澧為噺 MACD
        m_val = strategy_status.get('macd')
        if m_val is not None and hasattr(self, '_history_macd'):
            macd_data = {
                'time': timestamp_ms,
                'macd': m_val,
                'macdsignal': strategy_status.get('macdsignal', 0.0),
                'macdhist': strategy_status.get('macdhist', 0.0)
            }
            if not self._history_macd or self._history_macd[-1]['time'] < timestamp_ms:
                self._history_macd.append(macd_data)
            else:
                self._history_macd[-1] = macd_data
            if len(self._history_macd) > 3000: self._history_macd = self._history_macd[-3000:]
            
        # 鍚屾鍘嗗彶璧勪骇鏇茬嚎
        if not hasattr(self, '_history_equity'):
            self._history_equity = []
        if not self._history_equity or self._history_equity[-1]['time'] < timestamp_ms:
            self._history_equity.append({'time': timestamp_ms, 'value': total_value})
        else:
            self._history_equity[-1] = {'time': timestamp_ms, 'value': total_value}
        if len(self._history_equity) > 3000: self._history_equity = self._history_equity[-3000:]

        return {
            'timestamp': data.timestamp.isoformat(),
            'symbol': data.symbol,
            'price': data.close,
            'open': data.open,
            'high': data.high,
            'low': data.low,
            # 鍓嶇鍥捐〃鏍稿績锛欿绾垮璞?
            'candle': {
                't': timestamp_ms,
                'o': data.open,
                'h': data.high,
                'l': data.low,
                'c': data.close,
                'v': data.volume
            },
            'cash': cash,
            'position_value': position_value,
            'total_value': total_value,
            'initial_balance': initial_balance,
            'pnl_pct': pnl_pct,
            'rsi': rsi_val,
            'strategy': strategy_status,
            'positions': {
                p.symbol: {
                    'size': p.size,
                    'avg_price': p.avg_price,
                    'unrealized_pnl': (data.close - p.avg_price) * p.size if p.symbol == data.symbol else 0.0
                } for p in positions
            },
            'trade_history': trade_history, # 缁熶竴瀛楁鍚嶄负 trade_history
            'history_candles': self._history_candles[-3000:],  # 鍚屾鍘嗗彶K绾挎暟鎹?
            'history_rsi': self._history_rsi[-3000:] if hasattr(self, '_history_rsi') else [],
            'history_macd': self._history_macd[-3000:] if hasattr(self, '_history_macd') else [],
            'history_equity': self._history_equity[-3000:] if hasattr(self, '_history_equity') else []
        }
    
    def _sync_history_candles(self, data: MarketData):
        """鍚屾鍘嗗彶K绾挎暟鎹埌鍥捐〃"""
        candle = {
            't': int(data.timestamp.timestamp() * 1000),
            'o': data.open,
            'h': data.high,
            'l': data.low,
            'c': data.close
        }
        # 鍘婚噸锛氭鏌ユ槸鍚﹀凡瀛樺湪鐩稿悓鏃堕棿鎴?
        if self._history_candles and self._history_candles[-1]['t'] == candle['t']:
            self._history_candles[-1] = candle  # 鏇存柊褰撳墠K绾?
        else:
            self._history_candles.append(candle)
        # 闄愬埗鍘嗗彶鏁版嵁澶у皬
        if len(self._history_candles) > 3000:
            self._history_candles = self._history_candles[-3000:]

    def save_trades(self, filepath: str):
        """淇濆瓨浜ゆ槗璁板綍"""
        import json
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self._trades, f, indent=4)
        except Exception as e:
            print(f"[寮曟搸] 淇濆瓨浜ゆ槗璁板綍澶辫触: {e}")

    def load_trades(self, filepath: str):
        """鍔犺浇浜ゆ槗璁板綍"""
        import json
        import os
        if not os.path.exists(filepath):
            return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self._trades = json.load(f)
            print(f"[寮曟搸] 宸蹭粠 {filepath} 鍔犺浇 {len(self._trades)} 鏉′氦鏄撹褰?)
        except Exception as e:
            print(f"[寮曟搸] 鍔犺浇浜ゆ槗璁板綍澶辫触: {e}")

    def stop(self):
        """鍋滄寮曟搸"""
        self.is_running = False
        self._is_warmed = False
        self.strategy.on_stop()
        self.data_feed.stop()
        print("\n寮曟搸宸插仠姝?)
