"""
Dashboard Web 服务器
Flask + SocketIO 实现实时监控
"""

import threading
import json
from datetime import datetime
from typing import Dict, Any, Optional

from flask import Flask, render_template, jsonify, make_response
from flask_socketio import SocketIO, emit


class DashboardServer:
    """
    Dashboard 服务器
    
    功能：
    1. 接收引擎状态更新
    2. 通过 WebSocket 推送到前端
    3. 提供 REST API
    """
    
    def __init__(self, host='0.0.0.0', port=5000):
        self.host = host
        self.port = port
        
        # Flask 应用
        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = 'cts1-secret-key'
        self.app.config['TEMPLATES_AUTO_RELOAD'] = True  # 开启模板自动重载
        
        # SocketIO
        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode='threading')
        
        # 数据缓存
        self._data: Dict[str, Any] = {
            'prices': {},
            'total_value': 0,
            'cash': 0,
            'position_value': 0,
            'positions': {},
            'pnl_pct': 0,
            'rsi': 50,
            'trades': [],
            'history_candles': [],
            'history_rsi': [],
            'history_equity': [],
            'strategy': {}
        }
        
        self._setup_routes()
        self._setup_socketio()
    
    def _setup_routes(self):
        """设置路由"""
        
        # 版本号 - 每次修改前端代码后更新
        self.version = "v3.7-20260224"
        
        @self.app.route('/')
        def index():
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
            res = make_response(render_template('dashboard.html', 
                                                  version=timestamp,
                                                  app_version=self.version))
            res.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
            res.headers['Pragma'] = 'no-cache'
            res.headers['Expires'] = '-1'
            res.headers['Vary'] = '*'
            return res
        
        @self.app.route('/api/status')
        def api_status():
            return jsonify(self._clean_data(self._data))
        
        @self.app.route('/favicon.ico')
        def favicon():
            return '', 204
    
    def _setup_socketio(self):
        """设置 WebSocket 事件"""
        
        @self.socketio.on('connect')
        def handle_connect():
            print('[SocketIO] 客户端已连接')
            print(f"[SocketIO] 当前历史数据: {len(self._data.get('history_candles', []))} 根 K 线")
            emit('server_ready', {
                'status': 'active',
                'time': datetime.now().isoformat()
            })
            # 发送全量数据
            clean_data = self._clean_data(self._data)
            print(f"[SocketIO] 发送 update: {len(clean_data.get('history_candles', []))} 根 K 线")
            emit('update', clean_data)
        
        @self.socketio.on('ping')
        def handle_ping():
            emit('pong', {'time': datetime.now().isoformat()})
    
    def _clean_data(self, data: Any) -> Any:
        """清理数据，确保可序列化"""
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
    
    def update(self, data: Dict[str, Any]):
        """更新数据并推送到前端"""
        try:
            # DEBUG
            if 'history_candles' in data:
                print(f"[DashboardServer] update 收到 {len(data['history_candles'])} 根 K 线")
            
            # 合并数据
            for key, value in data.items():
                if isinstance(value, dict) and key in self._data:
                    self._data[key].update(value)
                else:
                    self._data[key] = value
            
            # 限制历史数据长度
            for key in ['history_candles', 'history_rsi', 'history_equity', 'trades']:
                if key in self._data and isinstance(self._data[key], list):
                    self._data[key] = self._data[key][-500:]
            
            # 推送
            clean = self._clean_data(data)
            self.socketio.emit('update', clean, namespace='/')
            
        except Exception as e:
            print(f"[Dashboard] 更新失败: {e}")
            import traceback
            traceback.print_exc()
    
    def start(self, debug=False):
        """启动服务器"""
        print(f"\n{'='*60}")
        print(f"Dashboard 启动")
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
        """在后台线程启动"""
        thread = threading.Thread(target=self.start, kwargs={'debug': False})
        thread.daemon = True
        thread.start()
        return thread


def create_dashboard(host='0.0.0.0', port=5000) -> DashboardServer:
    """创建 Dashboard 实例"""
    return DashboardServer(host=host, port=port)


# 全局实例（方便导入）
_default_dashboard: Optional[DashboardServer] = None

def get_dashboard() -> Optional[DashboardServer]:
    """获取默认 Dashboard 实例"""
    return _default_dashboard

def set_dashboard(dashboard: DashboardServer):
    """设置默认 Dashboard 实例"""
    global _default_dashboard
    _default_dashboard = dashboard



