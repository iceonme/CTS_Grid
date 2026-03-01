"""
CTS 5.2 多策略启动入口
针对 Grid RSI V5.2 (Refactored) 优化的启动器

功能：
- 支持 Grid RSI V5.2 的外部 JSON 配置热加载
- 单一 OKX 数据流广播
- 前端 Dashboard 支持
"""

import sys
import os
import time
from pathlib import Path

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategies import GridRSIStrategyV5_2
from executors.paper import PaperExecutor
from datafeeds import OKXDataFeed
from dashboard import create_dashboard
from runner import MultiStrategyRunner, StrategySlot
from config.api_config import OKX_DEMO_CONFIG, DEFAULT_SYMBOL, DEFAULT_TIMEFRAME

# ──────────────────────────────────────────────────────────────
# 策略配置
# ──────────────────────────────────────────────────────────────
INITIAL_BALANCE = 10000.0
V52_RUNTIME_PATH = "config/grid_v52_runtime.json"
V52_FACTORY_PATH = "config/grid_v52_default.json"

STRATEGY_CATALOG = {
    'grid_v51': {
        'display_name': 'Grid RSI V5.2 (Refactored)',
        'cls': GridRSIStrategyV5_2,
        'params': {
            'symbol': DEFAULT_SYMBOL,
            'config_path': V52_RUNTIME_PATH,
        }
    }
}

def build_history_data(strategy_cls, strategy_params, initial_balance, trades_sorted, data_source):
    """从数据源重建指标和权益的历史演进过程"""
    history_candles = []
    history_rsi = []
    history_equity = []
    history_macd = []

    # 创建一个纯净的临时策略实例用于模拟
    temp_strat = strategy_cls(**strategy_params)
    temp_strat.initialize()

    from core import Side
    sim_cash = initial_balance
    sim_pos = 0.0
    trade_idx = 0

    print(f"  开始模拟 {len(data_source)} 步数据以重建指标...")
    
    for i, data in enumerate(data_source):
        ts_ms = int(data.timestamp.timestamp() * 1000)

        # 1. 更新指标
        temp_strat._update_buffer(data)
        
        # 记录指标历史 (等到 warmup_done 之后)
        if temp_strat.indicators.warmup_done:
            status = temp_strat.get_status()
            
            history_candles.append({
                't': ts_ms, 'o': data.open, 'h': data.high,
                'l': data.low, 'c': data.close
            })
            
            history_rsi.append({'t': ts_ms, 'v': status.get('current_rsi')})
            history_macd.append({
                'time': ts_ms,
                'macd': status.get('macd'),
                'macdsignal': status.get('macdsignal'),
                'macdhist': status.get('macdhist')
            })

            # 更新资产权益
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

    if history_rsi:
        print(f"  指标历史记录成功: 起始RSI={history_rsi[0]['v']:.2f}, 最终RSI={history_rsi[-1]['v']:.2f}")
    
    return history_candles, history_rsi, history_equity, history_macd


