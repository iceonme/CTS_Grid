"""
CTS1 主入口
统一入口，支持多种运行模式

使用方法:
    python main.py backtest --data btc_1m.csv
    python main.py paper --data btc_1m.csv
    python main.py live --demo
"""

import argparse
import sys
import os
from datetime import datetime

# 确保模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_backtest(args):
    """运行回测"""
    from strategies import GridRSIStrategy
    from executors import PaperExecutor
    from datafeeds import CSVDataFeed
    from engines import BacktestEngine
    
    print(f"\n{'='*60}")
    print(f"模式: 回测")
    print(f"数据: {args.data}")
    print(f"初始资金: ${args.capital:,.2f}")
    print(f"{'='*60}\n")
    
    data_feed = CSVDataFeed(filepath=args.data, symbol=args.symbol)
    
    strategy_version = getattr(args, 'strategy', '4.0')
    if strategy_version == '5.1':
        from strategies import GridRSIStrategyV5_1
        strategy = GridRSIStrategyV5_1(symbol=args.symbol)
    else:
        from strategies import GridRSIStrategy
        strategy = GridRSIStrategy(
            symbol=args.symbol,
            grid_levels=args.grid_levels,
            rsi_period=args.rsi_period
        )
    
    executor = PaperExecutor(initial_capital=args.capital)
    
    engine = BacktestEngine(
        strategy=strategy,
        executor=executor,
        initial_capital=args.capital
    )
    
    results = engine.run(data_feed)
    engine.print_report(results)
    
    return 0


def run_paper(args):
    """运行模拟盘"""
    from strategies import GridRSIStrategy
    from executors import PaperExecutor
    from datafeeds import CSVDataFeed
    from engines import LiveEngine
    from dashboard import create_dashboard
    
    print(f"\n{'='*60}")
    print(f"模式: 模拟盘")
    print(f"数据: {args.data}")
    print(f"初始资金: ${args.capital:,.2f}")
    print(f"{'='*60}\n")
    
    # 启动 Dashboard
    dashboard = create_dashboard(port=args.port)
    
    strategy_version = getattr(args, 'strategy', '4.0')
    if strategy_version == '5.1':
        from strategies import GridRSIStrategyV5_1
        strategy = GridRSIStrategyV5_1(symbol=args.symbol)
        dashboard.register_strategy('default', 'Grid RSI V5.1 (模拟盘)', route='/5.1')
    else:
        from strategies import GridRSIStrategy
        strategy = GridRSIStrategy(symbol=args.symbol)
        dashboard.register_strategy('default', 'Grid RSI V4.0 (模拟盘)', route='/')
        
    dashboard.start_background()
    
    # 创建引擎
    data_feed = CSVDataFeed(filepath=args.data, symbol=args.symbol)
    
    executor = PaperExecutor(
        initial_capital=args.capital,
        fee_rate=0.001,
        slippage_model='adaptive'
    )
    
    engine = LiveEngine(
        strategy=strategy,
        executor=executor,
        data_feed=data_feed
    )
    
    # 注册状态回调
    def on_status_update(status):
        dashboard.update(status)
    
    engine.register_status_callback(on_status_update)
    
    # 运行
    try:
        engine.run()
    except KeyboardInterrupt:
        print("\n用户中断")
        engine.stop()
    
    return 0


