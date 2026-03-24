"""
实盘引擎 (ETH Swap 适配版)
"""
import time
import threading
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable, Any

from core import (
    MarketData, Signal, Order, FillEvent, Position,
    StrategyContext, PortfolioSnapshot, OrderStatus
)
from strategies import BaseStrategy
from executors import BaseExecutor
from datafeeds import BaseDataFeed

class LiveEngine:
    def __init__(self,
                 strategy: BaseStrategy,
                 executor: BaseExecutor,
                 data_feed: BaseDataFeed,
                 warmup_bars: int = 100):
        self.strategy = strategy
        self.executor = executor
        self.data_feed = data_feed
        self.warmup_bars = warmup_bars
        
        self.is_running = False
        self._is_warmed = False
        self._current_time: Optional[datetime] = None
        self._current_prices: Dict[str, float] = {}
        self._equity_curve: List[PortfolioSnapshot] = []
        self._trades: List[Dict] = []
        self._history_candles: List[Dict] = []
        self._status_callbacks: List[Callable[[Dict], None]] = []
        self._history_sent = False # 记录历史数据是否已同步通过
        self._history_equity: List[Dict] = [] # 记录资产历史
        self._history_rsi: List[float] = []   # 记录 RSI 历史 (对齐用)
        self._latest_trade: Optional[Dict] = None # 最近一条记录
        self._should_restart = False # 是否需要重启
        self._pending_intents: Dict[str, Dict] = {} # 意图缓存 clOrdId -> {reason, meta}
        # 资产统计
        self.initial_total_value: Optional[float] = None
        
        # 交易持久化
        self.trades_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "v93_trades.json")
        self.initial_balance_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "v93_initial_balance.json")
        self._load_trades()
        self._load_initial_balance()   # 从文件或调试日志恢复初始资金
        self._sync_exchange_orders()   # 同步委托单历史 (替代之前的成交明细同步)
        # 注意：此处不再调用 _sync_equity_history，改为在 warmup 之后调用，以利用已载入的 K 线对齐
        
        self.executor.register_fill_callback(self._on_fill)
        self.data_feed.register_data_callback(self._on_data)
    
    def _load_trades(self):
        """从文件加载交易记录"""
        try:
            if os.path.exists(self.trades_file):
                with open(self.trades_file, 'r', encoding='utf-8') as f:
                    self._trades = json.load(f)
                print(f"[引擎] 已加载 {len(self._trades)} 条历史交易记录")
        except Exception as e:
            print(f"[引擎] 加载交易历史失败: {e}")
            self._trades = []

    def _save_trades(self):
        """保存交易记录到文件"""
        try:
            with open(self.trades_file, 'w', encoding='utf-8') as f:
                json.dump(self._trades, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[引擎] 保存交易历史失败: {e}")

    def _sync_exchange_orders(self):
        """同步委托单级别的历史记录 (避免扫单导致记录过多)"""
        try:
            print(f"[引擎] 正在从 OKX 同步 {self.data_feed.symbol} 的委托单记录...")
            raw_orders = self.executor.get_order_history(self.data_feed.symbol, limit=50)
            if not raw_orders:
                return

            new_count = 0
            # 建立现有 ordId 集合以去重
            existing_ids = set()
            for t in self._trades:
                oid = t.get('meta', {}).get('ord_id')
                if oid: existing_ids.add(oid)
            
            for o in raw_orders:
                ord_id = o.get('ordId')
                if ord_id in existing_ids:
                    continue
                
                # 只同步已成交部分大于0的订单
                fill_sz = float(o.get('fillSz', 0))
                if fill_sz <= 0:
                    continue

                u_time = o.get('uTime')
                c_time = o.get('cTime')
                if u_time:
                    ts_ms = int(u_time)
                elif c_time:
                    ts_ms = int(c_time)
                else:
                    ts_ms = int(time.time() * 1000)
                dt = datetime.fromtimestamp(ts_ms/1000, tz=timezone.utc)
                side = o.get('side', '').upper()
                pos_side = o.get('posSide', '').lower()
                avg_px = float(o.get('avgPx', 0))
                pnl = float(o.get('pnl', 0)) if o.get('pnl') else None
                
                # 翻译 Action
                if pos_side == 'long':
                    action = "开多" if side == 'BUY' else "平多"
                elif pos_side == 'short':
                    action = "开空" if side == 'SELL' else "平空"
                else:
                    action = "买入" if side == 'BUY' else "卖出"

                # 关联本地意图 (Reason, Level 等)
                cl_ord_id = o.get('clOrdId')
                intent = self._pending_intents.get(cl_ord_id, {}) if cl_ord_id else {}
                
                # 记录理由增强
                strategy_reason = intent.get('reason') or "交易所同步"
                grid_level = intent.get('level', '-')
                
                detail = f"[同步] {action} | 层级:{grid_level} | 数量={fill_sz:.4f} 均价={avg_px:.2f}"
                if intent.get('reason'):
                   detail += f" | 理由: {intent['reason']}"
                
                # 将张数转换为 ETH 数量，确保单位统一
                eth_sz = fill_sz * self.executor.ct_val

                # 检查是否已存在记录
                existing_trade = next((t for t in self._trades if t['meta'].get('ord_id') == ord_id), None)
                
                if existing_trade:
                    # 如果已存在（如实时成交生成的瞬态记录），则更新 PnL 和精确数据
                    existing_trade.update({
                        'price': avg_px,
                        'size': eth_sz,
                        'quote_amount': avg_px * eth_sz,
                        'pnl': pnl,
                        'reason': f"{existing_trade.get('reason', '')} [已同步]"
                    })
                    # 确保更新后的记录时间戳也是最新的
                    existing_trade['t'] = ts_ms
                    existing_trade['time'] = dt.isoformat()
                    # 更新 detail 字段
                    existing_trade['detail'] = detail
                    # 更新 meta 中的 strategy_meta
                    existing_trade['meta']['strategy_meta'] = intent.get('meta', {})
                    # 不计入 new_count，因为是更新
                    # print(f"[引擎] 更新了委托单记录 {ord_id}")
                    continue # 继续处理下一个 raw_order
                
                record = {
                    'type': side,
                    'action': action,
                    'symbol': self.data_feed.symbol,
                    'price': avg_px,
                    'size': eth_sz, # 统一使用 ETH 数量
                    'quote_amount': avg_px * eth_sz, 
                    'pnl': pnl,
                    'time': dt.isoformat(),
                    't': ts_ms,
                    'detail': detail,
                    'reason': strategy_reason,
                    'meta': {
                        'ord_id': ord_id, 
                        'cl_ord_id': cl_ord_id,
                        'source': 'exchange',
                        'strategy_meta': intent.get('meta', {})
                    }
                }
                self._trades.append(record)
                new_count += 1
                
                # 同步成功后，如果缓存还在，可以移除 (可选，也可保留一段时间)
                if cl_ord_id in self._pending_intents:
                    del self._pending_intents[cl_ord_id]
            
            if new_count > 0:
                self._trades.sort(key=lambda x: x['t'])
                self._save_trades()
                print(f"[引擎] 已同步加载 {new_count} 条委托单记录")
        except Exception as e:
            print(f"[引擎] 同步委托单历史失败: {e}")

    def _load_initial_balance(self):
        """从文件恢复初始资金"""
        try:
            # 1. 尝试从正式持久化文件读取
            if os.path.exists(self.initial_balance_file):
                with open(self.initial_balance_file, 'r') as f:
                    data = json.load(f)
                val = data.get('initial_balance')
                # 2025-03-23 优化：放宽本金恢复范围检查 (> 0 且不等于已知的错误大数值)
                if val and val > 0 and val != 84000:
                    self.initial_total_value = val
                    print(f"[引擎] 已从持久化文件恢复初本金: {self.initial_total_value:.2f}")
                    return
                else:
                    print(f"[引擎] 持久化文件中的数值异常 ({val})，将尝试从备份/调试文件恢复")

            # 2. 尝试从 tmp/debug_equity.json 读取 (用于找回用户提到的 4999.x)
            # 路径修正：从 ethswap/engines/live.py 回溯三层到根目录，再进入 tmp
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            debug_file = os.path.join(root_dir, "tmp", "debug_equity.json")
            if os.path.exists(debug_file):
                with open(debug_file, 'r') as f:
                    data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    val = data[0].get('v')
                    if val and val > 0:
                        self.initial_total_value = val
                        print(f"[引擎] 已从调试文件还原初本金: {self.initial_total_value:.2f}")
                        self._save_initial_balance() # 顺便存入正式文件
                        return
                        
        except Exception as e:
            print(f"[引擎] 加载初始资金失败: {e}")

    def _save_initial_balance(self):
        """持久化初始资金"""
        if self.initial_total_value is None or self.initial_total_value <= 0:
            return
        try:
            with open(self.initial_balance_file, 'w') as f:
                json.dump({'initial_balance': self.initial_total_value}, f)
            print(f"[引擎] 初始本金已持久化: {self.initial_total_value:.2f}")
        except Exception as e:
            print(f"[引擎] 保存初始资金失败: {e}")

    def _sync_equity_history(self):
        """通过账单还原与 K 线对齐的资产历史 (阶梯形态)"""
        try:
            if not self._history_candles:
                return
                
            print(f"[引擎] 正在从 OKX 账单中还原资产历史...")
            bills = self.executor.get_recent_bills(limit=200)
            
            equity_history = []
            if not bills:
                # 如果没有账单，全量使用初始资产或当前资产填充以对齐 K 线
                base_val = self.initial_total_value if (self.initial_total_value and self.initial_total_value > 0) else self.executor.get_total_value()
                for candle in self._history_candles:
                    equity_history.append({'t': candle['t'], 'v': base_val})
                self._history_equity = equity_history
                print(f"[引擎] 未找到账单，已采用基准资产填充曲线: {base_val:.2f}")
                return

            # 按时间排序 bills (从旧到新)
            sorted_bills = sorted(bills, key=lambda x: int(x['ts']))
            
            bill_idx = 0
            # 初始锚点设置：对于最早一笔账单之前的 K 线，优先使用恢复出的 initial_total_value (4999.x)
            anchor_bal = self.initial_total_value if (self.initial_total_value and self.initial_total_value > 0) else float(sorted_bills[0].get('bal', 0))
            current_bal = anchor_bal
            
            for candle in self._history_candles:
                candle_ts = candle['t']
                # 寻找在该 K 线时间或之前的最新一笔账单
                while bill_idx < len(sorted_bills) and int(sorted_bills[bill_idx]['ts']) <= candle_ts:
                    current_bal = float(sorted_bills[bill_idx].get('bal', 0))
                    bill_idx += 1
                
                equity_history.append({
                    't': candle_ts,
                    'v': current_bal
                })
            
            if equity_history:
                self._history_equity = equity_history
                # 如果依然没有初始资产定义，则将其锁定为曲线第一个点
                if self.initial_total_value is None or self.initial_total_value <= 0:
                    self.initial_total_value = equity_history[0]['v']
                    self._save_initial_balance()
                print(f"[引擎] 已还原 {len(equity_history)} 个对齐的资产快照点，初始资产: {self.initial_total_value:.2f}")
        except Exception as e:
            print(f"[引擎] 还原资产历史失败: {e}")
            import traceback; traceback.print_exc()
    
    def register_status_callback(self, callback: Callable[[Dict], None]):
        self._status_callbacks.append(callback)
    
    def _get_context(self) -> StrategyContext:
        positions = {}
        for pos in self.executor.get_all_positions():
            positions[pos.symbol] = pos
        return StrategyContext(
            timestamp=self._current_time,
            cash=self.executor.get_cash(),
            positions=positions,
            current_prices=self._current_prices.copy(),
            meta={}
        )
    
    def _on_fill(self, fill: FillEvent):
        self.strategy.on_fill(fill)
        side = fill.side.value.upper()
        symbol = fill.symbol
        price = fill.filled_price
        size = fill.filled_size
        quote_amount = fill.quote_amount
        
        # 合约语义适配：size 可能为负（对应 Position），但在交易记录中我们显示绝对值
        abs_size = abs(size)
        
        # 合约特有：Action 翻译 (开多/平多/开空/平空)
        pos_side = fill.meta.get('posSide', '').lower()
        if pos_side == 'long':
            action = "开多" if side == 'BUY' else "平多"
        elif pos_side == 'short':
            action = "开空" if side == 'SELL' else "平空"
        else:
            # 兼容逻辑
            action = "买入" if side == 'BUY' else "卖出"

        detail = f"{action} 数量={abs_size:.6f} 价格={price:.2f}"
        if quote_amount:
            detail += f" 总额={quote_amount:.2f}"
        
        trade_record = {
            'type': side,
            'action': action,
            'symbol': symbol,
            'price': price,
            'size': abs_size,
            'quote_amount': quote_amount,
            'pnl': fill.pnl,
            'time': fill.timestamp.isoformat(),
            't': int(fill.timestamp.timestamp() * 1000), 
            'detail': detail,
            'reason': fill.meta.get('reason', '实时交易'),
            'meta': {
                'trade_id': fill.meta.get('trade_id') or str(int(time.time()*1000)), 
                'ord_id': fill.order_id, 
                'source': 'live'
            }
        }
        # 不再向 self._trades 追加，杜绝重复写入。
        # 记录最新的这笔交易，仅用于 Dashboard 实时图标闪烁展示 (瞬时态)
        self._latest_trade = trade_record
        print(f"[成交反馈] {side} {symbol} | {detail} | 价格=${price:.2f} (等待交易所同步入库)")
    
    def _on_data(self, data: MarketData):
        """处理实时数据 (主要由 run 循环调用)"""
        # 数据量计数
        if not hasattr(self, '_data_count'): self._data_count = 0
        self._data_count += 1
        
        self._current_time = data.timestamp
        self._current_prices[data.symbol] = data.close
        
        # 同步资产和 RSI 历史
        self._sync_history_candles(data)
        
        # 执行策略逻辑
        context = self._get_context()
        signals = self.strategy.on_data(data, context)
        
        if signals:
            self._execute_signals(signals)
            
        # 杠杆动态调整逻辑 (V93 专用)
        if hasattr(context, 'meta') and isinstance(context.meta, dict) and 'requested_leverage' in context.meta:
            lev = context.meta['requested_leverage']
            if lev > 0:
                self.executor.set_leverage(lev)
                print(f"[引擎] 策略请求调整杠杆为: {lev}x")
        
        # 每 30 次数据包(约30-40秒)自动触发一次交易所订单同步
        if self._data_count % 30 == 0:
            self._sync_exchange_orders()
            
        # 广播状态到 Dashboard
        status = self._build_status(data)
        self._notify_status(status)
    
    def _execute_signals(self, signals: List[Signal]):
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
            # 记录意图，以便稍后同步时回填理由
            cl_ord_id = order.meta.get('clOrdId')
            if not cl_ord_id:
                cl_ord_id = f"v93x{int(time.time()*1000)}"
                order.meta['clOrdId'] = cl_ord_id
                
            self._pending_intents[cl_ord_id] = {
                'reason': signal.reason,
                'level': signal.meta.get('level'),
                'meta': signal.meta
            }
            
            order_id = self.executor.submit_order(order)
            if not order_id or order.status == OrderStatus.REJECTED:
                # 如果下单失败，移除意图缓存
                if cl_ord_id in self._pending_intents:
                    del self._pending_intents[cl_ord_id]
                reason = order.meta.get('reject_reason', 'submit_failed_or_rejected')
                print(f"[执行拒单] {order.symbol} {order.side.value} sz={order.size} reason={reason}")
    
    def _notify_status(self, data: Dict):
        for callback in self._status_callbacks:
            try:
                callback(data)
            except Exception as e:
                print(f"状态回调错误: {e}")
    
    def warmup(self):
        """通用预热逻辑"""
        self.strategy.initialize()
        print(f"正在预热策略 ({self.warmup_bars} bars)...")
        
        try:
            if hasattr(self.data_feed, 'api'):
                df = self.data_feed.api.get_candles(
                    self.data_feed._inst_id, 
                    self.data_feed._bar_map.get(self.data_feed.timeframe, '1m'), 
                    limit=self.warmup_bars
                )
                if df is not None and len(df) > 0:
                    print(f"  成功获取 {len(df)} 条历史数据")
                    # 预热阶段的资产点：
                    # 如果已知初始资金 (4999.x)，我们应该用它作为这段“远古”历史的起点
                    # 只有在确实没有初始记录时才用当前值兜底。这消除了从 5000 到当前值的平线跳变。
                    historical_equity = self.initial_total_value if (self.initial_total_value and self.initial_total_value > 0) else self.executor.get_total_value()
                        
                    # 预热阶段先模拟 context，避免循环内重复请求 OKX 持仓 API (防止触发限频)
                    all_pos = self.executor.get_all_positions()
                    prefetched_positions = {p.symbol: p for p in all_pos}
                        
                    for timestamp, row in df.iterrows():
                        data = MarketData(
                            timestamp=timestamp, symbol=self.data_feed.symbol,
                            open=float(row['open']), high=float(row['high']),
                            low=float(row['low']), close=float(row['close']),
                            volume=float(row['volume'])
                        )
                        # 重要：预热阶段调用 on_data 以初始化 RSI 和波段点等内部状态
                        # 使用预热专用的 Mock Context
                        context = StrategyContext(
                            timestamp=timestamp,
                            cash=historical_equity, # 预热期暂用初始值
                            positions=prefetched_positions,
                            current_prices={data.symbol: data.close} # 补全缺失参数，防止 TypeError
                        )
                        self.strategy.on_data(data, context)
                        
                        self._current_prices[data.symbol] = data.close
                        # 传递 historical_equity 填充数据骨架
                        self._sync_history_candles(data, current_equity=historical_equity)
                    
                    # 预热结束，输出摘要
                    if len(self._history_candles) > 0:
                        first = self._history_candles[0]
                        last = self._history_candles[-1]
                        f_t = datetime.fromtimestamp(first['t']/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')
                        l_t = datetime.fromtimestamp(last['t']/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')
                        print(f"  [摘要] 预热起点: {f_t} | 价格: {first['c']:.2f}")
                        print(f"  [摘要] 预热终点: {l_t} | 价格: {last['c']:.2f}")
                else:
                    print(f"  警告: 未能获取历史数据 (可能网络超时或 API 错误)，尝试继续运行...")
        except Exception as e:
            print(f"  预热过程中发生异常: {e}")
            import traceback; traceback.print_exc()
        
        self._is_warmed = True # 标记预热流程已执行完成 (无论成功与否，以免阻塞主循环)
    
    def run(self):
        # 记录初始本金 (如果尚未通过持久化恢复)
        if self.initial_total_value is None:
            self.initial_total_value = self.executor.get_total_value()
            self._save_initial_balance()
            print(f"[引擎] 记录初始本金: {self.initial_total_value:.2f} USDT")
            
        if not self._is_warmed:
            self.warmup()
            # 预热完成后，且已载入 K 线骨架，执行资产历史对齐还原
            self._sync_equity_history()
        
        self.is_running = True
        self.strategy.on_start()
        
        print("  开始正式运行...")
        
        # 预热后立即推送一次当前状态给 Dashboard，以显示历史数据
        if self._history_candles:
            # 使用最后一根预热 K 线作为基础
            last_candle = self._history_candles[-1]
            # 构造一个临时 MarketData 用于 status 构造
            last_data = MarketData(
                timestamp=datetime.fromtimestamp(last_candle['t']/1000, tz=timezone.utc),
                symbol=self.data_feed.symbol,
                open=last_candle['o'], high=last_candle['h'],
                low=last_candle['l'], close=last_candle['c'], volume=0
            )
            status = self._build_status(last_data)
            self._notify_status(status)
            print("  已同步历史数据到监控面板")

        print(f"\n{'='*60}\n实盘引擎启动 | 策略: {self.strategy.name}\n{'='*60}\n")
        
        try:
            data_count = 0
            for data in self.data_feed.stream():
                if not self.is_running: break
                
                data_count += 1
                # 使用统一的 _on_data 处理每根 K 线
                self._on_data(data)
                
                if data_count % 10 == 0:
                    print(f"[引擎] 已处理 {data_count} 条数据 | 价格: {data.close:.2f}")
                
        except KeyboardInterrupt:
            print("\n收到停止信号...")
        except Exception as e:
            print(f"引擎错误: {e}")
            import traceback; traceback.print_exc()
        finally:
            self.stop()
    
    def _build_status(self, data: MarketData) -> Dict:
        # 2025-03-23 优化：缓存账户资产数据，避免 2s 一次的频繁 API 请求导致刷新卡顿
        now = time.time()
        if not hasattr(self, '_last_account_sync') or (now - self._last_account_sync > 10):
            try:
                self._cached_positions = self.executor.get_all_positions()
                self._cached_cash = self.executor.get_cash()
                self._cached_total_value = self.executor.get_total_value()
                self._last_account_sync = now
                # print(f"[状态] 已更新账户资产和持仓数据 (下一步每 2s 仅更新价格)")
            except Exception as e:
                print(f"更新账户状态失败(使用缓存): {e}")
                if not hasattr(self, '_cached_positions'):
                    self._cached_positions = []
                    self._cached_cash = 0
                    self._cached_total_value = 0
        
        positions = self._cached_positions
        cash = self._cached_cash
        total_value = self._cached_total_value
        
        # 计算 PNL
        pnl_pct = 0.0
        if self.initial_total_value and self.initial_total_value > 0:
            pnl_pct = (total_value - self.initial_total_value) / self.initial_total_value * 100
        
        strategy_status = {}
        if hasattr(self.strategy, 'get_status'):
            strategy_status = self.strategy.get_status()
        
        status = {
            'timestamp': data.timestamp.isoformat(),
            'symbol': data.symbol,
            'price': data.close,
            'candle': {
                't': int(data.timestamp.timestamp() * 1000),
                'o': data.open, 'h': data.high, 'l': data.low, 'c': data.close
            },
            'prices': self._current_prices.copy(),
            'cash': cash,
            'total_value': total_value,
            'initial_balance': self.initial_total_value,
            'pnl_pct': pnl_pct,
            'rsi': strategy_status.get('rsi', 50),
            'strategy': strategy_status,
            'positions': {
                p.symbol: {
                    'size': p.size, 
                    'avg_price': p.avg_price,
                    # 使用最新价动态计算持仓市值，无需等待 10s
                    'value': p.size * data.close if p.size != 0 else 0
                }
                for p in positions
            }
        }
        
        # 增量发送最新交易
        if self._latest_trade:
            status['trade'] = self._latest_trade
            self._latest_trade = None # 发送后清空
            
        # 仅在第一次同步时同步庞大的历史数据 (统一取最后 500 点以对齐索引)
        max_hist = 500
        if not self._history_sent:
            if self._history_candles:
                status['history_candles'] = self._history_candles[-max_hist:]
            if self._history_equity:
                status['history_equity'] = self._history_equity[-max_hist:]
            if self._history_rsi:
                status['history_rsi'] = self._history_rsi[-max_hist:]
            if self._trades:
                status['trade_history'] = self._trades
                
            self._history_sent = True
            print(f"[引擎] 已完成初始全量数据同步 (对齐点数: {len(status.get('history_candles', []))})")
            
        return status
    
    def _sync_history_candles(self, data: MarketData, current_equity: float = None):
        """同步 K 线、资产及 RSI 历史，确保索引严格对齐"""
        candle_ms = int(data.timestamp.timestamp() * 1000)
        candle = {
            't': candle_ms,
            'o': data.open, 'h': data.high, 'l': data.low, 'c': data.close
        }
        
        # 获取当前权益和 RSI
        total_value = current_equity if current_equity is not None else (self.executor.get_total_value() if hasattr(self.executor, 'get_total_value') else 0)
        rsi = getattr(self.strategy, 'last_rsi', 50.0)
        
        if self._history_candles and self._history_candles[-1]['t'] == candle_ms:
            # 1. 更新当前 K 线及其对齐点
            self._history_candles[-1] = candle
            if self._history_equity: self._history_equity[-1] = {'t': candle_ms, 'v': total_value}
            if self._history_rsi: self._history_rsi[-1] = float(rsi)
        else:
            # 2. 新增 K 线及其对齐点
            self._history_candles.append(candle)
            self._history_equity.append({'t': candle_ms, 'v': total_value})
            self._history_rsi.append(float(rsi))
        
        # 记录资产历史
        # 即使在预热阶段也记录权益和 RSI，以保持与 K 线历史的索引对齐
        if hasattr(self.executor, 'get_total_value'):
            total_value = current_equity if current_equity is not None else self.executor.get_total_value()
            self._history_equity.append({'t': candle['t'], 'v': total_value})
            
            # 同时记录 RSI 历史
            rsi = getattr(self.strategy, 'last_rsi', 50.0)
            self._history_rsi.append(float(rsi))
            
            if len(self._history_equity) > 500:
                self._history_equity.pop(0)
                self._history_rsi.pop(0)

        if len(self._history_candles) > 2000:
            self._history_candles = self._history_candles[-2000:]

    def save_trades(self, filepath: str):
        import json
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self._trades, f, indent=4)
        except Exception as e:
            print(f"[引擎] 保存交易记录失败: {e}")

    def load_trades(self, filepath: str):
        import json, os
        if not os.path.exists(filepath): return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self._trades = json.load(f)
        except Exception as e:
            print(f"[引擎] 加载交易记录失败: {e}")

    def reset(self):
        """重置引擎状态（用于测试）"""
        print("\n" + "!"*40 + "\n[引擎] 正在执行重置程序...\n" + "!"*40)
        self.stop()
        
        # 清空内部数据
        self._trades = []
        self._history_candles = []
        self._history_sent = False
        self.initial_total_value = None
        
        # 重置策略
        if hasattr(self.strategy, 'initialize'):
            self.strategy.initialize()
            
        print("[引擎] 重置完成，准备重新启动")
        
        # 注意：这里并不自动 run()，而是让外部逻辑决定
        # 但在 run_eth_swap_v93.py 中，由于 run() 在主线程，重置建议通过设置标志位或拋出异常实现
        # 简化版：这里只清理数据，由 LiveEngine.run() 中的循环检查 stop 状态

    def stop(self):
        self.is_running = False
        self.strategy.on_stop()
        self.data_feed.stop()
        print("\n引擎已停止")
