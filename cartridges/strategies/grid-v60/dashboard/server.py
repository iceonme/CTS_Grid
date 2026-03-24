# Grid V6.0 Dashboard Server Hooks

def register_dashboard(app, socketio):
    """
    此函数会被 DashboardServer 自动加载。
    你可以通过 app.route 增加 API，或者通过 socketio.on 增加事件处理器。
    """
    @app.route('/api/grid_v60/custom_info')
    def get_custom_info():
        return {"message": "这是来自 Grid V6.0 的自定义钩子数据"}

    print("[GridV60:Hook] 专属 API 钩子已挂载")
