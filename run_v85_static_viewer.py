import os
import sys
import json
import pandas as pd
from datetime import datetime, timedelta

# 确保模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engines.live import LiveEngine
from strategies.grid_v85 import GridStrategyV85
from datafeeds.csv_feed import CSVDataFeed
from executors.paper import PaperExecutor

import argparse

def run_v85_static_viewer():
    parser = argparse.ArgumentParser(description="Grid V8.5 Static Viewer Data Generator")
    parser.add_argument("--start", type=str, default="2025-03-16", help="开始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2025-03-16", help="结束日期 (YYYY-MM-DD)")
    args = parser.parse_args()

    data_path = "data/btc_1m_2025.csv"
    if not os.path.exists(data_path):
        data_path = "data/btc_1m_2025_03_16.csv"
        
    print(f"[配置] 数据源: {data_path} | 周期: {args.start} 到 {args.end}")

    try:
        start_dt = datetime.strptime(args.start, "%Y-%m-%d")
        end_dt = datetime.strptime(args.end, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except Exception as e:
        print(f"[错误] 日期解析失败: {e}")
        return
    
    warmup_start_dt = start_dt - timedelta(hours=4)
    
    # --- 高性能数据加载与预过滤 ---
    print("[1/3] 正在极速预加载数据切片...")
    # 1. 先读入所有时间戳，进行极速预过滤 (Epoch 毫秒格式)
    df_temp = pd.read_csv(data_path, usecols=['timestamp'])
    
    # 将日期转换为毫秒时间戳
    warmup_ts_ms = int(warmup_start_dt.timestamp() * 1000)
    end_ts_ms = int(end_dt.timestamp() * 1000)
    
    mask = (df_temp['timestamp'] >= warmup_ts_ms) & (df_temp['timestamp'] <= end_ts_ms)
    indices = df_temp.index[mask]
    
    if len(indices) == 0:
        print(f"[错误] 未在数据源中找到选定范围的数据 ({warmup_ts_ms} 至 {end_ts_ms})")
        return
        
    skip = indices[0] + 1 
    nrows = len(indices)
    
    # 2. 只读入需要的行
    df_slice = pd.read_csv(data_path, skiprows=range(1, skip), nrows=nrows)
    df_slice.columns = [c.lower() for c in df_slice.columns]
    
    # 转换 timestamp 到 datetime 供引擎使用
    df_slice['timestamp'] = pd.to_datetime(df_slice['timestamp'], unit='ms')
    df_slice.set_index('timestamp', inplace=True)
    df_slice.sort_index(inplace=True)
    
    print(f"[性能] 已精准提取 {len(df_slice)} 根 K 线，开始仿真...")

    # --- 初始化仿真引擎 ---
    strategy = GridStrategyV85(name="Grid_V85_Static", symbol="BTC-USDT", max_position_pct=0.8)
    executor = PaperExecutor(initial_capital=10000.0, fee_rate=0.001)
    
    # 注入预过滤的数据给 DataFeed
    data_feed = CSVDataFeed(filepath=data_path, symbol="BTC-USDT")
    data_feed._data = df_slice # 关键注入：避免 CSVDataFeed 再次全量加载
    
    engine = LiveEngine(strategy=strategy, executor=executor, data_feed=data_feed)

    full_history = {
        "candles": [], "equity": [], "rsi": [], "trades": [], "grid_snapshots": {},
        "meta": {"market_pnl_pct": 0.0}
    }

    stream = engine.data_feed.stream(start=warmup_start_dt, end=end_dt)
    engine.is_running = True
    engine._trades = [] 
    
    display_start_ts = int(pd.Timestamp(start_dt).timestamp() * 1000)
    first_price_in_range = None
    
    for data in stream:
        if not engine.is_running: break
        
        engine._current_time = data.timestamp
        engine._current_prices[data.symbol] = data.close
        engine.executor.update_market_data(data.timestamp, data.close)
        
        context = engine._get_context()
        signals = engine.strategy.on_data(data, context)
        if signals:
            engine._execute_signals(signals)
            
        ts_ms = int(pd.Timestamp(data.timestamp).timestamp() * 1000)
        if ts_ms < display_start_ts: continue
            
        if first_price_in_range is None:
            first_price_in_range = data.close
        
        # 记录 K线
        full_history["candles"].append({
            "time": ts_ms, "open": data.open, "high": data.high, "low": data.low, "close": data.close
        })
        # 记录 权益
        pos_value = sum(pos.size * engine._current_prices.get(sym, pos.avg_price) for sym, pos in engine.executor._positions.items())
        full_history["equity"].append({ "time": ts_ms, "value": engine.executor.get_cash() + pos_value })
        # 记录 RSI
        if engine.strategy.state.current_rsi is not None:
            full_history["rsi"].append({"time": ts_ms, "value": engine.strategy.state.current_rsi})
        # 记录 网格
        if hasattr(engine.strategy.state, 'grid_lines') and engine.strategy.state.grid_lines:
            full_history["grid_snapshots"][str(ts_ms)] = list(engine.strategy.state.grid_lines)

    # 计算基准收益
    last_price = engine._current_prices.get("BTC-USDT", first_price_in_range) if first_price_in_range else 0
    full_history["meta"]["market_pnl_pct"] = round(((last_price / first_price_in_range - 1) * 100), 2) if first_price_in_range else 0
    full_history["meta"]["l0_idx"] = engine.strategy.get_status().get('params', {}).get('l0_idx', 5)

    # 整理交易记录
    first_candle_time = full_history["candles"][0]["time"] if full_history["candles"] else 0
    for t in engine._trades:
        try:
            trade_ts_ms = int(pd.Timestamp(t.get('time', '')).timestamp() * 1000)
            if trade_ts_ms < first_candle_time: continue
            full_history["trades"].append({
                "time": trade_ts_ms, "side": t.get('type', 'BUY'), "price": t.get('price', 0),
                "size": t.get('size', 0), "id": f"t_{trade_ts_ms}"
            })
        except: continue

    # 注入决策日志
    full_history["decision_trace"] = engine.strategy.decision_trace

    output_path = "dashboard/static/backtest_data.json"
    with open(output_path, "w", encoding='utf-8') as f:
        json.dump(full_history, f)
        
    print(f"\n=====================================")
    print(f"DONE: 回测提速版执行完毕!")
    print(f"FILE: {output_path}")
    print(f"=====================================\n")

if __name__ == "__main__":
    run_v85_static_viewer()
