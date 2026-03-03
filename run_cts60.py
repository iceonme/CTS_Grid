
import sys
import os
import time
import json
from pathlib import Path

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategies import GridMTFStrategyV6_0
from executors.paper import PaperExecutor
from datafeeds import OKXDataFeed
from dashboard.server_60 import create_dashboard_60
from runner import MultiStrategyRunner, StrategySlot
from config.api_config import OKX_DEMO_CONFIG, DEFAULT_SYMBOL, DEFAULT_TIMEFRAME

# ──────────────────────────────────────────────────────────────
# 策略配置
# ──────────────────────────────────────────────────────────────
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
    """重建 V6.0 MTF 指标历史"""
    history_candles = []
    history_rsi = []
    history_equity = []
    history_macd = []

    temp_strat = strategy_cls(**strategy_params)
    temp_strat.initialize()

    sim_cash = initial_balance
    sim_pos = 0.0
    trade_idx = 0

    print(f"[V6.0] 重建指标历史 ({len(data_source)} bars)...")
    
    for i, data in enumerate(data_source):
        ts_ms = int(data.timestamp.timestamp() * 1000)

        # 更新指标
        temp_strat.on_data(data, None)
        
        # 记录 5m K线
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

        # 更新权益 (简单模拟)
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
    print("CTS 6.0 — 策略运行环境 (V6.0 MTF 专用)")
    print("="*60)
    
    # 1. 配置检查
    config_path = Path(V60_RUNTIME_PATH)
    if not config_path.exists():
        factory_path = Path(V60_FACTORY_PATH)
        if factory_path.exists():
            import shutil
            shutil.copy(factory_path, config_path)
            print(f"[系统] 已初始化运行配置: {config_path}")

    # 2. 启动 Dashboard (Port: 5066)
    dashboard = create_dashboard_60(port=5066)
    dashboard.start_background()

    # 3. 初始化 Runner
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

    # 4. 数据流
    data_feed = OKXDataFeed(
        symbol=DEFAULT_SYMBOL,
        timeframe='5m',
        api_key=OKX_DEMO_CONFIG['api_key'],
        api_secret=OKX_DEMO_CONFIG['api_secret'],
        passphrase=OKX_DEMO_CONFIG['passphrase'],
        is_demo=True
    )

    # 5. 预热 (200 bars for 15m MACD and 6h lookback)
    print("[V6.0] 预热数据中...")
    from engines import LiveEngine
    first_slot = next(iter(runner._slots.values()))
    warmup_engine = LiveEngine(first_slot.strategy, first_slot.executor, data_feed, warmup_bars=200)
    
    if warmup_engine.warmup():
        data_source = list(first_slot.strategy._data_5m)
        trades_sorted = sorted(runner._trades.get(first_slot.slot_id, []), key=lambda x: str(x.get('time', '')))
        hc, hrsi, heq, hmacd = build_history_data(GridMTFStrategyV6_0, STRATEGY_CATALOG['grid_v60']['params'], INITIAL_BALANCE, trades_sorted, data_source)
        runner.push_warmup(first_slot, hc, hrsi, heq, hmacd)
        print(f"[V6.0] 预热完成: {len(hc)} 根历史数据")

    # 6. 控制回调
    def on_control(action: str, str_id: str, **kwargs):
        print(f"[V6.0 Control] 接收控制指令: action={action}, str_id={str_id}, data={kwargs.get('data')}")
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
                    print(f"[V6.0] 参数已热加载: {str_id}")
            elif action in ['start', 'pause', 'reset']:
                func = getattr(runner, action, None)
                if func:
                    func(str_id)
                    print(f"[V6.0] 指令执行成功: {action} ({str_id})")
                else:
                    print(f"[V6.0 Error] MultiStrategyRunner 缺少方法: {action}")
        except Exception as e:
            print(f"[V6.0 Error] 控制回调执行失败: {e}")
            import traceback; traceback.print_exc()

    dashboard.on_control_callback = on_control

    print("\n[V6.0] 顺利启动! 请访问 http://localhost:5066")
    
    try:
        for market_data in data_feed.stream():
            runner.on_bar(market_data)
    except KeyboardInterrupt:
        runner.save_all()
        print("\n程序正常退出")
    except Exception as e:
        print(f"[V6.0 Fatal] {e}")
        import traceback; traceback.print_exc()
        runner.save_all()

    return 0

if __name__ == '__main__':
    sys.exit(main())
