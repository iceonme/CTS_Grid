# V93 Innovation Dashboard Server Hooks
from flask import jsonify

def register_dashboard(app, socketio):
    """
    此函数会被 DashboardServer 自动加载，并将当前的 Flask app 和 SocketIO 实例注入。
    """
    
    @app.route('/api/v93/info')
    def get_v93_info():
        """提供策略的元数据说明"""
        return jsonify({
            "name": "V9.3 Innovation",
            "description": "基于 3+2 动态网格与 RSI 动量过滤的 ETH 永续合约策略。",
            "logic": [
                "3层实体网格：Low, Mid, High 构筑核心交易区间。",
                "2层虚拟网格：VH, VL 作为突破重置与极值报警边界。",
                "动态阈值：随 ATR 波动率自动调整 RSI 入场与出场位。",
                "趋势过滤：顺势加码，逆势平仓归并。"
            ]
        })

    print("[V93:Hook] 专属 API 钩子已挂载")
