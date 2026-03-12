import os
import sys
import webbrowser
from datetime import datetime

# 确保项目根目录在 path 中
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from dashboard import create_dashboard

def main():
    port = 5005
    url = f"http://localhost:{port}/static/backtest_viewer.html"
    
    print("\n" + "="*60)
    print("CTS Arena - 回测竞技场可视化服务")
    print("="*60)
    print(f"模式: 静态回测数据展示 (Static Viewer)")
    print(f"端口: {port}")
    print(f"URL : {url}")
    print("="*60)
    
    # 启动 Dashboard 服务器
    dashboard = create_dashboard(port=port)
    
    # 注册一个占位策略用于加载静态文件
    dashboard.register_strategy('arena_viewer', 'Arena Backtest Viewer', route='/arena_static')
    
    print(f"\n[系统] 正在启动可视化服务...")
    print(f"[提示] 如果浏览器没有自动打开，请手动访问: {url}")
    
    # 尝试自动打开浏览器
    try:
        webbrowser.open(url)
    except Exception:
        pass

    # 启动 Flask 服务 (阻塞模式)
    try:
        dashboard.start(debug=False)
    except KeyboardInterrupt:
        print("\n[系统] 服务已手动停止")
    except Exception as e:
        print(f"\n[错误] 服务运行异常: {e}")

if __name__ == "__main__":
    main()
