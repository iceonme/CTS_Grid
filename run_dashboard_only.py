import os
import sys

# 确保模块路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from dashboard import create_dashboard

if __name__ == "__main__":
    port = 5005
    print(f"[SERVER] Starting Dashboard Server on port {port}...")
    print(f"[SERVER] Static viewer available at: http://localhost:{port}/static/backtest_viewer.html")
    
    dashboard = create_dashboard(port=port)
    # 随便注册一个，主要为了启动 Flask 容器
    dashboard.register_strategy('v85_static', 'Static Backtest Viewer', route='/v5_static')
    
    # 启动服务（阻塞模式）
    dashboard.start(debug=False)
