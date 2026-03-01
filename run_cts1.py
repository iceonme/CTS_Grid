"""
CTS1 多策略启动入口

功能：
- 单一 OKX 数据流广播给所有策略
- 前端可选择策略、启动/暂停/重置
- 每个策略独立账户、持久化、房间

使用方法:
    python run_cts1.py
"""

import sys
import os
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategies import GridRSIStrategy, GridRSIStrategyV5_1
from executors.paper import PaperExecutor
from datafeeds import OKXDataFeed
from dashboard import create_dashboard
from runner import MultiStrategyRunner, StrategySlot
from config.api_config import OKX_DEMO_CONFIG, DEFAULT_SYMBOL, DEFAULT_TIMEFRAME

# ──────────────────────────────────────────────────────────────
# 策略目录（可在此添加更多策略）
# ──────────────────────────────────────────────────────────────
INITIAL_BALANCE = 10000.0

STRATEGY_CATALOG = {
    'grid_v40': {
        'display_name': 'Grid RSI V4.0 (模拟盘)',
        'cls': GridRSIStrategy,
        'params': {
            'symbol': DEFAULT_SYMBOL,
            'grid_levels': 10,
            'use_kelly_sizing': True,
            'trailing_stop': True,
        }
    },
    'grid_v51': {
        'display_name': 'Grid RSI V5.1 (模拟盘)',
        'cls': GridRSIStrategyV5_1,
        'params': {
            'symbol': DEFAULT_SYMBOL,
            'grid_levels': 10,
            'use_kelly_sizing': True,
            'trailing_stop': True,
        }
    },
}


def build_history_data(strategy, initial_balance, trades_sorted):
    """从策略数据缓冲区重建历史快照"""
    history_candles = []
    history_rsi = []
    history_equity = []
    history_macd = []

    from core import Side
    sim_cash = initial_balance
    sim_pos = 0.0
    trade_idx = 0

    for i, data in enumerate(strategy._data_buffer):
        ts_ms = int(data.timestamp.timestamp() * 1000)

        history_candles.append({
            't': ts_ms, 'o': data.open, 'h': data.high,
            'l': data.low, 'c': data.close
        })

        if i >= strategy.params.get('rsi_period', 14):
            df = strategy._get_dataframe()
            if i < len(df):
                rsi = strategy._calculate_rsi(df['close'].iloc[:i+1])
                history_rsi.append({'t': ts_ms, 'v': float(rsi) if rsi is not None else None})
                
                # 计算 MACD
                if hasattr(strategy, '_calculate_macd'):
                    macd_item = {'time': ts_ms, 'macd': None, 'macdsignal': None, 'macdhist': None}
                    try:
                        ml, sl, hi = strategy._calculate_macd(df.iloc[:i+1])
                        macd_item = {
                            'time': ts_ms,
                            'macd': float(ml) if ml is not None else None,
                            'macdsignal': float(sl) if sl is not None else None,
                            'macdhist': float(hi) if hi is not None else None
                        }
                    except Exception:
                        pass
                    history_macd.append(macd_item)
                else:
                    # 策略不支持 MACD 时也要占位对齐
                    history_macd.append({'time': ts_ms, 'macd': None, 'macdsignal': None, 'macdhist': None})
            else:
                history_rsi.append({'t': ts_ms, 'v': None})
                history_macd.append({'time': ts_ms, 'macd': None, 'macdsignal': None, 'macdhist': None})
        else:
            history_rsi.append({'t': ts_ms, 'v': None})
            # 前期数据不足时也要为 MACD 占位，确保时间轴与 K 线完全对齐
            history_macd.append({'time': ts_ms, 'macd': None, 'macdsignal': None, 'macdhist': None})

        while trade_idx < len(trades_sorted):
            t = trades_sorted[trade_idx]
            try:
                from datetime import datetime, timezone
                t_dt = datetime.fromisoformat(str(t.get('time', '')).replace('Z', '+00:00'))
                t_ms = int(t_dt.timestamp() * 1000)
                if t_ms <= ts_ms:
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

        equity = sim_cash + sim_pos * data.close
        history_equity.append({'t': ts_ms, 'v': equity})

    return history_candles, history_rsi, history_equity, history_macd


