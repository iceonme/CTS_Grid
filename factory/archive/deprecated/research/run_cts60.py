
import sys
import os
import time
import json
from pathlib import Path

# 纭繚椤圭洰鏍圭洰褰曞湪 path 涓?
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cartridges.strategies import GridMTFStrategyV6_0
from cartridges.bridge.executors.paper import PaperExecutor
from cartridges.bridge.datafeeds import OKXDataFeed
from console.dashboard.server_60 import create_dashboard_60
from console.runner import MultiStrategyRunner, StrategySlot
from infra.config.api_config import OKX_DEMO_CONFIG, DEFAULT_SYMBOL, DEFAULT_TIMEFRAME

# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# 绛栫暐閰嶇疆
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
INITIAL_BALANCE = 10000.0
V60_RUNTIME_PATH = "config/grid_v60_runtime.json"
V60_FACTORY_PATH = "config/grid_v60_default.json"

STRATEGY_CATALOG = {
    'grid_v60': {
        'display_name': 'Grid MTF V6.0 (JeffHuang Optimized)',
        'cls': GridMTFStrategyV6_0,
        'params': {
            'symbol': DEFAULT_SYMBOL,
            'config_path': V60_RUNTIME_PATH,
        }
    }
}

def build_history_data(strategy_cls, strategy_params, initial_balance, trades_sorted, data_source):
    """閲嶅缓 V6.0 MTF 鎸囨爣鍘嗗彶"""
    history_candles = []
    history_rsi = []
    history_equity = []
    history_macd = []

    temp_strat = strategy_cls(**strategy_params)
    temp_strat.initialize()

    sim_cash = initial_balance
    sim_pos = 0.0
    trade_idx = 0

    print(f"[V6.0] 閲嶅缓鎸囨爣鍘嗗彶 ({len(data_source)} bars)...")
    
    for i, data in enumerate(data_source):
        ts_ms = int(data.timestamp.timestamp() * 1000)

        # 鏇存柊鎸囨爣
        temp_strat.on_data(data, None)
        
        # 璁板綍 5m K绾?
        history_candles.append({
            't': ts_ms, 'o': data.open, 'h': data.high,
            'l': data.low, 'c': data.close, 'v': data.volume
        })
        
        status = temp_strat.get_status()
        history_rsi.append({'t': ts_ms, 'v': status.get('current_rsi')})
        history_macd.append({
            'time': ts_ms,
            'macd': status.get('macd'),
            'macdsignal': status.get('macdsignal'),
            'macdhist': status.get('macdhist')
        })

        # 鏇存柊鏉冪泭 (绠€鍗曟ā鎷?
        while trade_idx < len(trades_sorted):
            t = trades_sorted[trade_idx]
            try:
                from datetime import datetime
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
                else: break
            except: trade_idx += 1

        equity = sim_cash + sim_pos * data.close
        history_equity.append({'t': ts_ms, 'v': equity})

    return history_candles, history_rsi, history_equity, history_macd


