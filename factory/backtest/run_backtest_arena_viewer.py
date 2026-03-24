import os
import sys
import json
import pandas as pd
from datetime import datetime, timedelta
import argparse

# 鑷姩澶勭悊璺緞 - 鍚戜笂瀵绘壘椤圭洰鏍圭洰褰?
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from console.engines.live import LiveEngine
from cartridges.bridge.datafeeds.csv_feed import CSVDataFeed
from cartridges.bridge.executors.paper import PaperExecutor

def run_single_strategy(strategy_id: str, df_slice: pd.DataFrame, start_dt, end_dt):
    # 鍔ㄦ€佸姞杞界瓥鐣ョ被
    try:
        if strategy_id == "grid_v85":
            from cartridges.strategies.grid_v85 import GridStrategyV85 as StrategyClass
            strategy = StrategyClass(name="Grid_V85_Static", symbol="BTC-USDT", max_position_pct=0.8)
        elif strategy_id == "grid_mtf_6_0":
            from cartridges.strategies.grid_mtf_6_0 import GridMTFStrategyV6_0 as StrategyClass
            strategy = StrategyClass(name="Grid_V60_Static", symbol="BTC-USDT")
        else:
            print(f"[閿欒] 涓嶆敮鎸佺殑绛栫暐: {strategy_id}")
            return None
    except ImportError as e:
        print(f"[閿欒] 鍔犺浇绛栫暐 {strategy_id} 澶辫触: {e}")
        return None

    # 鍒濆鍖栦豢鐪熷紩鎿?
    executor = PaperExecutor(initial_capital=10000.0, fee_rate=0.001)
    # 鏋勯€犺櫄鍋?DataFeed
    data_feed = CSVDataFeed(filepath="dummy", symbol="BTC-USDT")
    data_feed._data = df_slice
    
    engine = LiveEngine(strategy=strategy, executor=executor, data_feed=data_feed)
    engine._trades = []
    
    # 缁撴灉瀹瑰櫒
    res = {
        "equity": [], "rsi": [], "trades": [], "grid_snapshots": {},
        "meta": {"market_pnl_pct": 0.0}
    }
    
    display_start_ts = int(pd.Timestamp(start_dt).timestamp() * 1000)
    first_price_in_range = None
    
    stream = engine.data_feed.stream(start=None, end=None) # 宸茬粡鍒囩墖杩囦簡
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
        
        # 璁板綍 鏉冪泭
        pos_value = sum(pos.size * engine._current_prices.get(sym, pos.avg_price) for sym, pos in engine.executor._positions.items())
        res["equity"].append({ "time": ts_ms, "value": engine.executor.get_cash() + pos_value })
        # 璁板綍 RSI
        if hasattr(engine.strategy.state, 'current_rsi') and engine.strategy.state.current_rsi is not None:
            res["rsi"].append({"time": ts_ms, "value": engine.strategy.state.current_rsi})
        # 璁板綍 缃戞牸
        if hasattr(engine.strategy.state, 'grid_lines') and engine.strategy.state.grid_lines:
            res["grid_snapshots"][str(ts_ms)] = list(engine.strategy.state.grid_lines)

    # 璁＄畻鍩哄噯鏀剁泭
    last_price = engine._current_prices.get("BTC-USDT", first_price_in_range) if first_price_in_range else 0
    res["meta"]["market_pnl_pct"] = round(((last_price / first_price_in_range - 1) * 100), 2) if first_price_in_range else 0
    
    # 璁板綍绛栫暐鐗规湁鍏冩暟鎹?(濡?l0_idx)
    if hasattr(engine.strategy.state, 'l0_idx'):
        res["meta"]["l0_idx"] = engine.strategy.state.l0_idx

    # 璁板綍鍐崇瓥鏃ュ織
    if hasattr(engine.strategy, 'decision_trace'):
        res["decision_trace"] = engine.strategy.decision_trace

    # 鏁寸悊浜ゆ槗璁板綍
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
    parser.add_argument("--strategy", type=str, default="grid_v85", help="绛栫暐鍚嶇О锛屾敮鎸侀€楀彿鍒嗛殧 (grid_v85,grid_mtf_6_0)")
    parser.add_argument("--start", type=str, default="2025-03-16", help="寮€濮嬫棩鏈?(YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2025-03-16", help="缁撴潫鏃ユ湡 (YYYY-MM-DD)")
    args = parser.parse_args()

    # 澶勭悊澶氱瓥鐣ュ垪琛?
    strategy_ids = [s.strip() for s in args.strategy.split(',')]
    
    data_path = os.path.join(BASE_DIR, "data/btc_1m_2025.csv")
    if not os.path.exists(data_path):
        data_path = os.path.join(BASE_DIR, "data/btc_1m_2025_03_16.csv")
        
    print(f"[绔炴妧鍦篯 绛栫暐鍒楄〃: {strategy_ids} | 鏁版嵁婧? {data_path} | 鍛ㄦ湡: {args.start} 鍒?{args.end}")

    try:
        start_dt = datetime.strptime(args.start, "%Y-%m-%d")
        end_dt = datetime.strptime(args.end, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except Exception as e:
        print(f"[閿欒] 鏃ユ湡瑙ｆ瀽澶辫触: {e}")
        return
    
    # 纭畾鏈€闀?Warmup (鏆傚畾鏈€澶?6 灏忔椂)
    max_warmup_hours = 6
    warmup_start_dt = start_dt - timedelta(hours=max_warmup_hours)
    
    # --- 楂樻€ц兘鏁版嵁鍔犺浇涓庨杩囨护 ---
    print("[1/3] 姝ｅ湪鏋侀€熼鍔犺浇鏁版嵁鍒囩墖...")
    df_temp = pd.read_csv(data_path, usecols=['timestamp'])
    
    warmup_ts_ms = int(warmup_start_dt.timestamp() * 1000)
    end_ts_ms = int(end_dt.timestamp() * 1000)
    
    mask = (df_temp['timestamp'] >= warmup_ts_ms) & (df_temp['timestamp'] <= end_ts_ms)
    indices = df_temp.index[mask]
    
    if len(indices) == 0:
        print(f"[閿欒] 鏈湪鏁版嵁婧愪腑鎵惧埌閫夊畾鑼冨洿鐨勬暟鎹?)
        return
        
    skip = indices[0] + 1 
    nrows = len(indices)
    
    df_slice = pd.read_csv(data_path, skiprows=range(1, skip), nrows=nrows)
    df_slice.columns = [c.lower() for c in df_slice.columns]
    df_slice['timestamp'] = pd.to_datetime(df_slice['timestamp'], unit='ms')
    df_slice.set_index('timestamp', inplace=True)
    df_slice.sort_index(inplace=True)
    
    print(f"[鎬ц兘] 宸插姞杞?{len(df_slice)} 鏍?K 绾匡紝寮€濮嬭繍琛屽绛栫暐骞惰浠跨湡...")

    # 缁撴灉鏁村悎
    final_output = {
        "candles": [],
        "strategies": {}
    }

    # 濉厖鍏叡 K 绾?(浠呴檺鎸囧畾灞曠ず鑼冨洿鍐呯殑)
    display_start_ts = int(pd.Timestamp(start_dt).timestamp() * 1000)
    df_display = df_slice[df_slice.index >= start_dt]
    for ts, row in df_display.iterrows():
        final_output["candles"].append({
            "time": int(ts.timestamp() * 1000), "open": row['open'], "high": row['high'], "low": row['low'], "close": row['close']
        })

    # 閫愪釜杩愯绛栫暐
    for sid in strategy_ids:
        print(f"  > 姝ｅ湪杩愯绛栫暐: {sid}...")
        res = run_single_strategy(sid, df_slice, start_dt, end_dt)
        if res:
            final_output["strategies"][sid] = res

    # 鍏煎鎬у鐞嗭細濡傛灉鍙湁涓€涓瓥鐣ワ紝鍚屾椂涔熸斁鍦ㄥ灞備互渚挎棫鐗?UI 璇诲彇 (鍙€夛紝寤鸿鐩存帴鍗囩骇 UI)
    # 杩欓噷鎴戜滑鐩存帴閲囩敤鏂扮粨鏋勶紝骞跺幓鍗囩骇 UI
    
    output_path = os.path.join(BASE_DIR, "dashboard/static/backtest_data.json")
    with open(output_path, "w", encoding='utf-8') as f:
        json.dump(final_output, f)
        
    print(f"\n=====================================")
    print(f"DONE: 绔炴妧鍦哄绛栫暐鍥炴祴鎵ц瀹屾瘯!")
    print(f"FILE: {output_path}")
    print(f"=====================================\n")

if __name__ == "__main__":
    run_arena_viewer()