def run_live(args):
    """运行实盘"""
    from strategies import GridRSIStrategy
    from executors import OKXExecutor
    from datafeeds import OKXDataFeed
    from engines import LiveEngine
    from dashboard import create_dashboard
    
    # 获取 API 配置
    api_key = args.api_key or os.getenv('OKX_API_KEY')
    secret = args.secret or os.getenv('OKX_SECRET')
    passphrase = args.passphrase or os.getenv('OKX_PASSPHRASE')
    
    if not all([api_key, secret, passphrase]):
        print("错误: 需要提供 OKX API 凭证")
        print("可通过 --api-key/--secret/--passphrase 参数或环境变量设置")
        return 1
    
    print(f"\n{'='*60}")
    print(f"模式: {'模拟盘' if args.demo else '实盘'}")
    print(f"交易对: {args.symbol}")
    print(f"{'='*60}\n")
    
    # 创建引擎（但不启动）
    data_feed = OKXDataFeed(
        symbol=args.symbol,
        timeframe=args.timeframe,
        api_key=api_key,
        api_secret=secret,
        passphrase=passphrase,
        is_demo=args.demo
    )
    
    strategy_version = getattr(args, 'strategy', '4.0')
    if strategy_version == '5.1':
        from strategies import GridRSIStrategyV5_1
        strategy = GridRSIStrategyV5_1(symbol=args.symbol)
    else:
        from strategies import GridRSIStrategy
        strategy = GridRSIStrategy(symbol=args.symbol)
    
    executor = OKXExecutor(
        api_key=api_key,
        api_secret=secret,
        passphrase=passphrase,
        is_demo=args.demo
    )
    
    engine = LiveEngine(
        strategy=strategy,
        executor=executor,
        data_feed=data_feed
    )
    
    # 先执行 warmup，获取历史数据
    print("[1/4] 预热策略...")
    if not engine.warmup():
        print("预热失败")
        return 1
    
    # 从历史数据构建 K 线列表
    history_candles = []
    if hasattr(strategy, '_data_buffer') and strategy._data_buffer:
        for data in strategy._data_buffer:
            import pandas as pd
            ts_ms = int(pd.Timestamp(data.timestamp).timestamp() * 1000)
            history_candles.append({
                't': ts_ms,
                'o': float(data.open),
                'h': float(data.high),
                'l': float(data.low),
                'c': float(data.close)
            })
    print(f"[2/4] 准备 {len(history_candles)} 根历史 K 线")
    
    # 启动 Dashboard
    print(f"[3/4] 启动 Dashboard...")
    dashboard = create_dashboard(port=args.port)
    app_mode = "实盘模拟" if args.demo else "OKX 实盘"
    
    if strategy_version == '5.1':
        dashboard.register_strategy('default', f'Grid RSI V5.1 ({app_mode})', route='/5.1')
    else:
        dashboard.register_strategy('default', f'Grid RSI V4.0 ({app_mode})', route='/')
        
    dashboard.start_background()
    
    # 发送历史数据到 Dashboard
    if history_candles:
        hist_data = {
            'history_candles': history_candles,
            'history_rsi': [{'time': c['t'], 'value': None} for c in history_candles],
            'history_equity': [{'time': c['t'], 'value': None} for c in history_candles]
        }
        
        # 把引擎生成的历史指标附加上去
        if hasattr(engine, '_history_rsi'):
            hist_data['history_rsi'] = engine._history_rsi
        if hasattr(engine, '_history_macd'):
            hist_data['history_macd'] = engine._history_macd
            
        dashboard.update(hist_data)
        print(f"[4/4] 历史数据已发送到 Dashboard")
    
    # 注册状态回调
    def on_status_update(status):
        dashboard.update(status)
    
    engine.register_status_callback(on_status_update)
    
    # 运行引擎（跳过 warmup，因为已经执行过了）
    print(f"\n{'='*60}")
    print(f"实盘引擎启动 | 策略: {strategy.name}")
    print(f"{'='*60}\n")
    
    engine.is_running = True
    engine.strategy.on_start()
    
    try:
        data_count = 0
        for data in engine.data_feed.stream():
            if not engine.is_running:
                break
            
            data_count += 1
            engine._current_time = data.timestamp
            engine._current_prices[data.symbol] = data.close
            
            # 更新执行器
            engine.executor.update_market_data(data.timestamp, data.close)
            
            # 策略决策
            context = engine._get_context()
            signals = engine.strategy.on_data(data, context)
            
            # 执行
            if signals:
                print(f"[引擎] 生成 {len(signals)} 个信号")
                engine._execute_signals(signals)
            
            # 发送状态更新
            status = engine._build_status(data)
            engine._notify_status(status)
            
            # 每 5 条数据打印一次日志
            if data_count % 5 == 0:
                print(f"[引擎] 已处理 {data_count} 条数据 | 价格: {data.close:.2f} | 持仓: {len(status['positions'])}层")
                
    except KeyboardInterrupt:
        print("\n用户中断")
        engine.stop()
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='CTS1 - Grid RSI Trading System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s backtest --data btc_1m.csv
  %(prog)s paper --data btc_1m.csv --port 5000
  %(prog)s live --demo --api-key xxx --secret xxx --passphrase xxx
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='运行模式')
    
    # 回测模式
    backtest_parser = subparsers.add_parser('backtest', help='回测模式')
    backtest_parser.add_argument('--data', default='btc_1m.csv', help='数据文件')
    backtest_parser.add_argument('--symbol', default='BTC-USDT', help='交易对')
    backtest_parser.add_argument('--capital', type=float, default=10000, help='初始资金')
    backtest_parser.add_argument('--grid-levels', type=int, default=10, help='网格层数')
    backtest_parser.add_argument('--rsi-period', type=int, default=14, help='RSI周期')
    backtest_parser.add_argument('--strategy', default='4.0', choices=['4.0', '5.1'], help='策略版本')
    backtest_parser.set_defaults(func=run_backtest)
    
    # 模拟盘模式
    paper_parser = subparsers.add_parser('paper', help='模拟盘模式')
    paper_parser.add_argument('--data', default='btc_1m.csv', help='数据文件')
    paper_parser.add_argument('--symbol', default='BTC-USDT', help='交易对')
    paper_parser.add_argument('--capital', type=float, default=10000, help='初始资金')
    paper_parser.add_argument('--port', type=int, default=5000, help='Dashboard端口')
    paper_parser.add_argument('--strategy', default='4.0', choices=['4.0', '5.1'], help='策略版本')
    paper_parser.set_defaults(func=run_paper)
    
    # 实盘模式
    live_parser = subparsers.add_parser('live', help='实盘模式')
    live_parser.add_argument('--symbol', default='BTC-USDT', help='交易对')
    live_parser.add_argument('--timeframe', default='1m', help='K线周期')
    live_parser.add_argument('--api-key', help='API Key')
    live_parser.add_argument('--secret', help='API Secret')
    live_parser.add_argument('--passphrase', help='Passphrase')
    live_parser.add_argument('--demo', action='store_true', help='使用模拟盘')
    live_parser.add_argument('--port', type=int, default=5000, help='Dashboard端口')
    live_parser.add_argument('--strategy', default='4.0', choices=['4.0', '5.1'], help='策略版本')
    live_parser.set_defaults(func=run_live)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
