"""
run_multiple.py 鈥?多策略并行回测入鍙?

用法:
    python run_multiple.py --data btc_1m.csv --capital 10000
"""

import argparse
import sys
import threading
from datetime import datetime

from cartridges.strategies import GridRSIStrategy, GridRSIStrategyV5_2
from cartridges.bridge.executors import PaperExecutor
from cartridges.bridge.datafeeds import CSVDataFeed
from console.engines import BacktestEngine
from console.dashboard import create_dashboard, set_dashboard


def run_strategy(name: str, strategy, data_file: str, capital: float,
                 symbol: str, dashboard, strategy_id: str):
    """在独立线程中运行涓€条策略的回测，并鍚?Dashboard 鎺ㄩ€佹暟鎹?""

    data_feed = CSVDataFeed(filepath=data_file, symbol=symbol)
    executor  = PaperExecutor(
        initial_capital=capital,
        fee_rate=0.001,
        slippage_model='adaptive'
    )
    engine = BacktestEngine(
        strategy=strategy,
        executor=executor,
        initial_capital=capital
    )

    call_count = [0]

    def progress_callback(current, total):
        call_count[0] += 1
        if call_count[0] % 1000 == 0:
            print(f"[{name}] 进度: {current}/{total}")

        # 鍚?Dashboard 鎺ㄩ€侊紙姣?100 条推涓€娆?以降浣?CPU 压力锛?
        if dashboard and call_count[0] % 100 == 0:
            try:
                status = strategy.get_status()
                
                # 提取当前 K 线和历史数据用于图表绘制
                current_data = strategy._data_buffer[-1] if hasattr(strategy, '_data_buffer') and strategy._data_buffer else None
                
                payload = {
                    'strategy': {'name': name, **status},
                    'rsi': status.get('current_rsi', 50),
                }
                
                if current_data:
                    ts_ms = int(current_data.timestamp.timestamp() * 1000)
                    payload.update({
                        'timestamp': current_data.timestamp.isoformat(),
                        'price': current_data.close,
                        'total_value': engine.executor.get_total_value() if hasattr(engine, 'executor') else 10000,
                        'candle': {
                            't': ts_ms,
                            'o': float(current_data.open),
                            'h': float(current_data.high),
                            'l': float(current_data.low),
                            'c': float(current_data.close)
                        }
                    })
                    
                    # 为了鍦?/5.1 中显绀?MACD，检查策略状态里是否包含 macd
                    if 'macd' in status:
                        payload['macd'] = status['macd']
                        payload['macdsignal'] = status.get('macdsignal', 0.0)
                        payload['macdhist'] = status.get('macdhist', 0.0)
                
                # 如果是第涓€次推送（鎴栬€呭緢靠前），鎺ㄩ€佷竴下全量历史给图表铺底
                if call_count[0] <= 100 and hasattr(strategy, '_data_buffer'):
                    hist_candles = []
                    hist_rsi = []
                    hist_macd = []
                    import pandas as pd
                    df = strategy._get_dataframe()
                    
                    if not df.empty:
                        # K Line
                        for ts, row in df.iterrows():
                            t = int(ts.timestamp() * 1000)
                            hist_candles.append({
                                't': t, 'o': float(row['open']), 'h': float(row['high']),
                                'l': float(row['low']), 'c': float(row['close'])
                            })
                            
                        # MACD
                        if hasattr(strategy, '_calculate_macd') and len(df) > 26:
                            close = df['close']
                            ema_fast = close.ewm(span=12, adjust=False).mean()
                            ema_slow = close.ewm(span=26, adjust=False).mean()
                            macd_line = ema_fast - ema_slow
                            signal_line = macd_line.ewm(span=9, adjust=False).mean()
                            hist = macd_line - signal_line
                            for ts, val in hist.items():
                                if pd.isna(val): continue
                                hist_macd.append({
                                    'time': int(ts.timestamp() * 1000),
                                    'macd': float(macd_line[ts]),
                                    'macdsignal': float(signal_line[ts]),
                                    'macdhist': float(val)
                                })
                        
                        # RSI
                        delta = df['close'].diff()
                        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                        rs = gain / loss.replace(0, float('nan'))
                        rsi = 100 - (100 / (1 + rs))
                        for ts, val in rsi.items():
                            if not pd.isna(val):
                                hist_rsi.append({'time': int(ts.timestamp() * 1000), 'value': float(val)})

                        payload['history_candles'] = hist_candles
                        if hist_rsi: payload['history_rsi'] = hist_rsi
                        if hist_macd: payload['history_macd'] = hist_macd

                dashboard.update(payload, strategy_id=strategy_id)
            except Exception as e:
                print(f"[{name}] Dashboard 鎺ㄩ€佸紓甯? {e}")

    print(f"\n[{name}] 寮€始回娴?(strategy_id={strategy_id})")
    results = engine.run(data_feed, progress_callback)
    engine.print_report(results)
    print(f"\n[{name}] 回测完成")
    return results


def main():
    parser = argparse.ArgumentParser(description='多策略并行回娴?)
    parser.add_argument('--data',       type=str,   default='btc_1m.csv', help='历史数据文件路径')
    parser.add_argument('--symbol',     type=str,   default='BTC-USDT',   help='交易瀵?)
    parser.add_argument('--capital',    type=float, default=10000.0,       help='每条策略初始资金')
    parser.add_argument('--dashboard',  action='store_true',               help='启动 Dashboard')
    parser.add_argument('--port',       type=int,   default=5000,          help='Dashboard 端口')
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"多策略并行回娴?)
    print(f"{'='*60}")
    print(f"数据文件: {args.data}")
    print(f"交易瀵?   {args.symbol}")
    print(f"初始资金: ${args.capital:,.2f}")
    print(f"{'='*60}\n")

    # 鈹€鈹€ 创建两个策略实例 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    strategy_v40 = GridRSIStrategy(
        symbol=args.symbol,
        grid_levels=10,
        rsi_period=14,
        use_kelly_sizing=True,
        trailing_stop=True,
    )

    strategy_v52 = GridRSIStrategyV5_2(
        symbol=args.symbol,
        grid_levels=10,
        rsi_period=14,
        use_kelly_sizing=True,
        trailing_stop=True,
    )

    # 鈹€鈹€ 鍙€夛細启动 Dashboard 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    dashboard = None
    if args.dashboard:
        dashboard = create_dashboard(port=args.port)
        set_dashboard(dashboard)
        dashboard.register_strategy('grid_rsi_v40',  'Grid RSI V4.0', route='/')
        dashboard.register_strategy('grid_rsi_v52',  'Grid RSI V5.2', route='/v5')
        dashboard.start_background()
        print(f"[Dashboard] 已在 http://localhost:{args.port} 启动\n")
        import time; time.sleep(1)  # 缁?eventlet 涓€点启动时闂?

    # 鈹€鈹€ 多线程并行运琛?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    results_store = {}

    def thread_v40():
        results_store['v40'] = run_strategy(
            name='Grid RSI V4.0', strategy=strategy_v40,
            data_file=args.data, capital=args.capital,
            symbol=args.symbol, dashboard=dashboard,
            strategy_id='grid_rsi_v40'
        )

    def thread_v52():
        results_store['v52'] = run_strategy(
            name='Grid RSI V5.2', strategy=strategy_v52,
            data_file=args.data, capital=args.capital,
            symbol=args.symbol, dashboard=dashboard,
            strategy_id='grid_rsi_v52'
        )

    t1 = threading.Thread(target=thread_v40)
    t2 = threading.Thread(target=thread_v52)

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # 鈹€鈹€ 对比姹囨€?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    print(f"\n{'='*60}")
    print("📊 多策略对比汇鎬?)
    print(f"{'='*60}")
    for key, label in [('v40', 'Grid RSI V4.0'), ('v52', 'Grid RSI V5.2')]:
        r = results_store.get(key, {})
        print(f"\n[{label}]")
        print(f"  总收益率: {r.get('total_return', 0)*100:.2f}%")
        print(f"  鏈€大回鎾? {r.get('max_drawdown', 0)*100:.2f}%")
        print(f"  夏普比率: {r.get('sharpe_ratio', 0):.2f}")
        print(f"  总交易数: {r.get('total_trades', 0)}")
        print(f"  胜率:     {r.get('win_rate', 0)*100:.1f}%")

    if args.dashboard:
        print(f"\n[Dashboard] 保持运行，请在浏览器查看 http://localhost:{args.port}")
        try:
            import time
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n[Dashboard] 宸查€€鍑?)

    return 0


if __name__ == '__main__':
    sys.exit(main())
