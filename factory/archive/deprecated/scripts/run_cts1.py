"""
CTS1 澶氱瓥鐣ュ惎鍔ㄥ叆鍙?

鍔熻兘锛?
- 鍗曚竴 OKX 鏁版嵁娴佸箍鎾粰鎵€鏈夌瓥鐣?
- 鍓嶇鍙€夋嫨绛栫暐銆佸惎鍔?鏆傚仠/閲嶇疆
- 姣忎釜绛栫暐鐙珛璐︽埛銆佹寔涔呭寲銆佹埧闂?

浣跨敤鏂规硶:
    python run_cts1.py
"""

import sys
import os
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cartridges.strategies import GridRSIStrategy, GridRSIStrategyV5_2
from cartridges.bridge.executors.paper import PaperExecutor
from cartridges.bridge.datafeeds import OKXDataFeed
from console.dashboard import create_dashboard
from console.runner import MultiStrategyRunner, StrategySlot
from infra.config.api_config import OKX_DEMO_CONFIG, DEFAULT_SYMBOL, DEFAULT_TIMEFRAME

# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# 绛栫暐鐩綍锛堝彲鍦ㄦ娣诲姞鏇村绛栫暐锛?
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
INITIAL_BALANCE = 10000.0

STRATEGY_CATALOG = {
    'grid_v40': {
        'display_name': 'Grid RSI V4.0 (妯℃嫙鐩?',
        'cls': GridRSIStrategy,
        'params': {
            'symbol': DEFAULT_SYMBOL,
            'grid_levels': 10,
            'use_kelly_sizing': True,
            'trailing_stop': True,
        }
    },
    'grid_v52': {
        'display_name': 'Grid RSI V5.2 (妯℃嫙鐩?',
        'cls': GridRSIStrategyV5_2,
        'params': {
            'symbol': DEFAULT_SYMBOL,
            'grid_levels': 10,
            'use_kelly_sizing': True,
            'trailing_stop': True,
        }
    },
}


def build_history_data(strategy, initial_balance, trades_sorted):
    """浠庣瓥鐣ユ暟鎹紦鍐插尯閲嶅缓鍘嗗彶蹇収"""
    history_candles = []
    history_rsi = []
    history_equity = []
    history_macd = []

    from console.core import Side
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
                
                # 璁＄畻 MACD
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
                    # 绛栫暐涓嶆敮鎸?MACD 鏃朵篃瑕佸崰浣嶅榻?
                    history_macd.append({'time': ts_ms, 'macd': None, 'macdsignal': None, 'macdhist': None})
            else:
                history_rsi.append({'t': ts_ms, 'v': None})
                history_macd.append({'time': ts_ms, 'macd': None, 'macdsignal': None, 'macdhist': None})
        else:
            history_rsi.append({'t': ts_ms, 'v': None})
            # 鍓嶆湡鏁版嵁涓嶈冻鏃朵篃瑕佷负 MACD 鍗犱綅锛岀‘淇濇椂闂磋酱涓?K 绾垮畬鍏ㄥ榻?
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
    print("CTS1 鈥?澶氱瓥鐣ュ苟鍙戞ā鎷熺洏")
    print("="*60)
    print(f"浜ゆ槗瀵? {DEFAULT_SYMBOL} | 鍛ㄦ湡: {DEFAULT_TIMEFRAME}")
    print(f"API Key: {OKX_DEMO_CONFIG['api_key'][:8]}...")
    print("="*60 + "\n")

    # 1. 鍚姩 Dashboard
    print("[1/4] 鍚姩 Dashboard...")
    dashboard = create_dashboard(port=5051)
    dashboard.start_background()
    time.sleep(1)

    # 2. 鍒涘缓 Runner + 绛栫暐妲?
    print("[2/4] 鍒濆鍖栫瓥鐣?..")
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

    # 3. OKX 鏁版嵁娴侊紙鍗曚竴杩炴帴锛屽箍鎾敤锛?
    print("[3/4] 鍚姩鏁版嵁娴?..")
    data_feed = OKXDataFeed(
        symbol=DEFAULT_SYMBOL,
        timeframe=DEFAULT_TIMEFRAME,
        api_key=OKX_DEMO_CONFIG['api_key'],
        api_secret=OKX_DEMO_CONFIG['api_secret'],
        passphrase=OKX_DEMO_CONFIG['passphrase'],
        is_demo=True,
        poll_interval=2.0
    )

    # 4. 棰勭儹锛氱敤 LiveEngine 鎷夊彇鍘嗗彶鏁版嵁锛屽垎鍙戠粰鎵€鏈夋Ы
    print("[4/4] 棰勭儹绛栫暐...")
    from console.engines import LiveEngine

    warmup_feed = OKXDataFeed(
        symbol=DEFAULT_SYMBOL,
        timeframe=DEFAULT_TIMEFRAME,
        api_key=OKX_DEMO_CONFIG['api_key'],
        api_secret=OKX_DEMO_CONFIG['api_secret'],
        passphrase=OKX_DEMO_CONFIG['passphrase'],
        is_demo=True,
        poll_interval=2.0
    )
    # 鐢ㄧ涓€涓Ы鐨勭瓥鐣ュ仛棰勭儹锛堣幏鍙?_data_buffer锛夛紝涔嬪悗鍏变韩缁欐墍鏈夋Ы
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
        print(f"  鑾峰彇 {len(first_slot.strategy._data_buffer)} 鏍瑰巻鍙?K 绾?)
        trades_sorted = sorted(runner._trades.get(first_slot.slot_id, []),
                               key=lambda x: str(x.get('time', '')))
        hc, hrsi, heq, hmacd = build_history_data(
            first_slot.strategy, INITIAL_BALANCE, trades_sorted)
        runner.push_warmup(first_slot, hc, hrsi, heq, hmacd)

        # 灏嗗巻鍙叉暟鎹悓姝ュ埌鍏朵綑妲?
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
        print("  璀﹀憡: 鏈兘棰勭儹锛屽皢浣跨敤瀹炴椂鏁版嵁鍚姩")

    # 5. 娉ㄥ唽 Dashboard 鎺у埗鍥炶皟
    def on_control(action: str, strategy_id: str):
        print(f"[Dashboard] 鎺у埗浜嬩欢: {action} 鈫?{strategy_id}")
        if action == 'start':
            runner.start(strategy_id)
        elif action == 'pause':
            runner.pause(strategy_id)
        elif action == 'reset':
            runner.reset(strategy_id)

    dashboard.on_control_callback = on_control

    print("\n" + "="*60)
    print("    >> Dashboard: http://localhost:5051")
    print("    >> 璇峰湪 Dashboard 閫夋嫨绛栫暐骞剁偣鍑?[鍚姩]")
    print("="*60 + "\n")

    # 6. 涓诲惊鐜細椹卞姩鏁版嵁娴侊紝骞挎挱缁?Runner
    try:
        for market_data in data_feed.stream():
            runner.on_bar(market_data)
    except KeyboardInterrupt:
        print("\n姝ｅ湪鍋滄...")
        runner.save_all()
        print("宸蹭繚瀛樻墍鏈夌瓥鐣ョ姸鎬侊紝閫€鍑恒€?)

    return 0


if __name__ == '__main__':
    sys.exit(main())
