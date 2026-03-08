
import threading
import json
from datetime import datetime
from typing import Dict, Any, Optional, List

from flask import Flask, render_template, jsonify, make_response, request
from flask_socketio import SocketIO, emit, join_room, leave_room


class DashboardServer80:
    """
    Dashboard 服务器 (V7.0-Razor 专用)

    功能：
    1. 专为 7.0 策略设计的独立服务
    2. 默认端口 5070
    """

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

    def __init__(self, port: int = 5080):
        self.host = '0.0.0.0' # Keep host for socketio.run
        self.port = port
        
        # 针对 V8.0-OPT-FINAL 定制的独立文件存储
        self.state_file: str = "trading_state_grid_v80.json"
        self.trades_file: str = "trading_trades_grid_v80.json"
        self.version: str = "v8.0-Grid-Dashboard"

        import os
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.app = Flask(__name__, 
                         static_folder=os.path.join(base_dir, 'static'),
                         template_folder=os.path.join(base_dir, 'templates'),
                         static_url_path='/static')
        self.app.config['SECRET_KEY'] = 'cts1-v70-secret-key'
        self.app.config['TEMPLATES_AUTO_RELOAD'] = True

        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode='threading')

        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        self._data: Dict[str, Dict[str, Any]] = {}
        self._strategy_ids: List[str] = []
        self.on_control_callback: Optional[callable] = None

        self._setup_routes()
        self._setup_socketio()

    def _setup_routes(self):
        from flask import redirect, url_for

        @self.app.route('/')
        def index():
            # 6.0 默认使用专用的模板（如果以后有特殊需求可以定制）
            # 目前先复用 5.2 的模板（因为 Runner 2.0 保证了数据结构兼容）
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
            res = make_response(render_template(
                'dashboard_v80.html',
                version=timestamp,
                app_version=self.version
            ))
            res.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
            res.headers['Pragma']  = 'no-cache'
            res.headers['Expires'] = '-1'
            res.headers['Vary']    = '*'
            return res

        @self.app.route('/api/status')
        def api_status():
            strategy_id = request.args.get('strategy_id')
            if strategy_id:
                data = self._data.get(strategy_id, DashboardServer80._EMPTY_STRATEGY_DATA())
                return jsonify(self._clean_data(data))
            return jsonify({sid: self._clean_data(d) for sid, d in self._data.items()})

        @self.app.route('/health')
        def health():
            return "OK", 200

    def _setup_socketio(self):
        @self.socketio.on('connect')
        def handle_connect():
            print(f"[Socket] Client connected: {request.sid}")
            emit('strategies_list', {
                'strategies': [
                    {'id': sid, 'name': self._data[sid].get('strategy', {}).get('name', sid)}
                    for sid in self._strategy_ids
                ]
            })
            emit('server_ready', {'status': 'active', 'time': datetime.now().isoformat()})

        @self.socketio.on_error_default
        def default_error_handler(e):
            print(f"[Socket Error] {e}")

        @self.socketio.on('join')
        def handle_join(data):
            strategy_id = data.get('strategy_id') if isinstance(data, dict) else str(data)
            print(f"[Socket] join requested: {strategy_id} by {request.sid}")
            if not strategy_id: return
            join_room(strategy_id)
            existing = self._data.get(strategy_id, DashboardServer80._EMPTY_STRATEGY_DATA())
            clean = self._clean_data(existing)
            emit('update', clean)
            if existing.get('history_candles'):
                emit('history_update', clean)

        @self.socketio.on('save_strategy_params')
        def handle_save_params(data):
            strategy_id = data.get('strategy_id')
            params = data.get('params')
            if strategy_id and params and self.on_control_callback:
                self.on_control_callback('save_params', strategy_id, data=params)

        @self.socketio.on('reset_strategy')
        def handle_reset_strategy(data=None):
            strategy_id = (data or {}).get('strategy_id') if isinstance(data, dict) else None
            if self.on_control_callback and strategy_id:
                self.on_control_callback('reset', strategy_id)

        @self.socketio.on('start_strategy')
        def handle_start_strategy(data=None):
            strategy_id = (data or {}).get('strategy_id') if isinstance(data, dict) else None
            print(f"[Socket] start_strategy received: {strategy_id}")
            if self.on_control_callback and strategy_id:
                self.on_control_callback('start', strategy_id)

        @self.socketio.on('pause_strategy')
        def handle_pause_strategy(data=None):
            strategy_id = (data or {}).get('strategy_id') if isinstance(data, dict) else None
            print(f"[Socket] pause_strategy received: {strategy_id}")
            if self.on_control_callback and strategy_id:
                self.on_control_callback('pause', strategy_id)

    def _clean_data(self, data: Any) -> Any:
        import math
        from enum import Enum
        if isinstance(data, dict): return {k: self._clean_data(v) for k, v in data.items()}
        elif isinstance(data, list): return [self._clean_data(v) for v in data]
        elif isinstance(data, float):
            if math.isnan(data) or math.isinf(data): return None
            return data
        elif isinstance(data, datetime): return data.isoformat()
        elif isinstance(data, Enum): return data.value
        return data

    def register_strategy(self, strategy_id: str, display_name: "str | None" = None):
        if strategy_id not in self._data:
            self._data[strategy_id] = DashboardServer80._EMPTY_STRATEGY_DATA()
            if display_name: self._data[strategy_id]['strategy'] = {'name': display_name}
            self._strategy_ids.append(strategy_id)

    def update(self, data: Dict[str, Any], strategy_id: str = 'default'):
        try:
            if strategy_id not in self._data: self.register_strategy(strategy_id)
            for key, value in data.items():
                if isinstance(value, dict) and key in self._data[strategy_id]:
                    self._data[strategy_id][key].update(value)
                else: self._data[strategy_id][key] = value
            for key in ['history_candles', 'history_rsi', 'history_equity', 'trades']:
                if key in self._data[strategy_id] and isinstance(self._data[strategy_id][key], list):
                    self._data[strategy_id][key] = self._data[strategy_id][key][-500:]
            clean = self._clean_data(data)
            self.socketio.emit('update', clean, to=strategy_id, namespace='/')
            if 'history_candles' in data:
                self.socketio.emit('history_update', clean, to=strategy_id, namespace='/')
        except Exception as e:
            print(f'[Dashboard70] [{strategy_id}] 更新失败: {e}')

    def start(self, debug=False):
        print(f"\n{'='*60}")
        print(f"Dashboard 启动 (V7.0 版 {self.version})")
        print(f"访问地址: http://localhost:{self.port}")
        print(f"{'='*60}\n")
        self.socketio.run(self.app, host=self.host, port=self.port, debug=debug, allow_unsafe_werkzeug=True)

    def start_background(self):
        thread = threading.Thread(target=self.start, kwargs={'debug': False})
        thread.daemon = True
        thread.start()
        return thread


def create_dashboard_80(port=5080) -> DashboardServer80:
    return DashboardServer80(port=port)
