"""
Agentic Trading Skill (ATS-20) Core Protocol Draft.
This file defines the absolute minimal interfaces and data schemas required for an ATS strategy.
It has ZERO dependencies on any external proprietary trading framework (like CTS1's `core.py`).
"""

from typing import List, Dict, Any, TypedDict, Optional, Literal

# --- Data Schemas (鏁版嵁濂戠害) ---

class MarketDataDict(TypedDict):
    """鏍囧噯鐨勮緭鍏?K 绾?Ticker 缁撴瀯"""
    symbol: str
    timestamp: float # Unix 绉掔骇鎴栨绉掔骇鏃堕棿鎴冲潎鍙紝闇€缁熶竴
    close: float
    high: Optional[float]
    low: Optional[float]
    open: Optional[float]
    volume: Optional[float]

class SignalDict(TypedDict):
    """鏍囧噯鐨勮緭鍑轰氦鏄撲俊鍙风粨鏋?""
    skill_name: str
    symbol: str
    side: Literal["BUY", "SELL"]
    type: Literal["MARKET", "LIMIT"]
    size: float
    price: Optional[float]
    rationale: str # 缁?Agent 鍜屽鏌ュ悗鍙扮湅鐨勬枃瀛楃悊鐢?


# --- Protocol Interface (鎺ュ彛濂戠害) ---

class ATSStrategy:
    """鎵€鏈?ATS Skill 蹇呴』瀹炵幇鐨勫熀绫?""
    
    def __init__(self, name: str, **params):
        """鐢ㄩ厤缃〃閲岀殑鍙傛暟瀹炰緥鍖栫瓥鐣?""
        self.name = name
        self.params = params
        self.is_initialized = False

    def initialize(self) -> bool:
        """鍔犺浇鍒濆鐘舵€併€侀鐑寚鏍囩紦瀛樼瓑"""
        self.is_initialized = True
        return True

    def on_data(self, data: MarketDataDict, context: Dict[str, Any]) -> List[SignalDict]:
        """
        鏍稿績鍐崇瓥閫昏緫锛氳緭鍏ユ爣鍑嗚鎯呭瓧鍏革紝杈撳嚭鏍囧噯鎸囦护瀛楀吀鍒楄〃銆?
        context 鐢ㄤ簬浼犲叆褰撳墠璧勯噾銆佹寔浠撶瓑鐘舵€併€?
        """
        raise NotImplementedError("Strategy must implement `on_data`")

    def on_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        鍝嶅簲澶栭儴浜嬩欢锛屽 'ORDER_FILLED' 鎴?'ORDER_REJECTED'
        """
        pass

    def get_status(self) -> Dict[str, Any]:
        """鏆撮湶绛栫暐褰撳墠杩愯鏃剁殑鍐呴儴鐘舵€佸彉閲?""
        return {"name": self.name}