def main():
    print("\n" + "="*60)
    print("CTS1 — 多策略并发模拟盘")
    print("="*60)
    print(f"交易对: {DEFAULT_SYMBOL} | 周期: {DEFAULT_TIMEFRAME}")
    print(f"API Key: {OKX_DEMO_CONFIG['api_key'][:8]}...")
    print("="*60 + "\n")

    # 1. 启动 Dashboard
    print("[1/4] 启动 Dashboard...")
    dashboard = create_dashboard(port=5000)
    dashboard.start_background()
    time.sleep(1)

    # 2. 创建 Runner + 策略槽
    print("[2/4] 初始化策略...")
    runner = MultiStrategyRunner(dashboard=dashboard)

    for slot_id, cfg in STRATEGY_CATALOG.items():
        strategy = cfg['cls'](**cfg['params'])
        executor = PaperExecutor(
            initial_capital=INITIAL_BALANCE,
            fee_rate=0.0,
            slippage_model='none'
        )
        slot = StrategySlot(
            slot_id=slot_id,
            display_name=cfg['display_name'],
            strategy=strategy,
            executor=executor,
            initial_balance=INITIAL_BALANCE,
        )
        runner.add_slot(slot)
        print(f"  [OK] {slot_id}: {cfg['display_name']}")

    # 3. OKX 数据流（单一连接，广播用）
    print("[3/4] 启动数据流...")
    data_feed = OKXDataFeed(
        symbol=DEFAULT_SYMBOL,
        timeframe=DEFAULT_TIMEFRAME,
        api_key=OKX_DEMO_CONFIG['api_key'],
        api_secret=OKX_DEMO_CONFIG['api_secret'],
        passphrase=OKX_DEMO_CONFIG['passphrase'],
        is_demo=True,
        poll_interval=2.0
    )

    # 4. 预热：用 LiveEngine 拉取历史数据，分发给所有槽
    print("[4/4] 预热策略...")
    from engines import LiveEngine

    warmup_feed = OKXDataFeed(
        symbol=DEFAULT_SYMBOL,
        timeframe=DEFAULT_TIMEFRAME,
        api_key=OKX_DEMO_CONFIG['api_key'],
        api_secret=OKX_DEMO_CONFIG['api_secret'],
        passphrase=OKX_DEMO_CONFIG['passphrase'],
        is_demo=True,
        poll_interval=2.0
    )
    # 用第一个槽的策略做预热（获取 _data_buffer），之后共享给所有槽
    first_slot = next(iter(runner._slots.values())) if runner._slots else None
    warmup_done = False
    if first_slot:
        warmup_engine = LiveEngine(
            strategy=first_slot.strategy,
            executor=first_slot.executor,
            data_feed=warmup_feed,
            warmup_bars=200
        )
        warmup_done = warmup_engine.warmup()

    if warmup_done and first_slot and first_slot.strategy._data_buffer:
        print(f"  获取 {len(first_slot.strategy._data_buffer)} 根历史 K 线")
        trades_sorted = sorted(runner._trades.get(first_slot.slot_id, []),
                               key=lambda x: str(x.get('time', '')))
        hc, hrsi, heq, hmacd = build_history_data(
            first_slot.strategy, INITIAL_BALANCE, trades_sorted)
        runner.push_warmup(first_slot, hc, hrsi, heq, hmacd)

        # 将历史数据同步到其余槽
        for slot_id, slot in runner._slots.items():
            if slot is first_slot:
                continue
            for candle in first_slot.strategy._data_buffer:
                slot.strategy._data_buffer.append(candle)
            slot_trades = sorted(runner._trades.get(slot_id, []),
                                 key=lambda x: str(x.get('time', '')))
            hc2, hrsi2, heq2, hmacd2 = build_history_data(slot.strategy, INITIAL_BALANCE, slot_trades)
            runner.push_warmup(slot, hc2, hrsi2, heq2, hmacd2)
    else:
        print("  警告: 未能预热，将使用实时数据启动")

    # 5. 注册 Dashboard 控制回调
    def on_control(action: str, strategy_id: str):
        print(f"[Dashboard] 控制事件: {action} → {strategy_id}")
        if action == 'start':
            runner.start(strategy_id)
        elif action == 'pause':
            runner.pause(strategy_id)
        elif action == 'reset':
            runner.reset(strategy_id)

    dashboard.on_control_callback = on_control

    print("\n" + "="*60)
    print("    >> Dashboard: http://localhost:5000")
    print("    >> 请在 Dashboard 选择策略并点击 [启动]")
    print("="*60 + "\n")

    # 6. 主循环：驱动数据流，广播给 Runner
    try:
        for market_data in data_feed.stream():
            runner.on_bar(market_data)
    except KeyboardInterrupt:
        print("\n正在停止...")
        runner.save_all()
        print("已保存所有策略状态，退出。")

    return 0


if __name__ == '__main__':
    sys.exit(main())