def main():
    print("\n" + "="*60)
    print("CTS 6.0 鈥?绛栫暐杩愯鐜 (V6.0 MTF 涓撶敤)")
    print("="*60)
    
    # 1. 閰嶇疆妫€鏌?
    config_path = Path(V60_RUNTIME_PATH)
    if not config_path.exists():
        factory_path = Path(V60_FACTORY_PATH)
        if factory_path.exists():
            import shutil
            shutil.copy(factory_path, config_path)
            print(f"[绯荤粺] 宸插垵濮嬪寲杩愯閰嶇疆: {config_path}")

    # 2. 鍚姩 Dashboard (Port: 5066)
    dashboard = create_dashboard_60(port=5066)
    dashboard.start_background()

    # 3. 鍒濆鍖?Runner
    runner = MultiStrategyRunner(dashboard=dashboard)
    for slot_id, cfg in STRATEGY_CATALOG.items():
        strategy = cfg['cls'](**cfg['params'])
        executor = PaperExecutor(initial_capital=INITIAL_BALANCE)
        slot = StrategySlot(
            slot_id=slot_id,
            display_name=cfg['display_name'],
            strategy=strategy,
            executor=executor,
            initial_balance=INITIAL_BALANCE,
            state_file=f"trading_state_{slot_id}_v60.json",
            trades_file=f"trading_trades_{slot_id}_v60.json"
        )
        runner.add_slot(slot)

    # 4. 鏁版嵁娴?
    data_feed = OKXDataFeed(
        symbol=DEFAULT_SYMBOL,
        timeframe='1m',
        api_key=OKX_DEMO_CONFIG['api_key'],
        api_secret=OKX_DEMO_CONFIG['api_secret'],
        passphrase=OKX_DEMO_CONFIG['passphrase'],
        is_demo=True,
        record_to=f"data/market/{DEFAULT_SYMBOL.replace('-', '_')}_1m.csv"
    )

    # 5. 棰勭儹 (200 bars for 15m MACD and 6h lookback)
    print("[V6.0] 棰勭儹鏁版嵁涓?..")
    from console.engines import LiveEngine
    first_slot = next(iter(runner._slots.values()))
    warmup_engine = LiveEngine(first_slot.strategy, first_slot.executor, data_feed, warmup_bars=360)
    
    if warmup_engine.warmup():
        data_source = list(first_slot.strategy._data_1m)
        print(f"[V6.0] 棰勭儹鎴愬姛锛屽叡鑾峰彇 {len(data_source)} 鏉″巻鍙?1m K绾?)
        trades_sorted = sorted(runner._trades.get(first_slot.slot_id, []), key=lambda x: str(x.get('time', '')))
        hc, hrsi, heq, hmacd = build_history_data(GridMTFStrategyV6_0, STRATEGY_CATALOG['grid_v60']['params'], INITIAL_BALANCE, trades_sorted, data_source)
        runner.push_warmup(first_slot, hc, hrsi, heq, hmacd)
        print(f"[V6.0] 棰勭儹瀹屾垚: {len(hc)} 鏍瑰巻鍙叉暟鎹?)
    else:
        print("\n[V6.0 Error] 绛栫暐棰勭儹澶辫触锛佹湭鑳戒粠 OKX 鑾峰彇蹇呰鐨勫巻鍙叉暟鎹€?)
        print("璇锋鏌ワ細\n1. 缃戠粶杩炴帴鏄惁绋冲畾锛堟捣澶栫嚎璺?VPN锛塡n2. API Key 鏉冮檺鏄惁鍖呭惈 'Read'\n3. 浜ゆ槗瀵?symbol 鍚嶇О鏄惁姝ｇ‘")
        return 1

    # 6. 鎺у埗鍥炶皟
    def on_control(action: str, str_id: str, **kwargs):
        print(f"[V6.0 Control] 鎺ユ敹鎺у埗鎸囦护: action={action}, str_id={str_id}, data={kwargs.get('data')}")
        try:
            if action == 'save_params':
                new_params = kwargs.get('data')
                slot = runner._slots.get(str_id)
                if slot and new_params:
                    cp = getattr(slot.strategy, 'params_path', V60_RUNTIME_PATH)
                    with open(cp, 'r', encoding='utf-8') as f: config = json.load(f)
                    config.update(new_params)
                    with open(cp, 'w', encoding='utf-8') as f: json.dump(config, f, indent=2)
                    if hasattr(slot.strategy, '_load_params'): slot.strategy._load_params()
                    print(f"[V6.0] 鍙傛暟宸茬儹鍔犺浇: {str_id}")
            elif action in ['start', 'pause', 'reset']:
                func = getattr(runner, action, None)
                if func:
                    func(str_id)
                    print(f"[V6.0] 鎸囦护鎵ц鎴愬姛: {action} ({str_id})")
                else:
                    print(f"[V6.0 Error] MultiStrategyRunner 缂哄皯鏂规硶: {action}")
        except Exception as e:
            print(f"[V6.0 Error] 鎺у埗鍥炶皟鎵ц澶辫触: {e}")
            import traceback; traceback.print_exc()

    dashboard.on_control_callback = on_control

    print("\n[V6.0] 椤哄埄鍚姩! 璇疯闂?http://localhost:5066")
    
    while True:
        try:
            for market_data in data_feed.stream():
                if market_data:
                    runner.on_bar(market_data)
        except KeyboardInterrupt:
            runner.save_all()
            print("\n鎺у埗鍙版崟鑾?KeyboardInterrupt锛岀▼搴忔甯搁€€鍑?)
            break
        except Exception as e:
            print(f"\n[V6.0 Error] 鏁版嵁娴佷腑鏂垨澶勭悊寮傚父: {e}")
            import traceback
            traceback.print_exc()
            print("[V6.0] 5绉掑悗灏濊瘯閲嶅惎鏁版嵁娴?..")
            time.sleep(5)
            runner.save_all() # 灏濊瘯淇濆瓨褰撳墠鐘舵€佷互闃插啀娆″穿婧?

    return 0

if __name__ == '__main__':
    sys.exit(main())
