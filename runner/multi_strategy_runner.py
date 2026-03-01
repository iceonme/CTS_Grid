"""
MultiStrategyRunner — 多策略并发运行管理器

设计理念：
- 单一 OKXDataFeed 连接广播数据至所有策略（节省 API 配额）
- 每个 StrategySlot 独立账户、独立持久化、独立暂停控制
- 异常隔离：某策略崩溃不影响其他策略
"""

import threading
import os
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable, Any
from datetime import datetime, timezone

from strategies.base import BaseStrategy
from executors.paper import PaperExecutor
from core import MarketData, StrategyContext


@dataclass
class StrategySlot:
    """单个策略的运行单元"""
    slot_id: str
    display_name: str
    strategy: BaseStrategy
    executor: PaperExecutor
    initial_balance: float

    # 持久化文件路径（每个 slot 独立）
    state_file: str = ""
    trades_file: str = ""

    # 运行控制
    _pause_event: threading.Event = field(default_factory=threading.Event)
    _is_running: bool = False
    _bar_count: int = 0

    def __post_init__(self):
        # 默认文件路径（如未指定）
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if not self.state_file:
            self.state_file = os.path.join(base, f"trading_state_{self.slot_id}.json")
        if not self.trades_file:
            self.trades_file = os.path.join(base, f"trading_trades_{self.slot_id}.json")
        # 默认启动时未暂停
        self._pause_event.set()

    @property
    def is_running(self):
        return self._is_running

    @property
    def is_paused(self):
        return not self._pause_event.is_set()

    def pause(self):
        self._pause_event.clear()
        print(f"[Slot:{self.slot_id}] 已暂停（不处理新 bar）")

    def resume(self):
        self._pause_event.set()
        print(f"[Slot:{self.slot_id}] 已恢复运行")

    def start(self):
        self._is_running = True
        self._pause_event.set()
        print(f"[Slot:{self.slot_id}] 已启动")

    def stop(self):
        self._is_running = False
        print(f"[Slot:{self.slot_id}] 已停止")


