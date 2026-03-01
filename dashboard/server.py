
import threading
import json
from datetime import datetime
from typing import Dict, Any, Optional, List

from flask import Flask, render_template, jsonify, make_response, request
from flask_socketio import SocketIO, emit, join_room, leave_room


class DashboardServer:
    """
    Dashboard 服务器（多策略版）

    功能：
    1. 接收多条策略的状态更新（通过 strategy_id 区分）
    2. WebSocket Room 化：前端 join 特定策略房间，只收该策略的推送
    3. 提供 REST API（/api/status?strategy_id=xxx）
    """

    # 默认空数据模板
    _EMPTY_STRATEGY_DATA = lambda: {
        'prices':         {},
        'total_value':    0,
        'cash':           0,
        'position_value': 0,
        'positions':      {},
        'pnl_pct':        0,
        'rsi':            50,
        'trades':         [],
        'history_candles': [],
        'history_rsi':    [],
        'history_equity': [],
        'strategy':       {}
    }

    def __init__(self, host='0.0.0.0', port=5000):
        self.host = host
        self.port = port

        import os
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.app = Flask(__name__, 
                         static_folder=os.path.join(base_dir, 'static'),
                         template_folder=os.path.join(base_dir, 'templates'),
                         static_url_path='/static')
        self.app.config['SECRET_KEY'] = 'cts1-secret-key'
        self.app.config['TEMPLATES_AUTO_RELOAD'] = True

        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode='threading')

        # 静默 Flask/Werkzeug 的 HTTP 请求日志，减少终端噪音
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        # 多策略数据缓存：{strategy_id: {...}}
        self._data: Dict[str, Dict[str, Any]] = {}
        # 已注册的策略 ID 列表（保持顺序）
        self._strategy_ids: List[str] = []
        # 控制回调（由 MultiStrategyRunner 注入）
        self.on_control_callback: Optional[callable] = None
        # 重置回调（兼容旧版 run_okx_demo.py）
        self.on_reset_callback: Optional[callable] = None

        self._setup_routes()
        self._setup_socketio()

    # ------------------------------------------------------------------
    # 路由
    # ------------------------------------------------------------------

    def _setup_routes(self):
        from flask import redirect, url_for
        self.version = "v5.1-MultiStrategy-0301-1"

        @self.app.route('/')
        def index():
            return redirect(url_for('index_5_1'))

        @self.app.route('/v4')
        def index_4():
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
            res = make_response(render_template(
                'dashboard.html',
                version=timestamp,
                app_version=self.version
            ))
            res.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
            res.headers['Pragma']  = 'no-cache'
            res.headers['Expires'] = '-1'
            res.headers['Vary']    = '*'
            return res

        @self.app.route('/v5')
        @self.app.route('/dashboard_5_1')
        def index_5_1():
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
            res = make_response(render_template(
                'dashboard_5_1.html',
                version=timestamp,
                app_version=self.version + "-5.1"
            ))
            res.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
            res.headers['Pragma']  = 'no-cache'
            res.headers['Expires'] = '-1'
            res.headers['Vary']    = '*'
            return res

        @self.app.route('/dashboard_4')
        def index_4_alias():
            return redirect(url_for('index_4'))

        @self.app.route('/api/status')
        def api_status():
            strategy_id = request.args.get('strategy_id')
            if strategy_id:
                data = self._data.get(strategy_id, DashboardServer._EMPTY_STRATEGY_DATA())
                return jsonify(self._clean_data(data))
            # 无参数：返回所有策略
            return jsonify({sid: self._clean_data(d) for sid, d in self._data.items()})

        @self.app.route('/api/strategies')
        def api_strategies():
            """返回当前已注册的策略列表"""
            return jsonify({
                'strategies': [
                    {
                        'id': sid, 
                        'name': self._data[sid].get('strategy', {}).get('name', sid),
                        'route': self._data[sid].get('route', '/')
                    }
                    for sid in self._strategy_ids
                ]
            })

        @self.app.route('/favicon.ico')
        def favicon():
            return '', 204

    # ------------------------------------------------------------------
    # SocketIO 事件
    # ------------------------------------------------------------------

    def _setup_socketio(self):

        @self.socketio.on('connect')
        def handle_connect():
            print('[SocketIO] 客户端已连接')
            # 发送策略列表，让前端填充下拉框
            emit('strategies_list', {
                'strategies': [
                    {
                        'id': sid, 
                        'name': self._data[sid].get('strategy', {}).get('name', sid),
                        'route': self._data[sid].get('route', '/')
                    }
                    for sid in self._strategy_ids
                ]
            })
            emit('server_ready', {'status': 'active', 'time': datetime.now().isoformat()})

        @self.socketio.on('join')
        def handle_join(data):
            strategy_id = data.get('strategy_id') if isinstance(data, dict) else str(data)
            if not strategy_id:
                return
            join_room(strategy_id)
            print(f'[SocketIO] 客户端加入策略房间: {strategy_id}')
            # 推送当前已有数据
            existing = self._data.get(strategy_id, DashboardServer._EMPTY_STRATEGY_DATA())
            clean = self._clean_data(existing)
            emit('update', clean)
            
            # 补发历史更新信号，确保刷新页面的图表能立刻渲染历史记录
            if existing.get('history_candles'):
                emit('history_update', clean)

        @self.socketio.on('leave')
        def handle_leave(data):
            strategy_id = data.get('strategy_id') if isinstance(data, dict) else str(data)
            if strategy_id:
                leave_room(strategy_id)
                print(f'[SocketIO] 客户端离开策略房间: {strategy_id}')

        @self.socketio.on('ping')
        def handle_ping():
            emit('pong', {'time': datetime.now().isoformat()})

        @self.socketio.on('reset_strategy')
        def handle_reset_strategy(data=None):
            strategy_id = (data or {}).get('strategy_id') if isinstance(data, dict) else None
            print(f'[SocketIO] >>> 收到前端重置策略请求 strategy_id={strategy_id} <<<')
            if self.on_control_callback:
                sid = strategy_id or (self._strategy_ids[0] if self._strategy_ids else None)
                if sid:
                    self.on_control_callback('reset', sid)
                    self.reset_ui(sid) # 显式通知前端清空 UI
                    self.socketio.emit('strategy_status_changed',
                                       {'strategy_id': sid, 'status': 'stopped'},
                                       to=sid, namespace='/')
            elif hasattr(self, 'on_reset_callback') and self.on_reset_callback:
                self.on_reset_callback()
            else:
                print('[SocketIO] 警告: 未注册控制回调函数')

        @self.socketio.on('start_strategy')
        def handle_start_strategy(data=None):
            strategy_id = (data or {}).get('strategy_id') if isinstance(data, dict) else None
            print(f'[SocketIO] >>> 收到前端启动策略请求 strategy_id={strategy_id} <<<')
            if self.on_control_callback and strategy_id:
                self.on_control_callback('start', strategy_id)
                # 通知该策略的所有客户端状态变化
                self.socketio.emit('strategy_status_changed',
                                   {'strategy_id': strategy_id, 'status': 'running'},
                                   to=strategy_id, namespace='/')
            else:
                print('[SocketIO] start_strategy: 缺少 strategy_id 或未注册控制回调')

        @self.socketio.on('pause_strategy')
        def handle_pause_strategy(data=None):
            strategy_id = (data or {}).get('strategy_id') if isinstance(data, dict) else None
            print(f'[SocketIO] >>> 收到前端暂停策略请求 strategy_id={strategy_id} <<<')
            if self.on_control_callback and strategy_id:
                self.on_control_callback('pause', strategy_id)
                self.socketio.emit('strategy_status_changed',
                                   {'strategy_id': strategy_id, 'status': 'paused'},
                                   to=strategy_id, namespace='/')
            else:
                print('[SocketIO] pause_strategy: 缺少 strategy_id 或未注册控制回调')

    # ------------------------------------------------------------------
    # 数据工具
    # ------------------------------------------------------------------

    def _clean_data(self, data: Any) -> Any:
        import math
        from enum import Enum

        if isinstance(data, dict):
            return {k: self._clean_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._clean_data(v) for v in data]
        elif isinstance(data, float):
            if math.isnan(data) or math.isinf(data):
                return None
            return data
        elif isinstance(data, datetime):
            return data.isoformat()
        elif isinstance(data, Enum):
            return data.value
        return data

    # ------------------------------------------------------------------
    # 核心 API
    # ------------------------------------------------------------------

    def register_strategy(self, strategy_id: str, display_name: str = None, route: str = '/'):
        """注册一条策略（提前占位，可选）"""
        if strategy_id not in self._data:
            self._data[strategy_id] = DashboardServer._EMPTY_STRATEGY_DATA()
            self._data[strategy_id]['route'] = route
            if display_name:
                self._data[strategy_id]['strategy'] = {'name': display_name}
            self._strategy_ids.append(strategy_id)
            print(f'[DashboardServer] 注册策略: {strategy_id} (路由: {route})')

    def update(self, data: Dict[str, Any], strategy_id: str = 'default'):
        """更新指定策略的数据并推送到对应房间"""
        try:
            if strategy_id not in self._data:
                self.register_strategy(strategy_id)

            if 'history_candles' in data:
                print(f'[DashboardServer] [{strategy_id}] 收到 {len(data["history_candles"])} 根K线')

            # 合并数据
            for key, value in data.items():
                if isinstance(value, dict) and key in self._data[strategy_id]:
                    self._data[strategy_id][key].update(value)
                else:
                    self._data[strategy_id][key] = value

            # 限制历史数据长度
            for key in ['history_candles', 'history_rsi', 'history_equity', 'trades']:
                if key in self._data[strategy_id] and isinstance(self._data[strategy_id][key], list):
                    self._data[strategy_id][key] = self._data[strategy_id][key][-500:]

            # 推送到对应房间
            clean = self._clean_data(data)
            self.socketio.emit('update', clean, to=strategy_id, namespace='/')

            # 如果包含历史数据，额外发送 history_update 信号供前端调用 setData
            if 'history_candles' in data:
                self.socketio.emit('history_update', clean, to=strategy_id, namespace='/')

        except Exception as e:
            print(f'[Dashboard] [{strategy_id}] 更新失败: {e}')
            import traceback
            traceback.print_exc()

    def reset_ui(self, strategy_id: str = None):
        """通知前端清空 UI 数据（保留行情历史，仅清除账户数据）"""
        try:
            # 定义行情相关的键，用于保留
            market_keys = ['history_candles', 'history_rsi', 'history_equity_unused', 'history_macd', 'prices', 'candle', 'strategy']
            
            def perform_soft_reset(sid):
                old_data = self._data.get(sid, {})
                # 创建新数据，保留行情相关项
                new_data = DashboardServer._EMPTY_STRATEGY_DATA()
                for key in market_keys:
                    if key in old_data:
                        new_data[key] = old_data[key]
                
                # 确保权益历史被清空
                new_data['history_equity'] = []
                self._data[sid] = new_data
                self.socketio.emit('reset_ui', {'soft': True}, to=sid, namespace='/')
                print(f'[DashboardServer] 向 [{sid}] 发送 Soft Reset 信号 (保留行情历史)')

            if strategy_id:
                perform_soft_reset(strategy_id)
            else:
                for sid in self._strategy_ids:
                    perform_soft_reset(sid)
        except Exception as e:
            print(f'[Dashboard] 发送 reset_ui 失败: {e}')

    # ------------------------------------------------------------------
    # 服务器启动
    # ------------------------------------------------------------------

    def start(self, debug=False):
        print(f"\n{'='*60}")
        print(f"Dashboard 启动（多策略版 {self.version}）")
        print(f"访问地址: http://localhost:{self.port}")
        print(f"{'='*60}\n")

        self.socketio.run(
            self.app,
            host=self.host,
            port=self.port,
            debug=debug,
            allow_unsafe_werkzeug=True
        )

    def start_background(self):
        thread = threading.Thread(target=self.start, kwargs={'debug': False})
        thread.daemon = True
        thread.start()
        return thread


def create_dashboard(host='0.0.0.0', port=5000) -> DashboardServer:
    return DashboardServer(host=host, port=port)


_default_dashboard: Optional[DashboardServer] = None

def get_dashboard() -> Optional[DashboardServer]:
    return _default_dashboard

def set_dashboard(dashboard: DashboardServer):
    global _default_dashboard
    _default_dashboard = dashboard
