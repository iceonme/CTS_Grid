import sys
import os
import time
import json
from pathlib import Path
from datetime import datetime, timedelta

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategies.grid_v80_opt import GridStrategyV80Opt
from executors.paper import PaperExecutor
from datafeeds import OKXDataFeed
from dashboard_80.server_80 import create_dashboard_80
from runner import MultiStrategyRunner, StrategySlot
from config.api_config import OKX_DEMO_CONFIG, DEFAULT_SYMBOL, DEFAULT_TIMEFRAME

# ──────────────────────────────────────────────────────────────
# 策略配置
# ──────────────────────────────────────────────────────────────
INITIAL_BALANCE = 10000.0
base_dir = os.path.dirname(os.path.abspath(__file__))
V80_RUNTIME_PATH = os.path.join(base_dir, 'config', 'grid_v80_opt_btc_runtime.json')
V80_FACTORY_PATH = os.path.join(base_dir, 'config', 'grid_v80_opt_btc_default.json')

STRATEGY_CATALOG = {
    'grid_v80': {
        'display_name': 'Grid V8.0-OPT (纯RSI动态左侧)',
        'cls': GridStrategyV80Opt,
        'params': {
            'symbol': DEFAULT_SYMBOL,
            'config_path': V80_RUNTIME_PATH,
            'timeframe_minutes': 1  # 回归 1m
        }
    }
}

def build_history_data(strategy_cls, strategy_params, initial_balance, trades_sorted, data_main):
    """重建 V8.0-OPT 数据历史"""
    history_candles = []
    history_rsi = []
    history_equity = []

    temp_strat = strategy_cls(**strategy_params)
    temp_strat.initialize()
    
    # 手动推进状态
    # temp_strat._data_main.extend(data_main) # 不直接 extend，而是通过 on_data 模拟演化轨迹

    sim_cash = float(initial_balance)
    sim_pos = 0.0
    trade_idx = 0

    print(f"[V8.0-OPT] 重建指标历史 ({len(data_main)} bars)...")
    
    for i, data in enumerate(data_main):
        ts_ms = int(data.timestamp.timestamp() * 1000)

        # 更新指标 (on_data 会内部 append 到 _data_main)
        temp_strat.on_data(data, None)
        
        # 记录 K 线
        history_candles.append({
            't': ts_ms, 'o': data.open, 'h': data.high,
            'l': data.low, 'c': data.close, 'v': data.volume
        })
        
        status = temp_strat.get_status()
        history_rsi.append({'t': ts_ms, 'v': status.get('current_rsi')})

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

    return history_candles, history_rsi, history_equity, []


def main():
    print("\n" + "="*60)
    print("CTS 8.0 — 策略运行环境 (V8.0-OPT 动态网格)")
    print("="*60)
    
    # 1. 配置检查
    config_path = Path(V80_RUNTIME_PATH)
    if not config_path.exists():
        factory_path = Path(V80_FACTORY_PATH)
        if factory_path.exists():
            import shutil
            shutil.copy(factory_path, config_path)
            print(f"[系统] 已初始化运行配置: {config_path}")
        else:
            # 如果没有，自动生成一份默认的作为 fallback
            default_config = {
              "version": "8.0-OPT-BTC",
              "port": 5080,
              "symbol": "BTC-USDT",
              "trading": {
                "initial_capital": 10000,
                "grid_layers": 5,
                "layer_size_percent": 20
              },
              "signals": {
                "rsi_period": 14,
                "rsi_buy_extreme": 20,
                "rsi_buy_normal": 28,
                "rsi_sell_normal": 70,
                "rsi_sell_extreme": 80
              },
              "grid": {
                "dynamic_spacing": True,
                "min_spacing": 0.003,
                "atr_multiplier": 0.15
              },
              "risk": {
                "black_swan_atr_mult": 3,
                "ladder_take_profit": [0.3, 0.4, 0.3]
              }
            }
            if not config_path.parent.exists():
                config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2)
            print(f"[系统] 已生成默认运行配置: {config_path}")


    # 2. 启动 Dashboard (Port: 5080)
    dashboard = create_dashboard_80(port=5080)
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
            state_file=f"trading_state_{slot_id}_v80.json",
            trades_file=f"trading_trades_{slot_id}_v80.json"
        )
        runner.add_slot(slot)

    # 4. 数据流 (回归 1m)
    data_feed = OKXDataFeed(
        symbol=DEFAULT_SYMBOL,
        timeframe='1m',
        api_key=OKX_DEMO_CONFIG['api_key'],
        api_secret=OKX_DEMO_CONFIG['api_secret'],
        passphrase=OKX_DEMO_CONFIG['passphrase'],
        is_demo=True
    )

    # 5. 预热 (600 bars for 10h lookback ATR)
    print("[V8.0-OPT] 预热数据中...")
    from engines import LiveEngine
    first_slot = next(iter(runner._slots.values()))
    warmup_engine = LiveEngine(first_slot.strategy, first_slot.executor, data_feed, warmup_bars=600)
    
    if warmup_engine.warmup():
        data_main = list(first_slot.strategy._data_main)
        trades_sorted = sorted(runner._trades.get(first_slot.slot_id, []), key=lambda x: str(x.get('time', '')))
        # 调用新版 build_history_data (单数据流)
        hc, hrsi, heq, hmacd = build_history_data(GridStrategyV80Opt, STRATEGY_CATALOG['grid_v80']['params'], INITIAL_BALANCE, trades_sorted, data_main)
        runner.push_warmup(first_slot, hc, hrsi, heq, hmacd)
        print(f"[V8.0-OPT] 预热完成: {len(hc)} 根历史数据")

    # 6. 控制回调
    def on_control(action: str, str_id: str, **kwargs):
        print(f"[V8.0 Control] 接收控制指令: action={action}, str_id={str_id}, data={kwargs.get('data')}")
        try:
            if action == 'save_params':
                new_params = kwargs.get('data')
                slot = runner._slots.get(str_id)
                if slot and new_params:
                    cp = getattr(slot.strategy, 'params_path', V80_RUNTIME_PATH)
                    with open(cp, 'r', encoding='utf-8') as f: config = json.load(f)
                    config.update(new_params)
                    with open(cp, 'w', encoding='utf-8') as f: json.dump(config, f, indent=2)
                    if hasattr(slot.strategy, '_load_params'): slot.strategy._load_params()
                    print(f"[V8.0-OPT] 参数已热加载: {str_id}")
            elif action in ['start', 'pause', 'reset']:
                func = getattr(runner, action, None)
                if func:
                    func(str_id)
                    print(f"[V8.0-OPT] 指令执行成功: {action} ({str_id})")
                else:
                    print(f"[V8.0 Error] MultiStrategyRunner 缺少方法: {action}")
        except Exception as e:
            print(f"[V8.0 Error] 控制回调执行失败: {e}")
            import traceback; traceback.print_exc()

    dashboard.on_control_callback = on_control

    print("\n[V8.0-OPT] 顺利启动! 请访问 http://localhost:5080")
    
    while True:
        try:
            for market_data in data_feed.stream():
                if market_data:
                    runner.on_bar(market_data)
        except KeyboardInterrupt:
            runner.save_all()
            print("\n控制台捕获 KeyboardInterrupt，程序正常退出")
            break
        except Exception as e:
            print(f"\n[V7.0 Error] 数据流中断或处理异常: {e}")
            import traceback
            traceback.print_exc()
            print("[V7.0-Razor] 5秒后尝试重启数据流...")
            time.sleep(5)
            runner.save_all()

    return 0

if __name__ == '__main__':
    sys.exit(main())