class MultiStrategyRunner:
    """
    多策略并发运行管理器

    用法：
        runner = MultiStrategyRunner(dashboard)
        runner.add_slot(slot)
        runner.start_all()      # 启动所有 slot
        runner.start('v40')     # 单独启动
        runner.pause('v51')     # 单独暂停
    """

    def __init__(self, dashboard=None):
        self.dashboard = dashboard
        self._slots: Dict[str, StrategySlot] = {}
        self._trades: Dict[str, list] = {}   # slot_id -> trade list
        self._warmup_done = False

    # ──────────────────────────────────────────────
    # 槽管理
    # ──────────────────────────────────────────────

    def add_slot(self, slot: StrategySlot):
        """注册一个策略槽"""
        self._slots[slot.slot_id] = slot
        self._trades[slot.slot_id] = []

        # 向 Dashboard 注册该策略
        if self.dashboard:
            self.dashboard.register_strategy(slot.slot_id, slot.display_name)

        # 尝试加载持久化状态
        if os.path.exists(slot.state_file):
            try:
                slot.executor.load_state(slot.state_file)
                print(f"[Slot:{slot.slot_id}] 已从持久化恢复账户状态: "
                      f"{slot.executor.get_cash():.2f} USDT")
            except Exception as e:
                print(f"[Slot:{slot.slot_id}] 加载状态失败: {e}")

        # 尝试加载历史交易
        if os.path.exists(slot.trades_file):
            try:
                import json
                with open(slot.trades_file, 'r') as f:
                    self._trades[slot.slot_id] = json.load(f)
                print(f"[Slot:{slot.slot_id}] 加载 {len(self._trades[slot.slot_id])} 条历史交易")
            except Exception as e:
                print(f"[Slot:{slot.slot_id}] 加载交易历史失败: {e}")

        print(f"[Runner] 注册策略槽: {slot.slot_id} ({slot.display_name})")

    # ──────────────────────────────────────────────
    # 控制 API（供 Dashboard SocketIO 回调调用）
    # ──────────────────────────────────────────────

    def start(self, slot_id: str):
        slot = self._slots.get(slot_id)
        if slot:
            slot.start()
            self._push_status_update(slot, note="控制信号: 已启动")

    def pause(self, slot_id: str):
        slot = self._slots.get(slot_id)
        if slot:
            slot.pause()
            self._push_status_update(slot, note="控制信号: 已暂停")

    def reset(self, slot_id: str):
        slot = self._slots.get(slot_id)
        if not slot:
            return
        print(f"[Runner] 重置策略槽: {slot_id}")
        slot.stop()
        slot.executor.reset()
        slot.strategy.initialize()
        self._trades[slot_id] = []
        # 删除持久化文件
        for f in [slot.state_file, slot.trades_file]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                    print(f"  已删除: {os.path.basename(f)}")
                except Exception as e:
                    print(f"  删除失败: {e}")
        # 重置后策略处于停止状态，不再自动恢复运行
        # slot.start()

    def start_all(self):
        for slot in self._slots.values():
            slot.start()

    def get_status(self, slot_id: str) -> dict:
        slot = self._slots.get(slot_id)
        if not slot:
            return {}
        return {
            'is_running': slot.is_running,
            'is_paused': slot.is_paused,
            'bar_count': slot._bar_count,
        }

    # ──────────────────────────────────────────────
    # 数据广播（核心）
    # ──────────────────────────────────────────────

    def on_bar(self, market_data: MarketData):
        """
        由 OKXDataFeed 回调触发，广播给所有策略。
        
        - 数据推送：始终执行（无论启动状态），让前端实时看到行情
        - 信号执行：只有 is_running=True 且未暂停时才处理
        """
        # 移除原有的简单心跳，交由 _push_dashboard 进行带数据的摘要打印

        for slot in self._slots.values():
            try:
                self._process_bar(slot, market_data)
            except Exception as e:
                print(f"[Slot:{slot.slot_id}] 处理 bar 异常: {e}")
                import traceback
                traceback.print_exc()

    def _process_bar(self, slot: StrategySlot, data: MarketData):
        """
        处理单根 K 线
        - 数据推送：无论启动状态，始终向 Dashboard 推送价格和指标数据
        - 信号执行：仅当 is_running=True 且未暂停时才计算并下单
        """
        slot._bar_count += 1

        # 更新执行器的市场数据（价格/时间）
        slot.executor.update_market_data(data.timestamp, data.close)

        # 构建 context
        cash = slot.executor.get_cash()
        positions_list = slot.executor.get_all_positions()
        positions = {p.symbol: p for p in positions_list}

        context = StrategyContext(
            timestamp=data.timestamp,
            cash=cash,
            positions=positions,
            current_prices={data.symbol: data.close}
        )

        # === 信号执行部分（仅 is_running 且未暂停） ===
        if slot.is_running and not slot.is_paused:
            try:
                signals = slot.strategy.on_data(data, context)
                for sig in (signals if signals else []):
                    try:
                        # --- 执行审计 ---
                        if slot.slot_id == 'grid_v51':
                            print(f"  [SIGNAL] [V5.1] 发现信号: {sig.side.name} | 数量: {sig.size} | 原因: {getattr(sig, 'reason', 'N/A')}")

                        from core import Order, OrderType
                        order = Order(
                            order_id="",
                            symbol=sig.symbol,
                            side=sig.side,
                            order_type=OrderType.MARKET,
                            size=sig.size,
                            meta=sig.meta if hasattr(sig, 'meta') and sig.meta else {}
                        )
                        order_id = slot.executor.submit_order(order)
                        
                        if order_id:
                            from core import OrderStatus
                            if order.status == OrderStatus.REJECTED:
                                print(f"  [ORDER]  [{slot.slot_id}] 订单被拒绝! 原因: {order.meta.get('reject_reason', '未知')}")
                            else:
                                if slot.slot_id == 'grid_v51':
                                    print(f"  [ORDER]  [V5.1] 订单已成交: {order_id} | 价格: {order.avg_price:.2f}")
                                trade = {
                                    'time': data.timestamp.isoformat(),
                                    'side': sig.side.value if hasattr(sig.side, 'value') else str(sig.side),
                                    'size': getattr(order, 'filled_size', None) or sig.size,
                                    'price': data.close,
                                    'fee': 0,
                                    'type': 'BUY' if 'buy' in str(sig.side).lower() else 'SELL',
                                    'reason': getattr(sig, 'reason', ''),
                                    'quote_amount': (getattr(order, 'filled_size', None) or sig.size) * data.close,
                                }
                                self._trades[slot.slot_id].append(trade)
                    except Exception as e:
                        print(f"[Slot:{slot.slot_id}] 执行信号失败: {e}")
                if signals:
                    self._save_slot(slot)
            except Exception as e:
                print(f"[Slot:{slot.slot_id}] on_data 异常: {e}")
                import traceback
                traceback.print_exc()
        else:
            # 当策略暂停时，手动更新指标以便 Dashboard 能够正确显示
            try:
                if hasattr(slot.strategy, '_update_buffer') and hasattr(slot.strategy, '_get_dataframe'):
                    slot.strategy._update_buffer(data)
                    df = slot.strategy._get_dataframe()
                    
                    if hasattr(slot.strategy, '_calculate_rsi') and hasattr(slot.strategy.state, 'current_rsi'):
                        if len(df) >= getattr(slot.strategy.params, 'rsi_period', 14):
                            slot.strategy.state.current_rsi = slot.strategy._calculate_rsi(df['close'])
                            
                    if hasattr(slot.strategy, '_calculate_macd'):
                        ml, sl, hi = slot.strategy._calculate_macd(df)
                        if hasattr(slot.strategy.state, 'macd_line'):
                            slot.strategy.state.macd_line = ml
                            slot.strategy.state.signal_line = sl
                            slot.strategy.state.histogram = hi
            except Exception:
                pass

        # === 数据推送部分（始终执行） ===
        self._push_dashboard(slot, data, context)

    # ──────────────────────────────────────────────
    # Dashboard 推送
    # ──────────────────────────────────────────────

    def _push_status_update(self, slot: StrategySlot, note: str = ""):
        """推送简单的控制状态更新"""
        if not self.dashboard:
            return
        ctrl_data = {
            'slot_status': {
                'is_running': slot.is_running,
                'is_paused': slot.is_paused,
                'note': note,
            }
        }
        self.dashboard.update(ctrl_data, strategy_id=slot.slot_id)

    def _push_dashboard(self, slot: StrategySlot, data: MarketData, context):
        """每 bar 推送完整的策略+资产状态到 Dashboard"""
        if not self.dashboard:
            return

        ts_ms = int(data.timestamp.timestamp() * 1000)
        cash = context.cash
        positions = context.positions

        pos_data = {}
        position_value = 0.0
        for sym, p in positions.items():
            size = p.size if hasattr(p, 'size') else p
            avg_price = p.avg_price if hasattr(p, 'avg_price') else 0
            pos_data[sym] = {'size': size, 'avg_price': avg_price}
            position_value += size * data.close

        total_value = cash + position_value
        pnl_pct = (total_value / slot.initial_balance - 1) * 100 if slot.initial_balance > 0 else 0

        strategy_status = slot.strategy.get_status(context)
        rsi_val = strategy_status.get('current_rsi', 50) if strategy_status else 50

        dashboard_data = {
            'timestamp': ts_ms,
            'prices': {data.symbol: data.close},
            'candle': {
                't': ts_ms, 'o': data.open,
                'h': data.high, 'l': data.low, 'c': data.close
            },
            'total_value': total_value,
            'cash': cash,
            'position_value': position_value,
            'positions': pos_data,
            'pnl_pct': round(pnl_pct, 4),
            'initial_balance': slot.initial_balance,
            'rsi': rsi_val,
            'trade_history': self._trades[slot.slot_id],
            'strategy': strategy_status,
            'slot_status': {
                'is_running': slot.is_running,
                'is_paused': slot.is_paused,
            }
        }

        # 追加到历史缓存
        slot_cache = self.dashboard._data.get(slot.slot_id, {})
        hc = slot_cache.get('history_candles', [])
        candle = dashboard_data['candle']
        if hc and hc[-1]['t'] == candle['t']:
            hc[-1] = candle
        else:
            hc.append(candle)
            if len(hc) > 500:
                hc.pop(0)

        hrsi = slot_cache.get('history_rsi', [])
        if hrsi and hrsi[-1]['t'] == candle['t']:
            hrsi[-1]['v'] = rsi_val
        else:
            hrsi.append({'t': candle['t'], 'v': rsi_val})
            if len(hrsi) > 500:
                hrsi.pop(0)

        heq = slot_cache.get('history_equity', [])
        if heq and heq[-1]['t'] == candle['t']:
            heq[-1]['v'] = total_value
        else:
            heq.append({'t': candle['t'], 'v': total_value})
            if len(heq) > 500:
                heq.pop(0)

        # 实时维护 MACD 历史缓存（刷新后仍能完整对齐）
        hmacd = slot_cache.get('history_macd', [])
        macd_item = {'time': ts_ms, 'macd': None, 'macdsignal': None, 'macdhist': None}
        if strategy_status:
            ml = strategy_status.get('macd')
            sl = strategy_status.get('macdsignal')
            hi = strategy_status.get('macdhist')
            macd_item = {
                'time': ts_ms,
                'macd': float(ml) if ml is not None else None,
                'macdsignal': float(sl) if sl is not None else None,
                'macdhist': float(hi) if hi is not None else None,
            }
        if hmacd and hmacd[-1]['time'] == ts_ms:
            hmacd[-1] = macd_item
        else:
            hmacd.append(macd_item)
            if len(hmacd) > 500:
                hmacd.pop(0)
        slot_cache['history_macd'] = hmacd

        self.dashboard.update(dashboard_data, strategy_id=slot.slot_id)

        # 终端摘要打印 (节流控制：每 15 个 bar 打印一次，约 30 秒)
        if not hasattr(self, '_summary_counter'):
            self._summary_counter = 0
        self._summary_counter += 1
        
        if self._summary_counter % 15 == 0:
            # 这里的打印会在所有 slot 处理完后触发一次吗？
            # 实际上由于 update 会并发或顺序调用，我们只需要在一个特定的 slot 或者全局计数器下打印一次
            # 简单起见，如果当前是已知存在的第一个 slot，就打印所有运行中的 slot 摘要
            first_slot_id = next(iter(self._slots))
            if slot.slot_id == first_slot_id:
                now_str = datetime.now().strftime('%H:%M:%S')
                summary = f"[{now_str}] ══ 市场: {data.symbol} ${data.close:,.2f} ══"
                for s_id, s_slot in self._slots.items():
                    status_flag = "▶" if s_slot.is_running and not s_slot.is_paused else "⏸"
                    # 从已有的数据中提取关键指标
                    cached = self.dashboard._data.get(s_id, {})
                    r_val = cached.get('rsi', 0)
                    e_val = cached.get('total_value', 0)
                    p_pct = cached.get('pnl_pct', 0)
                    summary += f"\n  {status_flag} [{s_id}] RSI:{r_val:.1f} | 权益:{e_val:,.1f} | 盈亏:{p_pct:+.2f}%"
                print(summary + "\n")

    def push_warmup(self, slot: StrategySlot, history_candles: list,
                    history_rsi: list, history_equity: list, history_macd: list = None):
        """预热完成后发送历史数据快照"""
        if not self.dashboard:
            return
        warmup_data = {
            'history_candles': history_candles,
            'history_rsi': history_rsi,
            'history_equity': history_equity,
            'history_macd': history_macd or [],
            'prices': {},
            'candle': history_candles[-1] if history_candles else {},
            'total_value': history_equity[-1]['v'] if history_equity else slot.initial_balance,
            'cash': slot.executor.get_cash(),
            'position_value': 0,
            'positions': {},
            'pnl_pct': 0,
            'initial_balance': slot.initial_balance,
            'rsi': history_rsi[-1]['v'] if history_rsi and history_rsi[-1]['v'] is not None else 50,
            'trade_history': self._trades[slot.slot_id],
            'strategy': slot.strategy.get_status(None),
            'slot_status': {
                'is_running': slot.is_running,
                'is_paused': slot.is_paused,
            }
        }
        self.dashboard.update(warmup_data, strategy_id=slot.slot_id)
        print(f"[Slot:{slot.slot_id}] 预热数据已推送到 Dashboard")

    # ──────────────────────────────────────────────
    # 持久化
    # ──────────────────────────────────────────────

    def _save_slot(self, slot: StrategySlot):
        try:
            slot.executor.save_state(slot.state_file)
        except Exception as e:
            print(f"[Slot:{slot.slot_id}] 保存账户状态失败: {e}")
        try:
            import json
            with open(slot.trades_file, 'w') as f:
                json.dump(self._trades[slot.slot_id], f, ensure_ascii=False, default=str)
        except Exception as e:
            print(f"[Slot:{slot.slot_id}] 保存交易记录失败: {e}")

    def save_all(self):
        for slot in self._slots.values():
            self._save_slot(slot)
