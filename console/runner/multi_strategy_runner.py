"""
MultiStrategyRunner - 多策略并发运行管理器

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

from cartridges.strategies.base import BaseStrategy
from cartridges.bridge.executors.base import BaseExecutor
from console.core import MarketData, StrategyContext, Order, OrderType, OrderStatus


@dataclass
class StrategySlot:
    """单个策略的运行单元"""
    slot_id: str
    display_name: str
    strategy: BaseStrategy
    executor: BaseExecutor
    initial_balance: float

    # 持久化文件路径（每个 slot 独立）：
    state_file: str = ""
    trades_file: str = ""

    # Skill 元信息（从 SKILL.md frontmatter 解析，可选）
    skill_meta: dict = field(default_factory=dict)

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
        # 默认起始时未暂停
        self._pause_event.set()

    @property
    def is_running(self):
        return self._is_running

    @property
    def is_paused(self):
        return not self._pause_event.is_set()

    def pause(self):
        self._pause_event.clear()
        print(f"[Slot:{self.slot_id}] 指令执行: 暂停 (pause_event.clear)")

    def resume(self):
        self._pause_event.set()
        print(f"[Slot:{self.slot_id}] 指令执行: 恢复 (pause_event.set)")

    def start(self):
        print(f"[Slot:{self.slot_id}] 指令执行: 启动中...")
        self._is_running = True
        self.resume()
        print(f"[Slot:{self.slot_id}] 启动成功: running={self._is_running}, paused={self.is_paused}")
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

    # ------------------------------------------------------------
    # 槽管理
    # ------------------------------------------------------------

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
                
                # 恢复运行状态
                import json
                with open(slot.state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                    
                    # [核心逻辑] 恢复策略内部状态（槽位、锁定标记等）
                    strategy_state = state_data.get('strategy_state')
                    if strategy_state and hasattr(slot.strategy, 'set_state'):
                        print(f"[Slot:{slot.slot_id}] 正在从持久化恢复策略内部状态...")
                        slot.strategy.set_state(strategy_state)

                    meta = state_data.get('slot_metadata', {})
                    if meta.get('is_running'):
                        slot.start()
                    if meta.get('is_paused'):
                        slot.pause()
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

    # ------------------------------------------------------------
    # 控制 API（供 Dashboard SocketIO 回调调用）：
    # ------------------------------------------------------------

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

    def on_control_handle(self, action: str, slot_id: str, **kwargs):
        """处理来自 Dashboard 的远程控制指令"""
        print(f"[Runner] 接收到控制请求: action={action}, slot_id={slot_id}")
        if action == 'start':
            self.start(slot_id)
        elif action == 'pause':
            self.pause(slot_id)
        elif action == 'reset':
            self.reset(slot_id)
        elif action == 'save_params':
            new_params = kwargs.get('data')
            slot = self._slots.get(slot_id)
            if slot and new_params:
                # 合并参数并通知策略
                slot.strategy.params.update(new_params)
                # 如果策略有专门的重载逻辑
                if hasattr(slot.strategy, 'initialize'):
                    # 某些策略可能需要重新初始化指标
                    pass
                print(f"[Runner] 策略 {slot_id} 参数已热更新: {new_params}")
                self._save_slot(slot) # 保存到磁盘以便下次启动生效

    def get_status(self, slot_id: str) -> dict:
        slot = self._slots.get(slot_id)
        if not slot:
            return {}
        return {
            'is_running': slot.is_running,
            'is_paused': slot.is_paused,
            'bar_count': slot._bar_count,
        }

    # ------------------------------------------------------------
    # 数据广播（核心）
    # ------------------------------------------------------------

    def on_bar(self, market_data: MarketData):
        """
        由 OKXDataFeed 回调触发，广播给所有策略。
        """
        # 初次运行或每 10 次打印一个极其简短的心跳，证明 Runner 还在工作
        if not hasattr(self, '_heartbeat_count'): self._heartbeat_count = 0
        self._heartbeat_count += 1
        if self._heartbeat_count % 10 == 1:
             print(f"🔍 [Runner] 接收数据流: {market_data.symbol} @ {market_data.close} ({market_data.timestamp.strftime('%H:%M:%S')})", flush=True)

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

        # 更新执行器的市场数据（价格 / 时间）：
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

        # === 信号执行部分（仅 is_running 且未暂停时） ===
        if slot.is_running and not slot.is_paused:
            try:
                signals = slot.strategy.on_data(data, context)
                for sig in (signals if signals else []):
                    try:
                        # --- 执行审计 ---
                        if 'grid_v5' in slot.slot_id:
                            print(f"  [SIGNAL] [{slot.slot_id.upper()}] 发现信号: {sig.side.name} | 数量: {sig.size} | 原因: {getattr(sig, 'reason', 'N/A')}")

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
                            if order.status == OrderStatus.REJECTED:
                                print(f"  [ORDER]  [{slot.slot_id}] 订单被拒绝: 原因: {order.meta.get('reject_reason', '未知')}")
                            else:
                                if 'grid_v5' in slot.slot_id:
                                    print(f"  [ORDER]  [{slot.slot_id.upper()}] 订单已成交: {order_id} | 价格: {order.avg_price:.2f}")
                                trade = {
                                    'time': data.timestamp.isoformat(),
                                    'side': sig.side.value if hasattr(sig.side, 'value') else str(sig.side),
                                    'size': order.filled_size,
                                    'price': order.avg_price,
                                    'fee': getattr(order, 'fee', 0),
                                    'type': 'BUY' if 'buy' in str(sig.side).lower() else 'SELL',
                                    'reason': getattr(sig, 'reason', ''),
                                    'symbol': data.symbol,
                                    'quote_amount': order.filled_size * order.avg_price,
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

        # 数据推送部分（始终执行）
        self._push_dashboard(slot, data, context)

    # ------------------------------------------------------------
    # Dashboard 推送
    # ------------------------------------------------------------

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
            if len(hc) > 2000:
                hc.pop(0)

        hrsi = slot_cache.get('history_rsi', [])
        if hrsi and hrsi[-1]['t'] == candle['t']:
            hrsi[-1]['v'] = rsi_val
        else:
            hrsi.append({'t': candle['t'], 'v': rsi_val})
            if len(hrsi) > 2000:
                hrsi.pop(0)

        heq = slot_cache.get('history_equity', [])
        if heq and heq[-1]['t'] == candle['t']:
            heq[-1]['v'] = total_value
        else:
            heq.append({'t': candle['t'], 'v': total_value})
            if len(heq) > 2000:
                heq.pop(0)

        # 实时维护 MACD 历史缓存
        hmacd = slot_cache.get('history_macd', [])
        ts_ms = candle['t']
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
            if len(hmacd) > 2000:
                hmacd.pop(0)
        slot_cache['history_macd'] = hmacd

        self.dashboard.update(dashboard_data, strategy_id=slot.slot_id)

        # 终端摘要打印 (节流控制：每 15 个 bar 打印一次，约 30 秒)
        if not hasattr(self, '_summary_counter'):
            self._summary_counter = 0
        self._summary_counter += 1
        
        if self._summary_counter % 5 == 0:
            # 这里的打印会在所有 slot 处理完后触发一次吗？
            # 实际上由于 update 会并发或顺序调用，我们只需要在一个特定的 slot 或者全局计数器下打印一次
            # 简单起见，如果当前是已知存在的第一个 slot，就打印所有运行中的 slot 摘要
            first_slot_id = next(iter(self._slots))
            if slot.slot_id == first_slot_id:
                now_str = datetime.now().strftime('%H:%M:%S')
                summary = f"[{now_str}] ═╤ 市场: {data.symbol} ${data.close:,.2f} ╤═"
                for s_id, s_slot in self._slots.items():
                    status_flag = "[运行中]" if s_slot.is_running and not s_slot.is_paused else "[已暂停]"
                    # 从已有数据中提取关键指标
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

    # ------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------

    def _save_slot(self, slot: StrategySlot):
        try:
            # 1. 保存 Executor 状态
            slot.executor.save_state(slot.state_file)
            
            # 2. 追加保存 Slot 运行元数据（确保重启后能自动恢复运行）
            import json
            import os
            if os.path.exists(slot.state_file):
                with open(slot.state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                
                state_data['slot_metadata'] = {
                    'is_running': slot.is_running,
                    'is_paused': slot.is_paused,
                    'last_save_time': datetime.now().isoformat()
                }

                # 3. 保存策略内部状态 (网格槽位等)
                if hasattr(slot.strategy, 'get_state'):
                    state_data['strategy_state'] = slot.strategy.get_state()
                
                with open(slot.state_file, 'w', encoding='utf-8') as f:
                    json.dump(state_data, f, indent=4, ensure_ascii=False, default=str)
        except Exception as e:
            print(f"[Slot:{slot.slot_id}] 保存账户状态及元数据失败: {e}")
        try:
            import json
            with open(slot.trades_file, 'w') as f:
                json.dump(self._trades[slot.slot_id], f, ensure_ascii=False, default=str)
        except Exception as e:
            print(f"[Slot:{slot.slot_id}] 保存交易记录失败: {e}")

    def perform_warmup(self, feed: Any):
        """执行统一预热流水线，并同步历史指标到 Dashboard"""
        # 1. 查找最大需求
        max_warmup = 0
        for slot in self._slots.values():
            max_warmup = max(max_warmup, getattr(slot.strategy, 'warmup_bars', 0))
        
        if max_warmup <= 0:
            return

        print(f"[Runner] 开始预热流水线: 最大需求 {max_warmup} 根 K 线")
        
        # 2. 从 feed 获取数据
        if hasattr(feed, 'get_history'):
            data_list = feed.get_history(limit=max_warmup)
            if not data_list:
                print("[Runner] 预热失败: 未能获取到历史数据")
                return
                
            # 3. 分发给各策略执行并收集指标
            for slot in self._slots.values():
                count = getattr(slot.strategy, 'warmup_bars', 0)
                if count > 0:
                    needed_data = data_list[-count:]
                    print(f"[Runner] 正在预热策略 [{slot.slot_id}]: {len(needed_data)} bars")
                    
                    h_candles, h_rsi, h_equity, h_macd = [], [], [], []
                    
                    # 权益回溯初始化
                    sim_cash = slot.initial_balance
                    sim_pos = 0.0
                    trades_sorted = sorted(self._trades.get(slot.slot_id, []), key=lambda x: str(x.get('time', '')))
                    trade_idx = 0

                    for bar in needed_data:
                        # 喂给策略 (context=None 表示预热模式)
                        slot.strategy.on_data(bar, None)
                        
                        # 同步已成交记录进行权益逆推
                        while trade_idx < len(trades_sorted):
                            t = trades_sorted[trade_idx]
                            try:
                                t_time = t['time']
                                if isinstance(t_time, str):
                                    from datetime import datetime
                                    # 先尝试 ISO 格式。如果含有 Z，Python 3.11+ 的 fromisoformat 能识别，但为了兼容性统一处理
                                    t_dt = datetime.fromisoformat(t_time.replace('Z', '+00:00'))
                                    if t_dt.tzinfo is None:
                                        t_dt = t_dt.replace(tzinfo=timezone.utc)
                                    # 确保转为 UTC
                                    t_dt = t_dt.astimezone(timezone.utc)
                                else:
                                    t_dt = t_time
                                    if t_dt.tzinfo is None:
                                        t_dt = t_dt.replace(tzinfo=timezone.utc)
                                    t_dt = t_dt.astimezone(timezone.utc)
                                
                                # 确保 bar.timestamp 也是 Aware
                                bar_ts = bar.timestamp
                                if bar_ts.tzinfo is None:
                                    bar_ts = bar_ts.replace(tzinfo=timezone.utc)
                                
                                if t_dt <= bar_ts:
                                    side = str(t.get('side', '')).lower()
                                    size = float(t.get('size', 0))
                                    price = float(t.get('price', 0))
                                    fee = float(t.get('fee', 0) or 0)
                                    if 'buy' in side:
                                        sim_cash -= (size * price + fee)
                                        sim_pos += size
                                    else:
                                        sim_cash += (size * price - fee)
                                        sim_pos -= size
                                    trade_idx += 1
                                else:
                                    break
                            except Exception:
                                trade_idx += 1

                        # 收集该时刻的指标快照
                        ts_ms = int(bar.timestamp.timestamp() * 1000)
                        status = slot.strategy.get_status(None)
                        
                        h_candles.append({
                            't': ts_ms, 'o': bar.open, 'h': bar.high, 'l': bar.low, 'c': bar.close, 'v': bar.volume
                        })
                        h_rsi.append({'t': ts_ms, 'v': status.get('current_rsi')})
                        
                        # 计算即时权益
                        equity = sim_cash + sim_pos * bar.close
                        h_equity.append({'t': ts_ms, 'v': equity})
                        
                        h_macd.append({
                            'time': ts_ms,
                            'macd': status.get('macd'),
                            'macdsignal': status.get('macdsignal'),
                            'macdhist': status.get('macdhist')
                        })
                    
                    # 推送完整历史到 Dashboard
                    self.push_warmup(slot, h_candles, h_rsi, h_equity, h_macd)
                    
            print("[Runner] 预热流水线执行完毕")
        else:
            print("[Runner] 预热中止: DataFeed 不支持 get_history 接口")

    def save_all(self):
        for slot in self._slots.values():
            self._save_slot(slot)

    def stop(self):
        """停止所有策略并保存状态"""
        print("[Runner] 正在停止所有策略并保存状态...")
        for slot in self._slots.values():
            slot.stop()
        self.save_all()
        if self.dashboard:
            print("[Runner] 正在关闭 Dashboard 回调...")
            self.dashboard.on_control_callback = None
