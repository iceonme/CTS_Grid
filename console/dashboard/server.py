import threading
import json
from datetime import datetime
from typing import Dict, Any, Optional, List

from flask import Flask, render_template, jsonify, make_response, request, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room
import os
import importlib.util


class DashboardServer:
    """
    Dashboard 服务器（多策略版）

    功能：
    1. 接收多条策略的状态更新（通过 strategy_id 区分）
    2. WebSocket Room 化：前端 join 特定策略房间，只收该策略的推送
    3. 提供 REST API：/api/status?strategy_id=xxx
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
        'history_macd':   [],
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
        # Skill 看板目录映射：{strategy_id: skill_dashboard_dir}
        self._skill_dashboards: Dict[str, str] = {}
        # 控制回调（由 MultiStrategyRunner 注入）
        self.on_control_callback: Optional[callable] = None
        # 重置回调
        self.on_reset_callback: Optional[callable] = None

        # 回测并发锁
        self._backtest_lock = threading.Lock()

        self._setup_routes()
        self._setup_socketio()

    def _setup_routes(self):
        from flask import redirect, url_for
        self.version = "v6.0-MultiStrategy"

        @self.app.route('/')
        def index():
            # 优先重定向到第一个注册的 Skill 看板
            if self._strategy_ids:
                sid = self._strategy_ids[0]
                if sid in self._skill_dashboards:
                    return redirect(f'/strategy/{sid}/')
            
            # 如果没有任何策略加载，返回一个基础的欢迎/状态页面
            return """
            <html>
                <body style="background:#0f172a; color:#94a3b8; font-family:sans-serif; display:flex; justify-content:center; align-items:center; height:100vh; margin:0;">
                    <div style="text-align:center; padding:40px; background:#1e293b; border-radius:12px; border:1px solid #334155;">
                        <h1 style="color:#00d4ff;">ATS 控制台</h1>
                        <p>目前没有已加载或注册的策略看板。</p>
                        <p style="font-size:14px;">请确保已通过 <code>ats.py run &lt;skill&gt;</code> 启动系统。</p>
                    </div>
                </body>
            </html>
            """

        @self.app.route('/strategy/<sid>/')
        def skill_index(sid):
            if sid not in self._skill_dashboards:
                return f"Strategy {sid} dashboard not found", 404
            
            dashboard_dir = self._skill_dashboards[sid]
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
            
            # 渲染 Skill 目录下的 index.html
            # 这里的 template_folder 必须动态处理或使用 send_from_directory
            # 为了简单起见，我们直接读取文件并渲染内容
            index_path = os.path.join(dashboard_dir, 'index.html')
            if not os.path.exists(index_path):
                return f"index.html not found in {dashboard_dir}", 404
            
            with open(index_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 简单的模板替换（注入版本号等）
            content = content.replace('{{ app_version }}', self.version)
            content = content.replace('{{ version }}', timestamp)
            content = content.replace('{{ strategy_id }}', sid)
            
            res = make_response(content)
            res.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
            return res

        @self.app.route('/strategy/<sid>/<path:filename>')
        def skill_static(sid, filename):
            if sid not in self._skill_dashboards:
                return "Not found", 404
            return send_from_directory(self._skill_dashboards[sid], filename)

        @self.app.route('/v6')
        @self.app.route('/dashboard_v60')
        @self.app.route('/dashboard_5_2')
        def legacy_redirect():
            # 所有旧路径统一重定向到首页，首页会自动处理 Skill 跳转
            return redirect(url_for('index'))

        @self.app.route('/api/status')
        def get_status():
            strategy_id = request.args.get('strategy_id', 'default')
            if strategy_id != 'default' and strategy_id in self._data:
                data = self._data.get(strategy_id, DashboardServer._EMPTY_STRATEGY_DATA())
                return jsonify(self._clean_data(data))
            return jsonify({sid: self._clean_data(d) for sid, d in self._data.items()})

        @self.app.route('/api/run_backtest', methods=['POST'])
        def run_backtest():
            import subprocess
            import sys
            import os
            
            if not self._backtest_lock.acquire(blocking=False):
                return jsonify({"status": "error", "message": "回测引擎正忙，请稍后再试"}), 429
            
            try:
                data = request.json
                start_date = data.get('start', datetime.now().strftime('%Y-%m-%d'))
                end_date = data.get('end', datetime.now().strftime('%Y-%m-%d'))
                strategy_id = data.get('strategy', 'grid_v85')
                
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                script_path = os.path.join(base_dir, 'backtest', 'run_backtest_arena_viewer.py')
                
                cmd = [sys.executable, script_path, '--strategy', strategy_id, '--start', start_date, '--end', end_date]
                result = subprocess.run(cmd, capture_output=True, text=True, cwd=base_dir, timeout=60)
                
                if result.returncode == 0:
                    return jsonify({"status": "success", "message": "回测完成，数据已刷新"})
                else:
                    return jsonify({"status": "error", "message": f"计算失败: {result.stderr}"}), 500
                    
            except subprocess.TimeoutExpired:
                return jsonify({"status": "error", "message": "回测执行超时 (60s)，请缩小时间范围或选择更具体日期"}), 504
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 500
            finally:
                self._backtest_lock.release()

        @self.app.route('/api/strategies')
        def api_strategies():
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

    def _setup_socketio(self):
        @self.socketio.on('connect')
        def handle_connect():
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
            existing = self._data.get(strategy_id, DashboardServer._EMPTY_STRATEGY_DATA())
            clean = self._clean_data(existing)
            emit('update', clean)
            if existing.get('history_candles'):
                emit('history_update', clean)

        @self.socketio.on('leave')
        def handle_leave(data):
            strategy_id = data.get('strategy_id') if isinstance(data, dict) else str(data)
            if strategy_id:
                leave_room(strategy_id)

        @self.socketio.on('save_strategy_params')
        def handle_save_params(data):
            strategy_id = data.get('strategy_id')
            params = data.get('params')
            if strategy_id and params and self.on_control_callback:
                self.on_control_callback('save_params', strategy_id, data=params)

        @self.socketio.on('reset_strategy')
        def handle_reset_strategy(data=None):
            strategy_id = (data or {}).get('strategy_id') if isinstance(data, dict) else None
            if self.on_control_callback:
                sid = strategy_id or (self._strategy_ids[0] if self._strategy_ids else None)
                if sid:
                    self.on_control_callback('reset', sid)
                    self.reset_ui(sid)
                    self.socketio.emit('strategy_status_changed',
                                       {'strategy_id': sid, 'status': 'stopped'},
                                       to=sid, namespace='/')
            elif self.on_reset_callback:
                self.on_reset_callback()

        @self.socketio.on('start_strategy')
        def handle_start_strategy(data=None):
            strategy_id = (data or {}).get('strategy_id') if isinstance(data, dict) else None
            if self.on_control_callback and strategy_id:
                self.on_control_callback('start', strategy_id)
                self.socketio.emit('strategy_status_changed',
                                   {'strategy_id': strategy_id, 'status': 'running'},
                                   to=strategy_id, namespace='/')

        @self.socketio.on('pause_strategy')
        def handle_pause_strategy(data=None):
            strategy_id = (data or {}).get('strategy_id') if isinstance(data, dict) else None
            if self.on_control_callback and strategy_id:
                self.on_control_callback('pause', strategy_id)
                self.socketio.emit('strategy_status_changed',
                                   {'strategy_id': strategy_id, 'status': 'paused'},
                                   to=strategy_id, namespace='/')

    def _clean_data(self, data: Any) -> Any:
        import math
        from enum import Enum
        if isinstance(data, dict):
            return {k: self._clean_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._clean_data(v) for v in data]
        elif isinstance(data, float):
            if math.isnan(data) or math.isinf(data): return None
            return data
        elif isinstance(data, datetime):
            return data.isoformat()
        elif isinstance(data, Enum):
            return data.value
        return data

    def register_strategy(self, strategy_id: str, display_name: str = None, route: str = '/'):
        if strategy_id not in self._data:
            self._data[strategy_id] = DashboardServer._EMPTY_STRATEGY_DATA()
            self._data[strategy_id]['route'] = route
            if sid := strategy_id: # placeholder for sid
                if sid in self._skill_dashboards:
                    self._data[strategy_id]['route'] = f'/strategy/{sid}/'
            if display_name:
                self._data[strategy_id]['strategy'] = {'name': display_name}
            self._strategy_ids.append(strategy_id)

    def register_skill_dashboard(self, strategy_id: str, skill_path: str):
        """注册一个 Skill 专属的看板目录"""
        dashboard_dir = os.path.join(skill_path, 'dashboard')
        if not os.path.isdir(dashboard_dir):
            print(f"[DashboardServer] Warning: {dashboard_dir} is not a directory")
            return

        self._skill_dashboards[strategy_id] = dashboard_dir
        print(f"[DashboardServer] Registered custom dashboard for {strategy_id}: {dashboard_dir}")

        # 尝试加载 server.py 挂载点
        hooks_file = os.path.join(dashboard_dir, 'server.py')
        if os.path.isfile(hooks_file):
            try:
                spec = importlib.util.spec_from_file_location(f"dashboard_hooks_{strategy_id}", hooks_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, 'register_dashboard'):
                    module.register_dashboard(self.app, self.socketio)
                    print(f"[DashboardServer] Loaded server hooks for {strategy_id}")
            except Exception as e:
                print(f"[DashboardServer] Error loading hooks from {hooks_file}: {e}")

    def update(self, data: Dict[str, Any], strategy_id: str = 'default'):
        try:
            if strategy_id not in self._data:
                self.register_strategy(strategy_id)
            for key, value in data.items():
                if isinstance(value, dict) and key in self._data[strategy_id]:
                    self._data[strategy_id][key].update(value)
                else:
                    self._data[strategy_id][key] = value
            for key in ['history_candles', 'history_rsi', 'history_equity', 'history_macd', 'trades']:
                if key in self._data[strategy_id] and isinstance(self._data[strategy_id][key], list):
                    # 针对轻量化看板，历史记录保持在 500-1000 左右
                    self._data[strategy_id][key] = self._data[strategy_id][key][-1000:]
            clean = self._clean_data(data)
            self.socketio.emit('update', clean, to=strategy_id, namespace='/')
            if 'history_candles' in data:
                self.socketio.emit('history_update', clean, to=strategy_id, namespace='/')
        except Exception as e:
            print(f'[DashboardServer] Update error: {e}')

    def reset_ui(self, strategy_id: str = None):
        market_keys = ['history_candles', 'history_rsi', 'history_equity_unused', 'history_macd', 'prices', 'candle', 'strategy']
        def perform_soft_reset(sid):
            old_data = self._data.get(sid, {})
            new_data = DashboardServer._EMPTY_STRATEGY_DATA()
            for key in market_keys:
                if key in old_data: new_data[key] = old_data[key]
            new_data['history_equity'] = []
            self._data[sid] = new_data
            self.socketio.emit('reset_ui', {'soft': True}, to=sid, namespace='/')
        if strategy_id: perform_soft_reset(strategy_id)
        else:
            for sid in self._strategy_ids: perform_soft_reset(sid)

    def start(self, debug=False):
        self.socketio.run(self.app, host=self.host, port=self.port, debug=debug, allow_unsafe_werkzeug=True)

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
