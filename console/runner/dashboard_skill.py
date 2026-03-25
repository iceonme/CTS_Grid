"""
DashboardSkill - 系统可视化基础设施 (显卡驱动模式)
职责：提供通用的 WebSocket 管道与静态资源服务，不参与业务序列化。
"""
import asyncio
from typing import Dict, Any, List, Optional
import os
from datetime import datetime

from console.runner.base_skill import BaseSkill
from console.dashboard.server import DashboardServer, create_dashboard
from console.protocol import (
    MarketUpdateEvent, AccountUpdateEvent, 
    SignalRequestEvent, ExecutionReportEvent
)

class DashboardSkill(BaseSkill):
    """
    DashboardSkill 作为一个通用的“数据中转站”。
    它不关心业务协议，只负责根据 strategy_id 将总线事件透传至 Socket.IO 房间。
    """
    
    def __init__(self, port: int = 5066):
        super().__init__("dashboard_skill")
        self.server = create_dashboard(port=port)
        self.port = port

    def on_init(self):
        """订阅标准 UI 相关事件"""
        # 1. 订阅特定路由事件
        self.subscribe("ui_update", self._on_ui_relay)
        self.subscribe("ui_history_update", self._on_history_relay)
        self.subscribe("strategy_update", self._on_ui_relay)
        
        # 2. 订阅全局广播事件 (如果不带 strategy_id 则广播)
        self.subscribe("market_update", self._on_market_relay)
        self.subscribe("account_update", self._on_ui_relay)
        self.subscribe("execution_report", self._on_ui_relay)
        
        # 处理来自 UI 的反向控制指令 (HDMI 反向控制)
        self.server.on_control_callback = self._on_ui_control
        self.server.on_join_callback = self._on_ui_join
        
        print(f"[DashboardSkill] 数据中转服务已接入总线 (HDMI 总线就绪)")

    def _on_ui_join(self, strategy_id: str):
        """当新客户端连接时，请求全量状态快照"""
        # print(f"[DashboardSkill] 探测到新显示终端接入: {strategy_id}")
        self.publish("ui_snapshot_request", {
            "strategy_id": strategy_id,
            "timestamp": datetime.now().isoformat()
        })

    def _on_ui_control(self, cmd: str, strategy_id: str, data: Any = None):
        """HDMI 反向通道：将 UI 指令原样转发回总线"""
        # print(f"[DashboardSkill] 收到 UI 指令: {cmd} ({strategy_id})")
        self.publish("control_request", {
            "cmd": cmd,
            "strategy_id": strategy_id,
            "data": data,
            "timestamp": datetime.now().isoformat()
        })

    def register_strategy(self, strategy_id: str, skill_path: str, display_name: Optional[str] = None):
        """
        向显卡注册一个显示后端
        """
        self.server.register_strategy(strategy_id, display_name=display_name)
        self.server.register_skill_dashboard(strategy_id, skill_path)
        print(f"[DashboardSkill] 已配置显示输出端口: {strategy_id}")

    async def _on_ui_relay(self, event_data: Any):
        """通用透明中转协议：只要有 strategy_id，就转发到对应 Socket.IO Room"""
        # 尝试从 dataclass 或 dict 中提取 strategy_id
        sid = getattr(event_data, 'strategy_id', None)
        if isinstance(event_data, dict):
            sid = event_data.get('strategy_id', sid)
            data = event_data.get('data', event_data)
        else:
            # 如果是 Dataclass (如 AccountUpdateEvent)，需要序列化
            # 注意：复杂的序列化应该由生产者完成，这里仅做二次备份
            data = self._to_dict(event_data)
            
        # 路由分发
        if sid:
            self.server.update(data, strategy_id=sid)
        else:
            # 无特定 ID 则广播给所有客户端
            for room in self.server._strategy_ids:
                self.server.update(data, strategy_id=room)

    async def _on_history_relay(self, event_data: Dict[str, Any]):
        """专用历史中转：转发至 Socket.IO 的 history_update 事件"""
        sid = event_data.get("strategy_id")
        data = event_data.get("data", {})
        if sid:
            # print(f"[DashboardSkill] 正在向 {sid} 灌注历史 K 线...")
            self.server.update(data, strategy_id=sid, event='history_update')

    async def _on_market_relay(self, event: MarketUpdateEvent):
        """行情中转：虽然是全局数据，但为了性能，我们会将其包装成前端预期的通用格式"""
        # 注意：这里的转换极其轻量，仅保证基础绘图能力
        # 深度业务绘图应由策略在 strategy_update 中自行推送
        data = {
            "market_data": {
                "timestamp": int(event.data.timestamp * 1000) if isinstance(event.data.timestamp, (int, float)) else int(event.data.timestamp.timestamp() * 1000),
                "open": event.data.open,
                "high": event.data.high,
                "low": event.data.low,
                "close": event.data.close,
                "volume": event.data.volume,
                "symbol": event.data.symbol
            }
        }
        # 全局广播行情
        for room in self.server._strategy_ids:
            self.server.update(data, strategy_id=room)

    def _to_dict(self, obj):
        """通用的极简序列化 (显卡驱动内部转换)"""
        if hasattr(obj, '__dict__'):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
        return obj

    async def start(self):
        self._running = True
        self.server.start_background()
        while self._running:
            await asyncio.sleep(1)

    async def stop(self):
        self._running = False
        print("[DashboardSkill] 显示链路已切断。")
