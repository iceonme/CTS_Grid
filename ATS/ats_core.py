"""
Agentic Trading Skill (ATS-20) Core Protocol Draft.
This file defines the absolute minimal interfaces and data schemas required for an ATS strategy.
It has ZERO dependencies on any external proprietary trading framework (like CTS1's `core.py`).
"""

from typing import List, Dict, Any, TypedDict, Optional, Literal

# --- Data Schemas (数据契约) ---

class MarketDataDict(TypedDict):
    """标准的输入 K 线/Ticker 结构"""
    symbol: str
    timestamp: float # Unix 秒级或毫秒级时间戳均可，需统一
    close: float
    high: Optional[float]
    low: Optional[float]
    open: Optional[float]
    volume: Optional[float]

class SignalDict(TypedDict):
    """标准的输出交易信号结构"""
    skill_name: str
    symbol: str
    side: Literal["BUY", "SELL"]
    type: Literal["MARKET", "LIMIT"]
    size: float
    price: Optional[float]
    rationale: str # 给 Agent 和审查后台看的文字理由


# --- Protocol Interface (接口契约) ---

class ATSStrategy:
    """所有 ATS Skill 必须实现的基类"""
    
    def __init__(self, name: str, **params):
        """用配置表里的参数实例化策略"""
        self.name = name
        self.params = params
        self.is_initialized = False

    def initialize(self) -> bool:
        """加载初始状态、预热指标缓存等"""
        self.is_initialized = True
        return True

    def on_data(self, data: MarketDataDict, context: Dict[str, Any]) -> List[SignalDict]:
        """
        核心决策逻辑：输入标准行情字典，输出标准指令字典列表。
        context 用于传入当前资金、持仓等状态。
        """
        raise NotImplementedError("Strategy must implement `on_data`")

    def on_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        响应外部事件，如 'ORDER_FILLED' 或 'ORDER_REJECTED'
        """
        pass

    def get_status(self) -> Dict[str, Any]:
        """暴露策略当前运行时的内部状态变量"""
        return {"name": self.name}