def main():
    print("\n" + "="*60)
    print("CTS 5.2 — 策略运行环境 (V5.2 专用)")
    print("="*60)
    print(f"交易对: {DEFAULT_SYMBOL} | 周期: {DEFAULT_TIMEFRAME}")
    print(f"参数文件: {V52_RUNTIME_PATH}")
    print("="*60 + "\n")

    # 1. 检查配置 (Runtime 优先，Factory 兜底)
    config_path = Path(V52_RUNTIME_PATH)
    if not config_path.exists():
        factory_path = Path(V52_FACTORY_PATH)
        if factory_path.exists():
            import shutil
            shutil.copy(factory_path, config_path)
            print(f"[系统] 已从出厂默认值初始化运行配置: {config_path}")
        else:
            print(f"错误: 找不到任何配置文件 ({V52_RUNTIME_PATH} 或 {V52_FACTORY_PATH})")
            return 1

    # 2. 启动 Dashboard
    print("[1/4] 启动 Dashboard...")
    dashboard = create_dashboard(port=5051)
    dashboard.start_background()
    time.sleep(1)

    # 3. 初始化 Runner
    print("[2/4] 初始化引擎...")
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
        )
        runner.add_slot(slot)
        print(f"  [OK] {cfg['display_name']} 已就绪")

    # 4. 数据流
    print("[3/4] 建立数据连接...")
    data_feed = OKXDataFeed(
        symbol=DEFAULT_SYMBOL,
        timeframe=DEFAULT_TIMEFRAME,
        api_key=OKX_DEMO_CONFIG['api_key'],
        api_secret=OKX_DEMO_CONFIG['api_secret'],
        passphrase=OKX_DEMO_CONFIG['passphrase'],
        is_demo=True
    )

    # 5. 预热
    print("[4/4] 预热数据...")
    from engines import LiveEngine
    first_slot = next(iter(runner._slots.values()))
    warmup_engine = LiveEngine(
        strategy=first_slot.strategy,
        executor=first_slot.executor,
        data_feed=data_feed, # 直接复用 data_feed 获取历史
        warmup_bars=200
    )
    if warmup_engine.warmup():
        data_source = list(first_slot.strategy._data_buffer)
        print(f"  成功获取 {len(data_source)} 根历史数据，开始重建指标曲线...")
        
        trades_sorted = sorted(runner._trades.get(first_slot.slot_id, []), key=lambda x: str(x.get('time', '')))
        
        # 传入类和参数进行重新演练
        hc, hrsi, heq, hmacd = build_history_data(
            GridRSIStrategyV5_2, 
            STRATEGY_CATALOG['grid_v51']['params'], 
            INITIAL_BALANCE, 
            trades_sorted,
            data_source
        )
        runner.push_warmup(first_slot, hc, hrsi, heq, hmacd)
        print(f"  指标历史重建完成: K线={len(hc)} RSI={len(hrsi)}")
    else:
        print("  警告: 预热失败")

    # 6. 回调
    def on_control(action: str, str_id: str, **kwargs):
        try:
            if action == 'start': runner.start(str_id)
            elif action == 'pause': runner.pause(str_id)
            elif action == 'reset': runner.reset(str_id)
            elif action == 'save_params':
                new_params = kwargs.get('data')
                slot = runner._slots.get(str_id)
                if slot and new_params:
                    # 获取策略绑定的配置文件路径
                    cp = getattr(slot.strategy, 'params_path', None)
                    if cp and os.path.exists(cp):
                        import json
                        with open(cp, 'r', encoding='utf-8') as f:
                            current_config = json.load(f)
                        
                        # 合并新参数
                        current_config.update(new_params)
                        
                        with open(cp, 'w', encoding='utf-8') as f:
                            json.dump(current_config, f, indent=2, ensure_ascii=False)
                        
                        print(f"[Config] 策略 {str_id} 运行时参数已保存至 {cp}")
                    else:
                        print(f"[Config] 错误: 找不到策略 {str_id} 的配置文件路径")
        except Exception as e:
            print(f"[Dashboard Control] 错误: {e}")
            import traceback; traceback.print_exc()

    dashboard.on_control_callback = on_control

    print("\n运行中... 请访问 http://localhost:5051 选择策略并启动")
    
    try:
        for market_data in data_feed.stream():
            try:
                runner.on_bar(market_data)
            except Exception as e:
                print(f"[Runner.on_bar] 实时处理异常: {e}")
                import traceback; traceback.print_exc()
    except KeyboardInterrupt:
        runner.save_all()
        print("\n状态已保存，程序退出")
    except Exception as e:
        print(f"[Fatal] 运行终止: {e}")
        import traceback; traceback.print_exc()
        runner.save_all()

    return 0

if __name__ == '__main__':
    sys.exit(main())
