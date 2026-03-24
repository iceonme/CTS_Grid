"""
模拟执行器
在本地模拟订单执行，支持滑点和延迟模拟
"""

import time
import uuid
from datetime import datetime
from typing import Optional, List, Dict
import numpy as np

from core import (
    Order, FillEvent, Position, OrderStatus, 
    Side, OrderType, MarketData
)
from .base import BaseExecutor


class PaperExecutor(BaseExecutor):
    """
    模拟执行器
    
    特性：
    1. 本地模拟成交
    2. 支持滑点模型（固定/自适应）
    3. 支持延迟模拟
    4. 维护虚拟资金和持仓
    """
    
    def __init__(self, 
                 initial_capital: float = 10000.0,
                 fee_rate: float = 0.001,
                 slippage_model: str = 'adaptive',  # none, fixed, adaptive
                 slippage_base: float = 0.0005,
                 latency_ms: float = 0):
        """
        Args:
            initial_capital: 初始资金
            fee_rate: 手续费率
            slippage_model: 滑点模型
            slippage_base: 基础滑点
            latency_ms: 模拟延迟（毫秒）
        """
        super().__init__()
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.fee_rate = fee_rate
        self.slippage_model = slippage_model
        self.slippage_base = slippage_base
        self.latency_ms = latency_ms
        
        # 状态
        self._positions: Dict[str, Position] = {}  # symbol -> Position
        self._orders: Dict[str, Order] = {}  # order_id -> Order
        self._current_price: float = 0.0
        self._current_time: Optional[datetime] = None
        
    def update_market_data(self, timestamp: datetime, price: float):
        """更新市场数据"""
        self._current_time = timestamp
        self._current_price = price
        
    def _calculate_slippage(self, side: Side, amount: float) -> float:
        """计算滑点"""
        if self.slippage_model == 'none':
            return 0.0
        
        if self.slippage_model == 'fixed':
            return self.slippage_base
        
        # 自适应模型
        depth_factor = 1.0
        slippage = self.slippage_base * depth_factor * (1 + np.random.normal(0, 0.3))
        return max(0.0001, min(0.005, slippage))
    
    def _simulate_latency(self):
        """模拟网络延迟"""
        if self.latency_ms > 0:
            actual_latency = self.latency_ms * (0.8 + np.random.random() * 0.4)
            time.sleep(actual_latency / 1000)
    
    def submit_order(self, order: Order) -> str:
        """
        提交订单（立即成交）
        """
        self._simulate_latency()
        
        # 生成订单ID
        order_id = str(uuid.uuid4())[:16]
        order.order_id = order_id
        
        # 使用 UTC 时间
        from datetime import timezone
        order.timestamp = self._current_time or datetime.now(timezone.utc)
        
        # 计算成交价格（含滑点）
        slippage = self._calculate_slippage(order.side, order.size)
        
        if order.side == Side.BUY:
            executed_price = self._current_price * (1 + slippage)
        else:
            executed_price = self._current_price * (1 - slippage)
        
        # 统一成交数量语义：
        # - BUY + size_in_quote=True: order.size 为报价币金额（如 USDT），需换算为基础币数量
        # - 其它情况: order.size 为基础币数量
        size_in_quote = bool(order.meta.get('size_in_quote', False))
        executed_size = float(order.size)
        trade_value = executed_size * executed_price
        if order.side == Side.BUY and size_in_quote:
            if executed_price <= 0:
                order.status = OrderStatus.REJECTED
                order.meta['reject_reason'] = "invalid_execution_price"
                self._orders[order_id] = order
                return order_id
            trade_value = float(order.size)
            executed_size = trade_value / executed_price
        fee = trade_value * self.fee_rate
        
        # 检查资金/持仓
        if order.side == Side.BUY:
            total_cost = trade_value + fee
            if total_cost > self.cash:
                order.status = OrderStatus.REJECTED
                order.meta['reject_reason'] = "insufficient_cash"
                self._orders[order_id] = order
                return order_id
        else:
            pos = self._positions.get(order.symbol)
            if not pos or pos.size < executed_size:
                order.status = OrderStatus.REJECTED
                order.meta['reject_reason'] = "insufficient_position"
                self._orders[order_id] = order
                return order_id
        
        # 更新资金和持仓
        if order.side == Side.BUY:
            self.cash -= (trade_value + fee)
            
            if order.symbol not in self._positions:
                self._positions[order.symbol] = Position(
                    symbol=order.symbol,
                    size=0.0,
                    avg_price=0.0,
                    entry_time=order.timestamp
                )
            
            pos = self._positions[order.symbol]
            # 更新平均成本
            total_cost = pos.size * pos.avg_price + executed_size * executed_price
            pos.size += executed_size
            pos.avg_price = total_cost / pos.size if pos.size > 0 else 0
            
        else:
            pos = self._positions[order.symbol]
            
            # 计算实现盈亏
            realized_pnl = (executed_price - pos.avg_price) * executed_size - fee
            
            self.cash += (trade_value - fee)
            pos.size -= executed_size
            
            if pos.size <= 0:
                del self._positions[order.symbol]
        
        # 更新订单状态
        order.status = OrderStatus.FILLED
        order.filled_size = executed_size
        order.avg_price = executed_price
        self._orders[order_id] = order
        
        # 发送成交回报
        fill = FillEvent(
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            filled_size=executed_size,
            filled_price=executed_price,
            timestamp=order.timestamp,
            fee=fee,
            pnl=realized_pnl if order.side == Side.SELL else None,
            quote_amount=trade_value  # 计算金额（USDT金额）
        )
        self._notify_fill(fill)
        
        return order_id
    
    def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        if order_id in self._orders:
            order = self._orders[order_id]
            if order.status == OrderStatus.PENDING:
                order.status = OrderStatus.CANCELLED
                return True
        return False
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """获取持仓"""
        return self._positions.get(symbol)
    
    def get_all_positions(self) -> List[Position]:
        """获取所有持仓"""
        return list(self._positions.values())
    
    def get_cash(self) -> float:
        """获取可用资金"""
        return self.cash
    
    def get_total_value(self) -> float:
        """获取总资产"""
        position_value = sum(
            pos.size * self._current_price 
            for pos in self._positions.values()
        )
        return self.cash + position_value
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'cash': self.cash,
            'initial_capital': self.initial_capital,
            'positions': {
                symbol: {
                    'symbol': pos.symbol,
                    'size': pos.size,
                    'avg_price': pos.avg_price,
                    'entry_time': pos.entry_time.isoformat() if pos.entry_time else None
                } for symbol, pos in self._positions.items()
            }
        }
    
    def from_dict(self, data: Dict):
        """从字典加载"""
        self.cash = data.get('cash', self.initial_capital)
        self.initial_capital = data.get('initial_capital', self.initial_capital)
        
        self._positions.clear()
        for symbol, pos_data in data.get('positions', {}).items():
            entry_time = None
            if pos_data.get('entry_time'):
                from datetime import timezone
                entry_time = datetime.fromisoformat(pos_data['entry_time'].replace('Z', '+00:00'))
            
            self._positions[symbol] = Position(
                symbol=pos_data['symbol'],
                size=float(pos_data['size']),
                avg_price=float(pos_data['avg_price']),
                entry_time=entry_time
            )

    def save_state(self, filepath: str):
        """保存状态到文件"""
        import json
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, indent=4)
            print(f"[PaperExecutor] 状态已保存至 {filepath}")
        except Exception as e:
            print(f"[PaperExecutor] 保存状态失败: {e}")

    def load_state(self, filepath: str):
        """从文件加载状态"""
        import json
        import os
        if not os.path.exists(filepath):
            return False
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.from_dict(data)
            print(f"[PaperExecutor] 已从 {filepath} 加载状态")
            return True
        except Exception as e:
            print(f"[PaperExecutor] 加载状态失败: {e}")
            return False

    def reset(self):
        """重置状态"""
        self.cash = self.initial_capital
        self._positions.clear()
        self._orders.clear()
