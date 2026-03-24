import eventlet
eventlet.monkey_patch()

"""
OKX 真实模拟盘启动脚本
使用 OKXExecutor 连接真实 OKX 模拟环境，并过滤非 BTC/USDT 资产
计算独立收益率并暴露在 4000 端口

使用方法:
    python run_okx_mock.py
"""

import sys
import os
import json
import time
import pandas as pd

# 确保模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timezone
from strategies import GridRSIStrategy
from executors.okx import OKXExecutor
from datafeeds import OKXDataFeed
from engines import LiveEngine
from dashboard import create_dashboard
from config.api_config import OKX_MOCK_CONFIG, DEFAULT_SYMBOL, DEFAULT_TIMEFRAME
from flask import request, jsonify

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trading_state_mock.json")
TRADES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trading_trades_mock.json")

# 全局重启标志
_restart_requested = False
_restart_callback = None


class MockFilteredOKXExecutor(OKXExecutor):
    """
    针对 OKX 模拟盘的过滤执行器
    因为模拟盘常发放多种测试币(ETH, OKB等)，这里只计算 BTC / USDT，以保证收益率(PNL)计算的准确性。
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial_anchor_balance = None
        self.ALLOWED_CCYS = ['BTC', 'USDT']
    
    def get_total_value(self) -> float:
        """重写：只计算 BTC 和 USDT 的总资产折算"""
        balances = self.api.get_balances()
        if not balances:
            return 0.0

        total = 0.0
        for asset in balances.get('details', []):
            ccy = asset.get('ccy')
            if not ccy or ccy not in self.ALLOWED_CCYS:
                continue
            eq = float(asset.get('eq', 0) or 0)
            if abs(eq) < 1e-12:
                continue
            if ccy == 'USDT':
                total += eq
                continue
            
            inst_id = f"{ccy}-USDT"
            px = self._get_reference_price(inst_id)
            if px:
                total += eq * px
        return total

    def _get_positions_from_api(self):
        """重写：只获取 BTC-USDT 持仓"""
        pos_list = super()._get_positions_from_api()
        return [p for p in pos_list if p.symbol == 'BTC-USDT']

    def _get_positions_from_balance(self):
        """重写：只获取 BTC-USDT 持仓"""
        pos_list = super()._get_positions_from_balance()
        return [p for p in pos_list if p.symbol == 'BTC-USDT']

    def _on_fill_update_position(self, fill):
        """重写：更新持仓后立刻保存状态"""
        super()._on_fill_update_position(fill)
        if hasattr(self, 'state_file') and self.state_file:
            self.save_state(self.state_file)

    def load_state(self, path: str) -> bool:
        """加载本地状态信息（独立锚定的初始本金和本地持仓）"""
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'initial_anchor_balance' in data:
                        self.initial_anchor_balance = data.get('initial_anchor_balance', None)
                    if 'local_positions' in data:
                        pos_data = data['local_positions']
                        for sym, p in pos_data.items():
                            if 'entry_time' in p and isinstance(p['entry_time'], str):
                                try:
                                    p['entry_time'] = datetime.fromisoformat(p['entry_time'])
                                except Exception:
                                    p['entry_time'] = datetime.now(timezone.utc)
                        self._local_positions = pos_data
                    return True
            except Exception as e:
                print(f"[加载状态报错] {e}")
        return False
        
    def save_state(self, path: str):
        """保存本地状态信息"""
        try:
            pos_data = {}
            for sym, p in self._local_positions.items():
                p_copy = p.copy()
                if isinstance(p_copy.get('entry_time'), datetime):
                    p_copy['entry_time'] = p_copy['entry_time'].isoformat()
                pos_data[sym] = p_copy
                
            data = {
                "initial_anchor_balance": self.initial_anchor_balance,
                "local_positions": pos_data
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[保存状态报错] {e}")


def main():
    print("\n" + "="*60)
    print("CTS1 - OKX 真实模拟盘 (Filtered: BTC & USDT)")
    print("="*60)
    print(f"交易对: {DEFAULT_SYMBOL}")
    print(f"K线周期: {DEFAULT_TIMEFRAME}")
    print(f"API Key: {OKX_MOCK_CONFIG['api_key'][:8]}...")
    print("="*60 + "\n")
    
    # 1. 启动 Dashboard (Port: 4000)
    print("[1/4] 启动 Dashboard (Port: 4000)...")
    dashboard = create_dashboard(port=4000)
    
    # 添加重启API端点
    @dashboard.app.route('/api/restart', methods=['POST'])
    def restart_strategy():
        global _restart_requested
        try:
            # 清空状态文件
            if os.path.exists(STATE_FILE):
                os.remove(STATE_FILE)
                print(f"[重启API] 已删除状态文件: {STATE_FILE}")
            if os.path.exists(TRADES_FILE):
                os.remove(TRADES_FILE)
                print(f"[重启API] 已删除交易记录: {TRADES_FILE}")
            
            _restart_requested = True
            print("[重启API] 重启标志已设置")
            return jsonify({'status': 'success', 'message': '重启请求已接收，程序将在下次检查点重启'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
    
    @dashboard.app.route('/api/status', methods=['GET'])
    def get_status():
        return jsonify({
            'restart_requested': _restart_requested,
            'state_file_exists': os.path.exists(STATE_FILE),
            'trades_file_exists': os.path.exists(TRADES_FILE)
        })
    
    dashboard.start_background()
    time.sleep(1)

    session_start = datetime.now(timezone.utc)
    
    # 2. 创建策略
    print("[2/4] 初始化策略...")
    strategy = GridRSIStrategy(
        symbol=DEFAULT_SYMBOL,
        grid_levels=10,
        use_kelly_sizing=True,
        trailing_stop=True
    )
    
    # 3. 创建执行器
    print("[3/4] 初始化与连接 OKX 模拟盘账户...")
    executor = MockFilteredOKXExecutor(
        api_key=OKX_MOCK_CONFIG['api_key'],
        api_secret=OKX_MOCK_CONFIG['api_secret'],
        passphrase=OKX_MOCK_CONFIG['passphrase'],
        is_demo=True
    )
    executor.state_file = STATE_FILE
    
    if executor.load_state(STATE_FILE):
        if executor.initial_anchor_balance is not None:
            print(f"      已恢复初始本地锚定本金: {executor.initial_anchor_balance:.2f} USDT")
        if executor._local_positions:
            print(f"      已恢复 {len(executor._local_positions)} 个本地持仓记忆")
    else:
        # 首次获取纯 BTC/USDT 资产并锚定
        executor.initial_anchor_balance = executor.get_total_value()
        executor.save_state(STATE_FILE)
        print(f"      创建全新底仓锚定记录: {executor.initial_anchor_balance:.2f} USDT")

    # 4. 创建数据流
    print("[4/4] 启动实时数据流...")
    data_feed = OKXDataFeed(
        symbol=DEFAULT_SYMBOL,
        timeframe=DEFAULT_TIMEFRAME,
        api_key=OKX_MOCK_CONFIG['api_key'],
        api_secret=OKX_MOCK_CONFIG['api_secret'],
        passphrase=OKX_MOCK_CONFIG['passphrase'],
        is_demo=True,
        poll_interval=1.0
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
    update_count = [0]
    last_context = [None]
    last_trade_count = [len(engine._trades)]
    
    def on_status_update(status):
        update_count[0] += 1
        
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
            t_stamp = t_stamp.astimezone(timezone.utc)
            
        context = StrategyContext(
            timestamp=t_stamp,
            cash=status['cash'],
            positions=positions_map,
            current_prices={status['symbol']: status['price']}
        )
        last_context[0] = context
        
        # 更新策略内部价格缓存
        strategy._current_prices = {status['symbol']: status['price']}
        
        try:
            dt_raw = datetime.fromisoformat(status['timestamp'].replace('Z', '+00:00'))
            if dt_raw.tzinfo is None:
                dt_raw = dt_raw.replace(tzinfo=timezone.utc)
            timestamp_ms = int(dt_raw.timestamp() * 1000)
        except Exception:
            timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        # 计算 PNL
        anchor_bal = executor.initial_anchor_balance or (status['total_value'] if status['total_value'] > 0 else 10000.0)
        pnl_pct = (status['total_value'] - anchor_bal) / anchor_bal * 100 if anchor_bal > 0 else 0
            
        strategy_status = strategy.get_status(context)
        trade_history = status.get('trade_history', []) or status.get('trades', [])
        
        # 处理仓位大小显示
        positions_raw = status.get('positions', {})
        total_pos_size = 0.0
        avg_price = 0.0
        
        if isinstance(positions_raw, dict):
            for p_val in positions_raw.values():
                if isinstance(p_val, dict):
                    total_pos_size += p_val.get('size', 0.0)
                    if p_val.get('avg_price'):
                        avg_price = p_val.get('avg_price')
                else:
                    total_pos_size += float(p_val)
        elif isinstance(positions_raw, list):
            total_pos_size = sum(p['size'] for p in positions_raw)
            btc_pos = [p for p in positions_raw if 'BTC' in p.get('symbol', '')]
            if btc_pos:
                avg_price = btc_pos[0].get('avg_price', 0.0)

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
            'positions': {status['symbol']: {'size': total_pos_size, 'avg_price': avg_price}},
            'pnl_pct': round(pnl_pct, 4),
            'initial_balance': anchor_bal,
            'rsi': getattr(strategy.state, 'current_rsi', 50),
            'trade_history': trade_history,
            'strategy': strategy_status
        }
        
        if dashboard:
            # 维护 Dashboard 内部缓存
            current_candle = dashboard_data['candle']
            
            # 1. 更新 K 线历史
            hc = dashboard._data.get('history_candles')
            if hc is not None:
                if len(hc) > 0 and hc[-1]['t'] == current_candle['t']:
                    hc[-1] = current_candle
                else:
                    hc.append(current_candle)
                    if len(hc) > 1000: hc.pop(0)
            
            # 2. 更新 RSI 历史
            hrsi = dashboard._data.get('history_rsi')
            if hrsi is not None:
                current_rsi = dashboard_data['rsi']
                if len(hrsi) > 0 and hrsi[-1]['t'] == current_candle['t']:
                    hrsi[-1]['v'] = current_rsi
                else:
                    hrsi.append({'t': current_candle['t'], 'v': current_rsi})
                    if len(hrsi) > 1000: hrsi.pop(0)
            
            # 3. 更新资产历史
            heq = dashboard._data.get('history_equity')
            if heq is not None:
                current_total = dashboard_data['total_value']
                if len(heq) > 0 and heq[-1]['t'] == current_candle['t']:
                    heq[-1]['v'] = current_total
                else:
                    heq.append({'t': current_candle['t'], 'v': current_total})
                    if len(heq) > 1000: heq.pop(0)

            # 发送更新（不重复发送大的历史列表，前端已有缓存）
            dashboard.update(dashboard_data)
            
            # 检查重启请求
            global _restart_requested
            if _restart_requested:
                print("\n[重启] 检测到重启请求，正在清理并退出...")
                executor.save_state(STATE_FILE)
                engine.save_trades(TRADES_FILE)
                print("[重启] 状态已保存，准备重启")
                os._exit(0)  # 强制退出，让外部重启脚本接管
            
            # 持久化状态
            if len(engine._trades) > last_trade_count[0]:
                executor.save_state(STATE_FILE)
                engine.save_trades(TRADES_FILE)
                last_trade_count[0] = len(engine._trades)
                print(f"[Mock] 交易发生，状态已持久化 (成交数: {last_trade_count[0]})")

    engine.register_status_callback(on_status_update)
    
    # --- Dashboard 数据初始化函数 ---
    def send_warmup_to_dashboard():
        """发送初始历史数据给 Dashboard"""
        if not dashboard: return
        
        history_candles = []
        history_rsi = []
        history_equity = []
        
        # 获取当前的真实资产状况作为回溯模拟的基础，使历史曲线与当前对齐
        current_pos_obj = executor.get_position(strategy.symbol)
        current_pos = current_pos_obj.size if current_pos_obj else 0.0
        current_cash = executor.get_cash()
        
        # 定义 anchor_bal 用于 PNL 计算
        anchor_bal = getattr(executor, 'initial_anchor_balance', None) or (executor.get_total_value() or 10000.0)
        
        # 正确的回溯模拟逻辑：
        # 1. 先从当前状态“倒带”，撤销掉 buffer 时间范围内的所有交易，得到 buffer 起始点的现金和持仓。
        # 2. 然后再随着 K 线正向重放这些交易。
        
        if not strategy._data_buffer:
            print("[Warning] strategy._data_buffer is empty during warmup!")
            return

        first_candle_ms = int(pd.to_datetime(strategy._data_buffer[0].timestamp, utc=True).timestamp() * 1000)
        trades_sorted = sorted(engine._trades, key=lambda x: str(x['time']))
        
        sim_pos = current_pos
        sim_cash = current_cash
        
        # 倒带：从最新成交往回推算起始点
        for t in reversed(trades_sorted):
            try:
                t_dt = datetime.fromisoformat(t['time'].replace('Z', '+00:00'))
                if t_dt.tzinfo is None: t_dt = t_dt.replace(tzinfo=timezone.utc)
                if int(t_dt.timestamp() * 1000) > first_candle_ms:
                    side = t['type'] if 'type' in t else t.get('side', 'BUY')
                    size = float(t['size'])
                    price = float(t['price'])
                    fee = float(t.get('fee', 0))
                    if side.upper() == 'BUY':
                        sim_cash += (size * price + fee)
                        sim_pos -= size
                    else:
                        sim_cash -= (size * price - fee)
                        sim_pos += size
            except Exception: continue
            
        trade_idx = 0

        for i, data in enumerate(strategy._data_buffer):
            dt_utc = data.timestamp.replace(tzinfo=timezone.utc) if data.timestamp.tzinfo is None else data.timestamp
            ts_ms = int(dt_utc.timestamp() * 1000)
            
            history_candles.append({
                't': ts_ms, 'o': data.open, 'h': data.high, 'l': data.low, 'c': data.close
            })
            
            # 计算 RSI 历史
            if i >= strategy.params['rsi_period']:
                df = strategy._get_dataframe()
                if i < len(df):
                    rsi_val = strategy._calculate_rsi(df['close'].iloc[:i+1])
                    history_rsi.append({'t': ts_ms, 'v': rsi_val})
                else:
                    history_rsi.append({'t': ts_ms, 'v': None})
            else:
                history_rsi.append({'t': ts_ms, 'v': None})
            
            # 计算资产历史 (模拟交易回放)
            while trade_idx < len(trades_sorted):
                t = trades_sorted[trade_idx]
                try:
                    # Ensure trade timestamp is UTC
                    t_dt = datetime.fromisoformat(t['time'].replace('Z', '+00:00'))
                    if t_dt.tzinfo is None:
                        t_dt = t_dt.replace(tzinfo=timezone.utc)
                    t_ms = int(t_dt.timestamp() * 1000)
                    if t_ms <= ts_ms:
                        side = t['type'] if 'type' in t else t.get('side', 'BUY')
                        size = float(t['size'])
                        price = float(t['price'])
                        fee = float(t.get('fee', 0))
                        if side.upper() in ['BUY']:
                            sim_cash -= (size * price + fee)
                            sim_pos += size
                        else:
                            sim_cash += (size * price - fee)
                            sim_pos -= size
                        trade_idx += 1
                    else: break
                except Exception: trade_idx += 1
            
            # 基于当前持仓和当时价格，计算“如果持有当前仓位，当时的总资产是多少”
            # 这样可以保证历史曲线的末端与实时的 total_value 完美对接，消除突变
            equity = sim_cash + sim_pos * data.close
            history_equity.append({'t': ts_ms, 'v': equity})
        
        final_price = strategy._data_buffer[-1].close
        final_cash = executor.get_cash()
        
        # 为所有成交记录注入数字时间戳，彻底消除 8 小时偏移风险
        normalized_trades = []
        for t in trades_sorted:
            try:
                t_dt = datetime.fromisoformat(t['time'].replace('Z', '+00:00'))
                if t_dt.tzinfo is None: t_dt = t_dt.replace(tzinfo=timezone.utc)
                t['t'] = int(t_dt.timestamp() * 1000)
            except Exception: t['t'] = None
            normalized_trades.append(t)

        warmup_data = {
            'history_candles': history_candles,
            'history_rsi': history_rsi,
            'history_equity': history_equity,
            'prices': {strategy.symbol: final_price},
            'candle': history_candles[-1] if history_candles else {},
            'total_value': history_equity[-1]['v'] if history_equity else anchor_bal,
            'cash': final_cash,
            'position_value': sim_pos * final_price,
            'positions': {strategy.symbol: sim_pos},
            'pnl_pct': ((history_equity[-1]['v'] / anchor_bal - 1) * 100) if history_equity and anchor_bal > 0 else 0,
            'initial_balance': anchor_bal,
            'rsi': history_rsi[-1]['v'] if history_rsi else 50,
            'trade_history': normalized_trades,
            'strategy': strategy.get_status(None)
        }
        dashboard.update(warmup_data)
        print("  Dashboard 初始化数据同步完成")

    # --- 重置处理器 ---
    def handle_dashboard_reset():
        print("\n[Mock] >>> 正在执行全局重置流程 <<<")
        
        # 1. 重新锚定本金为当前的纯净总权益 (BTC+USDT) 并清空本地持仓记忆
        current_total = executor.get_total_value()
        executor.initial_anchor_balance = current_total
        executor._local_positions.clear()
        executor.save_state(STATE_FILE)
        print(f"  [Mock] 已重新锚定本金基准为: {current_total:.2f} USDT，且已清空本地持仓轨迹")
        
        # 2. 引擎与策略状态彻底重置
        engine._is_warmed = False 
        strategy.initialize()
        engine._trades.clear()
        engine._history_candles.clear()
        last_trade_count[0] = 0
        
        # 3. 清空本地持久化文件
        if os.path.exists(TRADES_FILE):
            try:
                os.remove(TRADES_FILE)
                print(f"  [Mock] 已删除历史成交记录文件")
            except Exception: pass
            
        # 4. 清理 Dashboard 内部缓存并同步 UI
        if dashboard:
            # 显式清理缓存
            dashboard._data['history_candles'] = []
            dashboard._data['history_rsi'] = []
            dashboard._data['history_equity'] = []
            dashboard._data['trades'] = []
            dashboard._data['initial_balance'] = current_total
            
            # 发送重置信号
            dashboard.reset_ui()
            
            # 5. 重新预热并填充图表
            print("  [Mock] 正在重新执行数据预热...")
            engine.warmup()
            send_warmup_to_dashboard()
            
        print("[Mock] 重置流程执行完毕。\n")

    if dashboard:
        dashboard.on_reset_callback = handle_dashboard_reset

    # 6. 首次运行预热
    print("\n[5/5] 预热策略并初始化 Dashboard...")
    engine.warmup()
    send_warmup_to_dashboard()

    print("\n" + "="*60)
    print("启动完成!")
    print("Dashboard: http://localhost:4000")
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
