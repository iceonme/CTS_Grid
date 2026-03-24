
import threading
import json
from datetime import datetime
from typing import Dict, Any, Optional, List

from flask import Flask, render_template, jsonify, make_response, request
from flask_socketio import SocketIO, emit, join_room, leave_room


class DashboardServer:
    """
    Dashboard 鏈嶅姟鍣紙澶氱瓥鐣ョ増锛?

    鍔熻兘锛?
    1. 鎺ユ敹澶氭潯绛栫暐鐨勭姸鎬佹洿鏂帮紙閫氳繃 strategy_id 鍖哄垎锛?
    2. WebSocket Room 鍖栵細鍓嶇 join 鐗瑰畾绛栫暐鎴块棿锛屽彧鏀惰绛栫暐鐨勬帹閫?
    3. 鎻愪緵 REST API锛?api/status?strategy_id=xxx锛?
    """

    # 榛樿绌烘暟鎹ā鏉?
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

        # 闈欓粯 Flask/Werkzeug 鐨?HTTP 璇锋眰鏃ュ織锛屽噺灏戠粓绔櫔闊?
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        # 澶氱瓥鐣ユ暟鎹紦瀛橈細{strategy_id: {...}}
        self._data: Dict[str, Dict[str, Any]] = {}
        # 宸叉敞鍐岀殑绛栫暐 ID 鍒楄〃锛堜繚鎸侀『搴忥級
        self._strategy_ids: List[str] = []
        # 鎺у埗鍥炶皟锛堢敱 MultiStrategyRunner 娉ㄥ叆锛?
        self.on_control_callback: Optional[callable] = None
        # 閲嶇疆鍥炶皟锛堝吋瀹规棫鐗?run_okx_demo.py锛?
        self.on_reset_callback: Optional[callable] = None

        self._setup_routes()
        self._setup_socketio()

    # ------------------------------------------------------------------
    # 璺敱
    # ------------------------------------------------------------------

    def _setup_routes(self):
        from flask import redirect, url_for
        self.version = "v5.2-MultiStrategy-0302"

        @self.app.route('/')
        def index():
            return redirect(url_for('index_5_2'))

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
        @self.app.route('/dashboard_5_2')
        def index_5_2():
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
            res = make_response(render_template(
                'dashboard_5_2.html',
                version=timestamp,
                app_version=self.version
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
            # 鏃犲弬鏁帮細杩斿洖鎵€鏈夌瓥鐣?
            return jsonify({sid: self._clean_data(d) for sid, d in self._data.items()})

        @self.app.route('/api/strategies')
        def api_strategies():
            """杩斿洖褰撳墠宸叉敞鍐岀殑绛栫暐鍒楄〃"""
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
    # SocketIO 浜嬩欢
    # ------------------------------------------------------------------

    def _setup_socketio(self):

        @self.socketio.on('connect')
        def handle_connect():
            print('[SocketIO] 瀹㈡埛绔凡杩炴帴')
            # 鍙戦€佺瓥鐣ュ垪琛紝璁╁墠绔～鍏呬笅鎷夋
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
            print(f'[SocketIO] 瀹㈡埛绔姞鍏ョ瓥鐣ユ埧闂? {strategy_id}')
            # 鎺ㄩ€佸綋鍓嶅凡鏈夋暟鎹?
            existing = self._data.get(strategy_id, DashboardServer._EMPTY_STRATEGY_DATA())
            clean = self._clean_data(existing)
            emit('update', clean)
            
            # 琛ュ彂鍘嗗彶鏇存柊淇″彿锛岀‘淇濆埛鏂伴〉闈㈢殑鍥捐〃鑳界珛鍒绘覆鏌撳巻鍙茶褰?
            if existing.get('history_candles'):
                emit('history_update', clean)

        @self.socketio.on('leave')
        def handle_leave(data):
            strategy_id = data.get('strategy_id') if isinstance(data, dict) else str(data)
            if strategy_id:
                leave_room(strategy_id)
                print(f'[SocketIO] 瀹㈡埛绔寮€绛栫暐鎴块棿: {strategy_id}')

        @self.socketio.on('save_strategy_params')
        def handle_save_params(data):
            """澶勭悊鍓嶇鍙戦€佺殑鍙傛暟淇濆瓨璇锋眰"""
            strategy_id = data.get('strategy_id')
            params = data.get('params')
            if strategy_id and params and self.on_control_callback:
                print(f'[SocketIO] 鏀跺埌鍙傛暟淇濆瓨璇锋眰: {strategy_id}')
                self.on_control_callback('save_params', strategy_id, data=params)

        @self.socketio.on('ping')
        def handle_ping():
            emit('pong', {'time': datetime.now().isoformat()})

        @self.socketio.on('reset_strategy')
        def handle_reset_strategy(data=None):
            strategy_id = (data or {}).get('strategy_id') if isinstance(data, dict) else None
            print(f'[SocketIO] >>> 鏀跺埌鍓嶇閲嶇疆绛栫暐璇锋眰 strategy_id={strategy_id} <<<')
            if self.on_control_callback:
                sid = strategy_id or (self._strategy_ids[0] if self._strategy_ids else None)
                if sid:
                    self.on_control_callback('reset', sid)
                    self.reset_ui(sid) # 鏄惧紡閫氱煡鍓嶇娓呯┖ UI
                    self.socketio.emit('strategy_status_changed',
                                       {'strategy_id': sid, 'status': 'stopped'},
                                       to=sid, namespace='/')
            elif hasattr(self, 'on_reset_callback') and self.on_reset_callback:
                self.on_reset_callback()
            else:
                print('[SocketIO] 璀﹀憡: 鏈敞鍐屾帶鍒跺洖璋冨嚱鏁?)

        @self.socketio.on('start_strategy')
        def handle_start_strategy(data=None):
            strategy_id = (data or {}).get('strategy_id') if isinstance(data, dict) else None
            print(f'[SocketIO] >>> 鏀跺埌鍓嶇鍚姩绛栫暐璇锋眰 strategy_id={strategy_id} <<<')
            if self.on_control_callback and strategy_id:
                self.on_control_callback('start', strategy_id)
                # 閫氱煡璇ョ瓥鐣ョ殑鎵€鏈夊鎴风鐘舵€佸彉鍖?
                self.socketio.emit('strategy_status_changed',
                                   {'strategy_id': strategy_id, 'status': 'running'},
                                   to=strategy_id, namespace='/')
            else:
                print('[SocketIO] start_strategy: 缂哄皯 strategy_id 鎴栨湭娉ㄥ唽鎺у埗鍥炶皟')

        @self.socketio.on('pause_strategy')
        def handle_pause_strategy(data=None):
            strategy_id = (data or {}).get('strategy_id') if isinstance(data, dict) else None
            print(f'[SocketIO] >>> 鏀跺埌鍓嶇鏆傚仠绛栫暐璇锋眰 strategy_id={strategy_id} <<<')
            if self.on_control_callback and strategy_id:
                self.on_control_callback('pause', strategy_id)
                self.socketio.emit('strategy_status_changed',
                                   {'strategy_id': strategy_id, 'status': 'paused'},
                                   to=strategy_id, namespace='/')
            else:
                print('[SocketIO] pause_strategy: 缂哄皯 strategy_id 鎴栨湭娉ㄥ唽鎺у埗鍥炶皟')

    # ------------------------------------------------------------------
    # 鏁版嵁宸ュ叿
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
    # 鏍稿績 API
    # ------------------------------------------------------------------

    def register_strategy(self, strategy_id: str, display_name: str = None, route: str = '/'):
        """娉ㄥ唽涓€鏉＄瓥鐣ワ紙鎻愬墠鍗犱綅锛屽彲閫夛級"""
        if strategy_id not in self._data:
            self._data[strategy_id] = DashboardServer._EMPTY_STRATEGY_DATA()
            self._data[strategy_id]['route'] = route
            if display_name:
                self._data[strategy_id]['strategy'] = {'name': display_name}
            self._strategy_ids.append(strategy_id)
            print(f'[DashboardServer] 娉ㄥ唽绛栫暐: {strategy_id} (璺敱: {route})')

    def update(self, data: Dict[str, Any], strategy_id: str = 'default'):
        """鏇存柊鎸囧畾绛栫暐鐨勬暟鎹苟鎺ㄩ€佸埌瀵瑰簲鎴块棿"""
        try:
            if strategy_id not in self._data:
                self.register_strategy(strategy_id)

            if 'history_candles' in data:
                print(f'[DashboardServer] [{strategy_id}] 鏀跺埌 {len(data["history_candles"])} 鏍筀绾?)

            # 鍚堝苟鏁版嵁
            for key, value in data.items():
                if isinstance(value, dict) and key in self._data[strategy_id]:
                    self._data[strategy_id][key].update(value)
                else:
                    self._data[strategy_id][key] = value

            # 闄愬埗鍘嗗彶鏁版嵁闀垮害
            for key in ['history_candles', 'history_rsi', 'history_equity', 'trades']:
                if key in self._data[strategy_id] and isinstance(self._data[strategy_id][key], list):
                    self._data[strategy_id][key] = self._data[strategy_id][key][-500:]

            # 鎺ㄩ€佸埌瀵瑰簲鎴块棿
            clean = self._clean_data(data)
            self.socketio.emit('update', clean, to=strategy_id, namespace='/')

            # 濡傛灉鍖呭惈鍘嗗彶鏁版嵁锛岄澶栧彂閫?history_update 淇″彿渚涘墠绔皟鐢?setData
            if 'history_candles' in data:
                self.socketio.emit('history_update', clean, to=strategy_id, namespace='/')

        except Exception as e:
            print(f'[Dashboard] [{strategy_id}] 鏇存柊澶辫触: {e}')
            import traceback
            traceback.print_exc()

    def reset_ui(self, strategy_id: str = None):
        """閫氱煡鍓嶇娓呯┖ UI 鏁版嵁锛堜繚鐣欒鎯呭巻鍙诧紝浠呮竻闄よ处鎴锋暟鎹級"""
        try:
            # 瀹氫箟琛屾儏鐩稿叧鐨勯敭锛岀敤浜庝繚鐣?
            market_keys = ['history_candles', 'history_rsi', 'history_equity_unused', 'history_macd', 'prices', 'candle', 'strategy']
            
            def perform_soft_reset(sid):
                old_data = self._data.get(sid, {})
                # 鍒涘缓鏂版暟鎹紝淇濈暀琛屾儏鐩稿叧椤?
                new_data = DashboardServer._EMPTY_STRATEGY_DATA()
                for key in market_keys:
                    if key in old_data:
                        new_data[key] = old_data[key]
                
                # 纭繚鏉冪泭鍘嗗彶琚竻绌?
                new_data['history_equity'] = []
                self._data[sid] = new_data
                self.socketio.emit('reset_ui', {'soft': True}, to=sid, namespace='/')
                print(f'[DashboardServer] 鍚?[{sid}] 鍙戦€?Soft Reset 淇″彿 (淇濈暀琛屾儏鍘嗗彶)')

            if strategy_id:
                perform_soft_reset(strategy_id)
            else:
                for sid in self._strategy_ids:
                    perform_soft_reset(sid)
        except Exception as e:
            print(f'[Dashboard] 鍙戦€?reset_ui 澶辫触: {e}')

    # ------------------------------------------------------------------
    # 鏈嶅姟鍣ㄥ惎鍔?
    # ------------------------------------------------------------------

    def start(self, debug=False):
        print(f"\n{'='*60}")
        print(f"Dashboard 鍚姩锛堝绛栫暐鐗?{self.version}锛?)
        print(f"璁块棶鍦板潃: http://localhost:{self.port}")
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
