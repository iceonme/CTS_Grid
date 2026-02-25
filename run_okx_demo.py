"""
OKX 模拟盘一键启动脚本
无需命令行参数，直接使用配置好的 API

使用方法:
    python run_okx_demo.py
"""

import sys
import os
import time

# 确保模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from strategies import GridRSIStrategy
from executors import OKXExecutor
from datafeeds import OKXDataFeed
from engines import LiveEngine
from dashboard import create_dashboard
from config.api_config import OKX_DEMO_CONFIG, DEFAULT_SYMBOL, DEFAULT_TIMEFRAME


def main():
    print("\n" + "="*60)
    print("CTS1 - OKX 模拟盘一键启动")
    print("="*60)
    print(f"交易对: {DEFAULT_SYMBOL}")
    print(f"K线周期: {DEFAULT_TIMEFRAME}")
    print(f"API Key: {OKX_DEMO_CONFIG['api_key'][:8]}...")
    print("="*60 + "\n")
    
    # 1. 启动 Dashboard
    print("[1/4] 启动 Dashboard...")
    dashboard = create_dashboard(port=5000)
    dashboard.start_background()
    time.sleep(1)  # 等待 Dashboard 启动

    session_start = datetime.now()
    
    # 2. 创建策略
    print("[2/4] 初始化策略...")
    strategy = GridRSIStrategy(
        symbol=DEFAULT_SYMBOL,
        grid_levels=10,
        use_kelly_sizing=True,
        trailing_stop=True
    )
    
    # 3. 创建 OKX 执行器（模拟盘）
    print("[3/4] 连接 OKX 模拟盘...")
    executor = OKXExecutor(
        api_key=OKX_DEMO_CONFIG['api_key'],
        api_secret=OKX_DEMO_CONFIG['api_secret'],
        passphrase=OKX_DEMO_CONFIG['passphrase'],
        is_demo=True
    )
    
    # 测试连接并获取初始余额
    initial_balance = None
    try:
        # 获取总权益（USDT + 其他币折算）
        total_value = executor.get_total_value() if hasattr(executor, 'get_total_value') else None
        balance_detail = executor.api.get_balance()
        if total_value and total_value > 0:
            initial_balance = total_value
            print(f"      连接成功! 初始权益: {initial_balance:.2f} USDT")
        elif balance_detail:
            print(f"      API返回余额详情:")
            print(f"        availBal (可用): {balance_detail['availBal']}")
            print(f"        eq (总权益): {balance_detail['eq']}")
            print(f"        raw: {balance_detail.get('raw', {})}")
            initial_balance = balance_detail['eq']  # 退回使用 USDT 权益
            print(f"      连接成功! 初始权益: {initial_balance:.2f} USDT")
        else:
            print(f"      警告: API返回空余额信息")
            initial_balance = 3000  # 默认值
    except Exception as e:
        print(f"      连接测试失败: {e}")
        import traceback
        traceback.print_exc()
        print("      使用默认初始资金: 3000 USDT")
        initial_balance = 3000
    
    # 4. 创建数据流
    print("[4/4] 启动数据流...")
    data_feed = OKXDataFeed(
        symbol=DEFAULT_SYMBOL,
        timeframe=DEFAULT_TIMEFRAME,
        api_key=OKX_DEMO_CONFIG['api_key'],
        api_secret=OKX_DEMO_CONFIG['api_secret'],
        passphrase=OKX_DEMO_CONFIG['passphrase'],
        is_demo=True,
        poll_interval=2.0
    )
    
    # 5. 创建引擎
    engine = LiveEngine(
        strategy=strategy,
        executor=executor,
        data_feed=data_feed,
        warmup_bars=100
    )
    
    # 注册 Dashboard 回调 - 转换数据格式
    update_count = [0]  # 使用列表来在闭包中修改
    last_context = [None]  # 保存最新的 context
    
    def on_status_update(status):
        update_count[0] += 1
        
        # 保存 context 用于策略状态获取
        from core import StrategyContext, Position
        positions_input = status.get('positions') or {}
        positions_map = {}
        if isinstance(positions_input, dict):
            for sym, size in positions_input.items():
                positions_map[sym] = Position(
                    symbol=sym,
                    size=size,
                    avg_price=0.0,
                    entry_time=datetime.now(),
                    unrealized_pnl=0.0
                )
        else:
            for p in positions_input:
                positions_map[p['symbol']] = Position(
                    symbol=p['symbol'],
                    size=p['size'],
                    avg_price=p.get('avg_price', 0),
                    entry_time=datetime.now(),
                    unrealized_pnl=p.get('unrealized_pnl', 0)
                )

        context = StrategyContext(
            timestamp=datetime.fromisoformat(status['timestamp']),
            cash=status['cash'],
            positions=positions_map,
            current_prices={status['symbol']: status['price']}
        )
        last_context[0] = context
        
        # 更新策略内部价格缓存
        strategy._current_prices = {status['symbol']: status['price']}
        
        # 转换为 Dashboard 期望的格式
        timestamp_ms = int(datetime.fromisoformat(status['timestamp']).timestamp() * 1000)
        
        # 计算 PNL
        if initial_balance and initial_balance > 0:
            pnl_pct = (status['total_value'] - initial_balance) / initial_balance * 100
        else:
            pnl_pct = 0
        
        # 获取策略状态
        strategy_status = strategy.get_status(context)
        
        trade_history = status.get('trade_history', []) or status.get('trades', [])
        # 仅展示本次页面刷新后的交易记录
        filtered_trades = []
        for t in trade_history:
            t_time = t.get('time')
            if not t_time:
                continue
            try:
                trade_dt = datetime.fromisoformat(t_time.replace('Z', '+00:00'))
            except Exception:
                continue
            if trade_dt >= session_start:
                filtered_trades.append(t)
        dashboard_data = {
            'timestamp': status['timestamp'],
            'prices': {status['symbol']: status['price']},
            'candle': {
                't': timestamp_ms,
                'o': status.get('open', status['price']),
                'h': status.get('high', status['price']),
                'l': status.get('low', status['price']),
                'c': status['price']
            },
            'total_value': status['total_value'],
            'cash': status['cash'],
            'position_value': status['position_value'],
            'positions': (
                {status['symbol']: sum(p['size'] for p in status['positions'])}
                if isinstance(positions_input, list)
                else positions_input
            ),
            'pnl_pct': round(pnl_pct, 4),
            'initial_balance': initial_balance or 3000,
            'rsi': getattr(strategy.state, 'current_rsi', 50),
            'trade_history': filtered_trades,
            'strategy': strategy_status
        }
        
        # 每 10 次更新打印一次日志
        if update_count[0] % 10 == 0:
            print(f"[更新 #{update_count[0]}] 价格: {status['price']:.2f}, 资产: {status['total_value']:.2f}, PNL: {pnl_pct:.2f}%")
        
        dashboard.update(dashboard_data)
    
    engine.register_status_callback(on_status_update)
    
    # 6. 预热并发送初始数据到 Dashboard
    print("\n[5/5] 预热策略并初始化 Dashboard...")
    engine.warmup()  # 这会获取历史数据
    
    # 构建并发送预热数据给 Dashboard
    print(f"  strategy._data_buffer 长度: {len(strategy._data_buffer)}")
    if len(strategy._data_buffer) > 0:
        print(f"  准备发送 {len(strategy._data_buffer)} 条历史数据到 Dashboard")
        
        # 转换历史数据为 Dashboard 格式
        history_candles = []
        history_rsi = []
        history_equity = []
        equity_baseline = initial_balance or 3000
        
        for i, data in enumerate(strategy._data_buffer):
            ts_ms = int(data.timestamp.timestamp() * 1000)
            
            # K线数据
            history_candles.append({
                't': ts_ms,
                'o': data.open,
                'h': data.high,
                'l': data.low,
                'c': data.close
            })
            
            # RSI 数据（前 rsi_period 条为 null）
            if i >= strategy.params['rsi_period']:
                # 重新计算该时间点的 RSI
                df = strategy._get_dataframe()
                if i < len(df):
                    rsi = strategy._calculate_rsi(df['close'].iloc[:i+1])
                    history_rsi.append({'t': ts_ms, 'v': rsi})
                else:
                    history_rsi.append({'t': ts_ms, 'v': None})
            else:
                history_rsi.append({'t': ts_ms, 'v': None})
            
            # 资产数据：使用初始资金作为基线，避免图表出现 0 -> 初始资金 的断崖
            history_equity.append({'t': ts_ms, 'v': equity_baseline})
        
        
        # 获取当前价格和余额
        current_price = strategy._data_buffer[-1].close if strategy._data_buffer else 0
        current_cash = executor.get_cash()
        
        # 构建初始状态
        warmup_data = {
            'history_candles': history_candles,
            'history_rsi': history_rsi,
            'history_equity': history_equity,
            'prices': {DEFAULT_SYMBOL: current_price},
            'candle': {
                't': history_candles[-1]['t'] if history_candles else int(datetime.now().timestamp() * 1000),
                'o': history_candles[-1]['o'] if history_candles else current_price,
                'h': history_candles[-1]['h'] if history_candles else current_price,
                'l': history_candles[-1]['l'] if history_candles else current_price,
                'c': history_candles[-1]['c'] if history_candles else current_price,
            },
            'total_value': initial_balance or 3000,
            'cash': current_cash,
            'position_value': 0,
            'positions': {DEFAULT_SYMBOL: 0},
            'pnl_pct': 0,
            'initial_balance': initial_balance or 3000,
            'rsi': getattr(strategy.state, 'current_rsi', 50),
            'trade_history': [],
            'strategy': strategy.get_status(None)
        }
        
        dashboard.update(warmup_data)
        print("  预热数据已发送到 Dashboard")
    
    print("\n" + "="*60)
    print("启动完成!")
    print("Dashboard: http://localhost:5000")
    print("按 Ctrl+C 停止")
    print("="*60 + "\n")
    
    # 7. 运行引擎主循环
    try:
        engine.run()
    except KeyboardInterrupt:
        print("\n正在停止...")
        engine.stop()
        print("已停止")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
