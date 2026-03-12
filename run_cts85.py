
import sys
import os
import time
import json
from pathlib import Path
from datetime import datetime, timedelta

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategies.grid_v85 import GridStrategyV85
from executors.paper import PaperExecutor
from datafeeds import OKXDataFeed
from dashboard_85.server_85 import create_dashboard_85
from runner import MultiStrategyRunner, StrategySlot
from config.api_config import OKX_DEMO_CONFIG, DEFAULT_SYMBOL

# ──────────────────────────────────────────────────────────────
# 策略配置
# ──────────────────────────────────────────────────────────────
INITIAL_BALANCE = 10000.0
base_dir = os.path.dirname(os.path.abspath(__file__))
V85_RUNTIME_PATH = os.path.join(base_dir, 'config', 'grid_v85_btc_runtime.json')
V85_FACTORY_PATH = os.path.join(base_dir, 'config', 'grid_v85_btc_default.json')

STRATEGY_CATALOG = {
    'grid_v85': {
        'display_name': 'Grid V8.5 (Jeff 版)',
        'cls': GridStrategyV85,
        'params': {
            'symbol': DEFAULT_SYMBOL,
            'initial_capital': INITIAL_BALANCE,
            'verbose': True
        }
    }
}

def build_history_data(strategy_cls, strategy_params, initial_balance, trades_sorted, data_main):
    """重建 V8.5 数据历史 (参考 V8.0 实现)"""
    history_candles = []
    history_rsi = []
    history_equity = []

    temp_strat = strategy_cls(**strategy_params)
    # V8.5 不需要显式 initialize, 它在 on_data 中处理预热
    
    sim_cash = float(initial_balance)
    sim_pos = 0.0
    trade_idx = 0

    print(f"[V8.5] 重建指标历史 ({len(data_main)} bars)...")
    
    for i, data in enumerate(data_main):
        ts_ms = int(data.timestamp.timestamp() * 1000)

        # 更新指标
        temp_strat.on_data(data, None)
        
        # 记录 K 线
        history_candles.append({
            't': ts_ms, 'o': data.open, 'h': data.high,
            'l': data.low, 'c': data.close, 'v': data.volume
        })
        
        status = temp_strat.get_status()
        history_rsi.append({'t': ts_ms, 'v': status.get('rsi')})

        # 更新权益 (简单模拟)
        while trade_idx < len(trades_sorted):
            t = trades_sorted[trade_idx]
            try:
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

    return history_candles, history_rsi, history_equity, []


def main():
    print("\n" + "="*60)
    print("CTS 8.5 — 策略运行环境 (V8.5 Jeff 版 动态网格)")
    print("="*60)
    
    # 1. 配置加载 (V8.5 暂不强制使用 runtime.json, 先直接从代码参数启动，后续可扩展热加载)
    # 这里我们还是保留 runtime 逻辑，方便用户在 Dashboard 修改
    if not os.path.exists(V85_RUNTIME_PATH) and os.path.exists(V85_FACTORY_PATH):
        import shutil
        shutil.copy(V85_FACTORY_PATH, V85_RUNTIME_PATH)
        print(f"[系统] 已从默认配置同步: {V85_RUNTIME_PATH}")

    # 2. 启动 Dashboard (Port: 5085)
    dashboard = create_dashboard_85(port=5085)
    dashboard.start_background()

    # 3. 初始化 Runner
    runner = MultiStrategyRunner(dashboard=dashboard)
    for slot_id, cfg in STRATEGY_CATALOG.items():
        # 加载运行时参数 (如果存在)
        params = cfg['params'].copy()
        if os.path.exists(V85_RUNTIME_PATH):
            with open(V85_RUNTIME_PATH, 'r', encoding='utf-8') as f:
                runtime_config = json.load(f)
                params.update(runtime_config)
        
        strategy = cfg['cls'](**params)
        executor = PaperExecutor(initial_capital=INITIAL_BALANCE)
        slot = StrategySlot(
            slot_id=slot_id,
            display_name=cfg['display_name'],
            strategy=strategy,
            executor=executor,
            initial_balance=INITIAL_BALANCE,
            state_file=f"trading_state_{slot_id}_v85.json",
            trades_file=f"trading_trades_{slot_id}_v85.json"
        )
        runner.add_slot(slot)

    # 4. 数据流 (1m)
    data_feed = OKXDataFeed(
        symbol=DEFAULT_SYMBOL,
        timeframe='1m',
        api_key=OKX_DEMO_CONFIG['api_key'],
        api_secret=OKX_DEMO_CONFIG['api_secret'],
        passphrase=OKX_DEMO_CONFIG['passphrase'],
        is_demo=True,
        record_to=f"data/market/{DEFAULT_SYMBOL.replace('-', '_')}_1m.csv"
    )

    # 5. 预热 (V8.5 需要 4h = 240 bars, 预留 300 bars)
    print("[V8.5] 预热数据中...")
    from engines import LiveEngine
    first_slot = next(iter(runner._slots.values()))
    warmup_engine = LiveEngine(first_slot.strategy, first_slot.executor, data_feed, warmup_bars=300)
    
    if warmup_engine.warmup():
        data_main = list(first_slot.strategy._data_1m) # V8.5 已重构为 _data_1m
        trades_sorted = sorted(runner._trades.get(first_slot.slot_id, []), key=lambda x: str(x.get('time', '')))
        hc, hrsi, heq, hmacd = build_history_data(GridStrategyV85, STRATEGY_CATALOG['grid_v85']['params'], INITIAL_BALANCE, trades_sorted, data_main)
        runner.push_warmup(first_slot, hc, hrsi, heq, hmacd)
        print(f"[V8.5] 预热完成: {len(hc)} 根历史数据")

    # 6. 控制回调
    def on_control(action: str, str_id: str, **kwargs):
        print(f"[V8.5 Control] 接收控制指令: action={action}, str_id={str_id}, data={kwargs.get('data')}")
        try:
            if action == 'save_params':
                new_params = kwargs.get('data')
                slot = runner._slots.get(str_id)
                if slot and new_params:
                    # 更新 Runtime JSON
                    config = {}
                    if os.path.exists(V85_RUNTIME_PATH):
                        with open(V85_RUNTIME_PATH, 'r', encoding='utf-8') as f: config = json.load(f)
                    config.update(new_params)
                    with open(V85_RUNTIME_PATH, 'w', encoding='utf-8') as f: json.dump(config, f, indent=2)
                    
                    # 热更新内存中的策略对象
                    for k, v in new_params.items():
                        if hasattr(slot.strategy, k):
                            setattr(slot.strategy, k, v)
                    print(f"[V8.5] 参数已热更新: {str_id}")
            elif action in ['start', 'pause', 'reset']:
                func = getattr(runner, action, None)
                if func:
                    func(str_id)
                    print(f"[V8.5] 指令执行成功: {action} ({str_id})")
        except Exception as e:
            print(f"[V8.5 Error] 控制回调失败: {e}")

    dashboard.on_control_callback = on_control

    print("\n[V8.5] 顺利启动! 请访问 http://localhost:5085")
    
    while True:
        try:
            for market_data in data_feed.stream():
                if market_data:
                    runner.on_bar(market_data)
        except KeyboardInterrupt:
            runner.save_all()
            print("\n退出中...")
            break
        except Exception as e:
            print(f"\n[V8.5 Error] 数据流异常: {e}")
            time.sleep(5)
            runner.save_all()

    return 0

if __name__ == '__main__':
    sys.exit(main())
