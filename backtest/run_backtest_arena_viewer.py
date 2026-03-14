import os
import sys
import json
import pandas as pd
from datetime import datetime, timedelta
import argparse

# 自动处理路径 - 向上寻找项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from engines.live import LiveEngine
from datafeeds.csv_feed import CSVDataFeed
from executors.paper import PaperExecutor

def run_single_strategy(strategy_id: str, df_slice: pd.DataFrame, start_dt, end_dt):
    # 动态加载策略类
    try:
        if strategy_id == "grid_v85":
            from strategies.grid_v85 import GridStrategyV85 as StrategyClass
            strategy = StrategyClass(name="Grid_V85_Static", symbol="BTC-USDT", max_position_pct=0.8)
        elif strategy_id == "grid_mtf_6_0":
            from strategies.grid_mtf_6_0 import GridMTFStrategyV6_0 as StrategyClass
            strategy = StrategyClass(name="Grid_V60_Static", symbol="BTC-USDT")
        else:
            print(f"[错误] 不支持的策略: {strategy_id}")
            return None
    except ImportError as e:
        print(f"[错误] 加载策略 {strategy_id} 失败: {e}")
        return None

    # 初始化仿真引擎
    executor = PaperExecutor(initial_capital=10000.0, fee_rate=0.001)
    # 构造虚假 DataFeed
    data_feed = CSVDataFeed(filepath="dummy", symbol="BTC-USDT")
    data_feed._data = df_slice
    
    engine = LiveEngine(strategy=strategy, executor=executor, data_feed=data_feed)
    engine._trades = []
    
    # 结果容器
    res = {
        "equity": [], "rsi": [], "trades": [], "grid_snapshots": {},
        "meta": {"market_pnl_pct": 0.0}
    }
    
    display_start_ts = int(pd.Timestamp(start_dt).timestamp() * 1000)
    first_price_in_range = None
    
    stream = engine.data_feed.stream(start=None, end=None) # 已经切片过了
    engine.is_running = True
    
    for data in stream:
        ts_ms = int(pd.Timestamp(data.timestamp).timestamp() * 1000)
        
        engine._current_time = data.timestamp
        engine._current_prices[data.symbol] = data.close
        engine.executor.update_market_data(data.timestamp, data.close)
        
        context = engine._get_context()
        signals = engine.strategy.on_data(data, context)
        if signals:
            engine._execute_signals(signals)
            
        if ts_ms < display_start_ts: continue
            
        if first_price_in_range is None:
            first_price_in_range = data.close
        
        # 记录 权益
        pos_value = sum(pos.size * engine._current_prices.get(sym, pos.avg_price) for sym, pos in engine.executor._positions.items())
        res["equity"].append({ "time": ts_ms, "value": engine.executor.get_cash() + pos_value })
        # 记录 RSI
        if hasattr(engine.strategy.state, 'current_rsi') and engine.strategy.state.current_rsi is not None:
            res["rsi"].append({"time": ts_ms, "value": engine.strategy.state.current_rsi})
        # 记录 网格
        if hasattr(engine.strategy.state, 'grid_lines') and engine.strategy.state.grid_lines:
            res["grid_snapshots"][str(ts_ms)] = list(engine.strategy.state.grid_lines)

    # 计算基准收益
    last_price = engine._current_prices.get("BTC-USDT", first_price_in_range) if first_price_in_range else 0
    res["meta"]["market_pnl_pct"] = round(((last_price / first_price_in_range - 1) * 100), 2) if first_price_in_range else 0
    
    # 记录策略特有元数据 (如 l0_idx)
    if hasattr(engine.strategy.state, 'l0_idx'):
        res["meta"]["l0_idx"] = engine.strategy.state.l0_idx

    # 记录决策日志
    if hasattr(engine.strategy, 'decision_trace'):
        res["decision_trace"] = engine.strategy.decision_trace

    # 整理交易记录
    for t in engine._trades:
        try:
            trade_ts_ms = int(pd.Timestamp(t.get('time', '')).timestamp() * 1000)
            if trade_ts_ms < display_start_ts: continue
            res["trades"].append({
                "time": trade_ts_ms, "side": t.get('type', 'BUY'), "price": t.get('price', 0),
                "size": t.get('size', 0), "id": f"t_{trade_ts_ms}"
            })
        except: continue
        
    return res

