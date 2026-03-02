
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

from datetime import datetime, timezone
from strategies import GridRSIStrategy
from executors.paper import PaperExecutor
from executors import OKXExecutor
from datafeeds import OKXDataFeed
from engines import LiveEngine
from dashboard import create_dashboard
from config.api_config import OKX_DEMO_CONFIG, DEFAULT_SYMBOL, DEFAULT_TIMEFRAME

STRATEGY_ID = "grid_rsi_demo_01"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"trading_state_{STRATEGY_ID}.json")
TRADES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"trading_trades_{STRATEGY_ID}.json")


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
    if dashboard:
        dashboard.register_strategy(STRATEGY_ID, f"Grid RSI V4 ({DEFAULT_SYMBOL})")

    session_start = datetime.now(timezone.utc)
    
    # 2. 创建策略
    print("[2/4] 初始化策略...")
    strategy = GridRSIStrategy(
        symbol=DEFAULT_SYMBOL,
        grid_levels=10,
        use_kelly_sizing=True,
        trailing_stop=True
    )
    
    # 3. 创建本地模拟执行器 (PaperExecutor)
    print("[3/4] 初始化本地虚拟账户...")
    initial_balance = 10000.0  # 初始 10000 USDT
    executor = PaperExecutor(
        initial_capital=initial_balance,
        fee_rate=0.0,            # 简化：免除手续费
        slippage_model='none'    # 简化：去除滑点
    )
    print(f"      虚拟账户创建成功! 初始权益: {initial_balance:.2f} USDT")
    
    if executor.load_state(STATE_FILE):
        print(f"      已从上次运行恢复账户状态: 余额 {executor.get_cash():.2f}")

    # 4. 创建数据流 (依然使用实盘行情数据)
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
        warmup_bars=200
    )
    
    # 加载交易历史
    engine.load_trades(TRADES_FILE)
    
    # 注册 Dashboard 回调 - 转换数据格式
    update_count = [0]  # 使用列表来在闭包中修改
    last_context = [None]  # 保存最新的 context
    last_trade_count = [len(engine._trades)]
    
    def on_status_update(status):
        update_count[0] += 1
        
        # 保存 context 用于策略状态获取
        from core import StrategyContext, Position
        positions_input = status.get('positions') or {}
        positions_map = {}
        if isinstance(positions_input, dict):
            for sym, p_data in positions_input.items():
                if isinstance(p_data, dict):
                    positions_map[sym] = Position(
                        symbol=sym,
                        size=p_data.get('size', 0.0),
                        avg_price=p_data.get('avg_price', 0.0),
                        entry_time=datetime.now(timezone.utc),
                        unrealized_pnl=p_data.get('unrealized_pnl', 0.0)
                    )
                else:
                    positions_map[sym] = Position(
                        symbol=sym,
                        size=p_data,
                        avg_price=0.0,
                        entry_time=datetime.now(timezone.utc),
                        unrealized_pnl=0.0
                    )
        else:
            for p in positions_input:
                positions_map[p['symbol']] = Position(
                    symbol=p['symbol'],
                    size=p['size'],
                    avg_price=p.get('avg_price', 0),
                    entry_time=datetime.now(timezone.utc),
                    unrealized_pnl=p.get('unrealized_pnl', 0)
                )

        t_stamp = datetime.fromisoformat(status['timestamp'].replace('Z', '+00:00'))
        if t_stamp.tzinfo is None:
            t_stamp = t_stamp.replace(tzinfo=timezone.utc)

        context = StrategyContext(
            timestamp=t_stamp,
            cash=status['cash'],
            positions=positions_map,
            current_prices={status['symbol']: status['price']}
        )
        last_context[0] = context
        
        # 更新策略内部价格缓存
        strategy._current_prices = {status['symbol']: status['price']}
        
        # 转换为 Dashboard 期望的格式 (确保解析为 UTC)
        try:
            dt_raw = datetime.fromisoformat(status['timestamp'].replace('Z', '+00:00'))
            if dt_raw.tzinfo is None:
                dt_raw = dt_raw.replace(tzinfo=timezone.utc)
            timestamp_ms = int(dt_raw.timestamp() * 1000)
        except Exception:
            timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        # 计算 PNL
        if initial_balance and initial_balance > 0:
            pnl_pct = (status['total_value'] - initial_balance) / initial_balance * 100
        else:
            pnl_pct = 0
        
        # 获取策略状态
        strategy_status = strategy.get_status(context)
        
        trade_history = status.get('trade_history', []) or status.get('trades', [])
        # 保留所有历史交易
        filtered_trades = trade_history
        
        dashboard_data = {
            'timestamp': timestamp_ms,  # 避免字符串覆写前端数字格式
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
            'rsi': strategy_status.get('current_rsi', getattr(strategy.state, 'current_rsi', 50)) if hasattr(strategy, 'state') else strategy_status.get('current_rsi', 50),
            'trade_history': filtered_trades,
            'strategy': strategy_status
        }
        
        if dashboard:
            # 维护历史数据缓存，防止刷新页面产生断层 (适配多策略架构)
            current_candle = dashboard_data['candle']
            def_data = dashboard._data.get(STRATEGY_ID, {})
            
            # 1. 更新 K 线历史
            hc = def_data.get('history_candles', [])
            if hc:
                if hc[-1]['t'] == current_candle['t']:
                    hc[-1] = current_candle
                else:
                    hc.append(current_candle)
                    if len(hc) > 500: hc.pop(0)
            
            # 2. 更新 RSI 历史
            hrsi = def_data.get('history_rsi', [])
            if hrsi:
                current_rsi = dashboard_data['rsi']
                if hrsi[-1]['t'] == current_candle['t']:
                    hrsi[-1]['v'] = current_rsi
                else:
                    hrsi.append({'t': current_candle['t'], 'v': current_rsi})
                    if len(hrsi) > 500: hrsi.pop(0)
            
            # 3. 更新资产历史
            heq = def_data.get('history_equity', [])
            if heq:
                current_total = dashboard_data['total_value']
                if heq[-1]['t'] == current_candle['t']:
                    heq[-1]['v'] = current_total
                else:
                    heq.append({'t': current_candle['t'], 'v': current_total})
                    if len(heq) > 500: heq.pop(0)

            dashboard.update(dashboard_data, strategy_id=STRATEGY_ID)
            
            # 仅在发生实质交易变化时保存状态，避免每秒写盘
            if len(engine._trades) > last_trade_count[0]:
                executor.save_state(STATE_FILE)
                engine.save_trades(TRADES_FILE)
                last_trade_count[0] = len(engine._trades)
                print(f"[Demo] 交易发生，状态已持久化 (成交数: {last_trade_count[0]})")

    
    engine.register_status_callback(on_status_update)
    
    # --- Dashboard 数据初始化函数 ---
    def send_warmup_to_dashboard():
        if not dashboard:
            return
            
        if not strategy._data_buffer:
            print("[Demo] 警告: 策略数据缓存为空，跳过预热同步 (等待实时数据...)")
            return
            
        print(f"[Demo] 准备同步预热数据 (Buffer: {len(strategy._data_buffer)})")
        
        history_candles = []
        history_rsi = []
        history_equity = []
        
        # 资产数据重构
        from core import Side
        sim_cash = initial_balance or 10000.0
        sim_pos = 0.0
        trades_sorted = sorted(engine._trades, key=lambda x: str(x['time']))
        trade_idx = 0
        
        for i, data in enumerate(strategy._data_buffer):
            ts_ms = int(data.timestamp.timestamp() * 1000)
            
            history_candles.append({
                't': ts_ms, 'o': data.open, 'h': data.high, 'l': data.low, 'c': data.close
            })
            
            # RSI
            if i >= strategy.params['rsi_period']:
                df = strategy._get_dataframe()
                if i < len(df):
                    rsi = strategy._calculate_rsi(df['close'].iloc[:i+1])
                    history_rsi.append({'t': ts_ms, 'v': rsi})
                else:
                    history_rsi.append({'t': ts_ms, 'v': None})
            else:
                history_rsi.append({'t': ts_ms, 'v': None})
            
            # Equity Reconstruct
            while trade_idx < len(trades_sorted):
                t = trades_sorted[trade_idx]
                try:
                    t_dt = datetime.fromisoformat(t['time'].replace('Z', '+00:00'))
                    t_ms = int(t_dt.timestamp() * 1000)
                    if t_ms <= ts_ms:
                        side, size, price, fee = t['side'], float(t['size']), float(t['price']), float(t['fee'] or 0)
                        if side in ['buy', Side.BUY, 'BUY']:
                            sim_cash -= (size * price + fee)
                            sim_pos += size
                        else:
                            sim_cash += (size * price - fee)
                            sim_pos -= size
                        trade_idx += 1
                    else: break
                except Exception: trade_idx += 1
            
            equity = sim_cash + sim_pos * data.close
            history_equity.append({'t': ts_ms, 'v': equity})
        
        current_candle = history_candles[-1]
        current_price = strategy._data_buffer[-1].close
        current_cash = executor.get_cash()
        
        warmup_data = {
            'history_candles': history_candles,
            'history_rsi': history_rsi,
            'history_equity': history_equity,
            'prices': {DEFAULT_SYMBOL: current_price},
            'candle': current_candle,
            'total_value': history_equity[-1]['v'],
            'cash': current_cash,
            'position_value': sim_pos * current_price,
            'positions': {DEFAULT_SYMBOL: sim_pos},
            'pnl_pct': (history_equity[-1]['v'] / (initial_balance or 10000.0) - 1) * 100,
            'initial_balance': initial_balance or 10000.0,
            'rsi': history_rsi[-1]['v'] if history_rsi and history_rsi[-1]['v'] is not None else 50,
            'trade_history': trades_sorted,
            'strategy': strategy.get_status(None)
        }
        dashboard.update(warmup_data, strategy_id=STRATEGY_ID)
        print("  Dashboard 初始化数据同步完成")

    # --- 重置处理器 ---
    def handle_dashboard_reset():
        print("\n[Demo] >>> 正在执行全局重置流程 <<<")
        # 1. 停止引擎当前循环
        engine._is_warmed = False 
        
        # 2. 清理各组件状态
        executor.reset()
        strategy.initialize()
        engine._trades.clear()
        engine._history_candles.clear()
        last_trade_count[0] = 0
        
        # 3. 删除持久化文件
        for f_path in [STATE_FILE, TRADES_FILE]:
            if os.path.exists(f_path):
                try:
                    os.remove(f_path)
                    print(f"  已删除文件: {os.path.basename(f_path)}")
                except Exception as e:
                    print(f"  删除文件失败 {f_path}: {e}")
        
        # 4. 重新进行一次预热以获取最新数据（同步）
        engine.warmup()
        
        # 5. 通知 Dashboard
        if dashboard:
            # 清空 Dashboard 内部缓存并通知前端重置 UI
            dashboard.reset_ui()
            send_warmup_to_dashboard()
            
        print("[Demo] 重置完成，系统已恢复初始状态。\n")

    if dashboard:
        dashboard.on_reset_callback = handle_dashboard_reset

    # 6. 首次运行预热
    print("\n[5/5] 预热策略并初始化 Dashboard...")
    engine.warmup()
    send_warmup_to_dashboard()

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