def run_arena_viewer():
    parser = argparse.ArgumentParser(description="Multi-Strategy Arena Viewer Data Generator")
    parser.add_argument("--strategy", type=str, default="grid_v85", help="策略名称，支持逗号分隔 (grid_v85,grid_mtf_6_0)")
    parser.add_argument("--start", type=str, default="2025-03-16", help="开始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2025-03-16", help="结束日期 (YYYY-MM-DD)")
    args = parser.parse_args()

    # 处理多策略列表
    strategy_ids = [s.strip() for s in args.strategy.split(',')]
    
    data_path = os.path.join(BASE_DIR, "data/btc_1m_2025.csv")
    if not os.path.exists(data_path):
        data_path = os.path.join(BASE_DIR, "data/btc_1m_2025_03_16.csv")
        
    print(f"[竞技场] 策略列表: {strategy_ids} | 数据源: {data_path} | 周期: {args.start} 到 {args.end}")

    try:
        start_dt = datetime.strptime(args.start, "%Y-%m-%d")
        end_dt = datetime.strptime(args.end, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except Exception as e:
        print(f"[错误] 日期解析失败: {e}")
        return
    
    # 确定最长 Warmup (暂定最大 6 小时)
    max_warmup_hours = 6
    warmup_start_dt = start_dt - timedelta(hours=max_warmup_hours)
    
    # --- 高性能数据加载与预过滤 ---
    print("[1/3] 正在极速预加载数据切片...")
    df_temp = pd.read_csv(data_path, usecols=['timestamp'])
    
    warmup_ts_ms = int(warmup_start_dt.timestamp() * 1000)
    end_ts_ms = int(end_dt.timestamp() * 1000)
    
    mask = (df_temp['timestamp'] >= warmup_ts_ms) & (df_temp['timestamp'] <= end_ts_ms)
    indices = df_temp.index[mask]
    
    if len(indices) == 0:
        print(f"[错误] 未在数据源中找到选定范围的数据")
        return
        
    skip = indices[0] + 1 
    nrows = len(indices)
    
    df_slice = pd.read_csv(data_path, skiprows=range(1, skip), nrows=nrows)
    df_slice.columns = [c.lower() for c in df_slice.columns]
    df_slice['timestamp'] = pd.to_datetime(df_slice['timestamp'], unit='ms')
    df_slice.set_index('timestamp', inplace=True)
    df_slice.sort_index(inplace=True)
    
    print(f"[性能] 已加载 {len(df_slice)} 根 K 线，开始运行多策略并行仿真...")

    # 结果整合
    final_output = {
        "candles": [],
        "strategies": {}
    }

    # 填充公共 K 线 (仅限指定展示范围内的)
    display_start_ts = int(pd.Timestamp(start_dt).timestamp() * 1000)
    df_display = df_slice[df_slice.index >= start_dt]
    for ts, row in df_display.iterrows():
        final_output["candles"].append({
            "time": int(ts.timestamp() * 1000), "open": row['open'], "high": row['high'], "low": row['low'], "close": row['close']
        })

    # 逐个运行策略
    for sid in strategy_ids:
        print(f"  > 正在运行策略: {sid}...")
        res = run_single_strategy(sid, df_slice, start_dt, end_dt)
        if res:
            final_output["strategies"][sid] = res

    # 兼容性处理：如果只有一个策略，同时也放在外层以便旧版 UI 读取 (可选，建议直接升级 UI)
    # 这里我们直接采用新结构，并去升级 UI
    
    output_path = os.path.join(BASE_DIR, "dashboard/static/backtest_data.json")
    with open(output_path, "w", encoding='utf-8') as f:
        json.dump(final_output, f)
        
    print(f"\n=====================================")
    print(f"DONE: 竞技场多策略回测执行完毕!")
    print(f"FILE: {output_path}")
    print(f"=====================================\n")

if __name__ == "__main__":
    run_arena_viewer()
