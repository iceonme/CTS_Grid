"""
OKX 实盘执行器
连接 OKX API 进行真实交易
"""

from datetime import datetime
from typing import Optional, List

from core import Order, FillEvent, Position, OrderStatus, Side, OrderType
from .base import BaseExecutor
from config.okx_config import OKXAPI


class OKXExecutor(BaseExecutor):
    """
    OKX 实盘执行器

    特性：
    1. 真实下单到 OKX
    2. 支持模拟盘/实盘切换
    3. 自动同步资金和持仓
    """

    def __init__(self,
                 api_key: str,
                 api_secret: str,
                 passphrase: str,
                 is_demo: bool = True):
        """
        Args:
            api_key: API Key
            api_secret: API Secret
            passphrase: API Passphrase
            is_demo: 是否使用模拟盘
        """
        super().__init__()
        self.api = OKXAPI(
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            is_demo=is_demo,
            simulate_slippage=False  # 真实成交不需要本地滑点
        )
        self.is_demo = is_demo
        self._order_map: dict = {}  # order_id -> local_order

    def _get_reference_price(self, inst_id: str, fallback: Optional[float] = None) -> Optional[float]:
        if fallback and fallback > 0:
            return float(fallback)
        ticker = self.api.get_ticker(inst_id)
        if ticker and ticker.get('last'):
            try:
                px = float(ticker['last'])
                return px if px > 0 else None
            except (TypeError, ValueError):
                return None
        return None

    def _resolve_order_size(self, order: Order, inst_id: str) -> Optional[float]:
        raw_size = float(order.size)
        if raw_size <= 0:
            return None

        # 与 V4 原始策略对齐：买入信号 size 是报价币金额（USDT）
        if order.side == Side.BUY and order.meta.get('size_in_quote', False):
            ref_price = self._get_reference_price(inst_id, order.price)
            if not ref_price:
                return None
            base_size = raw_size / ref_price
            return base_size if base_size > 0 else None

        # 卖出信号 size 直接使用基础币数量
        return raw_size

    @staticmethod
    def _format_size(size: float) -> str:
        return f"{size:.8f}".rstrip('0').rstrip('.')

    def submit_order(self, order: Order) -> str:
        """
        提交订单到 OKX
        """
        # OKX 使用 instId 格式: BTC-USDT
        inst_id = order.symbol.replace('/', '-')

        # 转换参数
        side = order.side.value
        ord_type = order.order_type.value
        resolved_size = self._resolve_order_size(order, inst_id)
        if not resolved_size:
            order.status = OrderStatus.REJECTED
            return ""

        sz = self._format_size(resolved_size)
        px = str(order.price) if (order.price and order.order_type == OrderType.LIMIT) else None

        # 调用 OKX API
        result = self.api.place_order(
            inst_id=inst_id,
            side=side,
            ord_type=ord_type,
            sz=sz,
            px=px,
            force_server=True  # 真实发送到服务器
        )

        if result and result.get('code') == '0':
            # OKX 返回的订单ID
            okx_order_id = result['data'][0]['ordId']
            order.order_id = okx_order_id
            order.status = OrderStatus.SUBMITTED
            self._order_map[okx_order_id] = order

            # 市价单在模拟盘里通常快速成交，这里回推 fill 保持策略/监控状态一致
            if order.order_type == OrderType.MARKET:
                fill_price = self._get_reference_price(inst_id, order.price) or 0.0
                if fill_price > 0:
                    fill = FillEvent(
                        order_id=okx_order_id,
                        symbol=order.symbol,
                        side=order.side,
                        filled_size=resolved_size,
                        filled_price=fill_price,
                        timestamp=datetime.now(),
                        fee=0.0,
                    )
                    self._notify_fill(fill)

            return okx_order_id

        order.status = OrderStatus.REJECTED
        return ""

    def cancel_order(self, order_id: str) -> bool:
        """取消订单（待实现）"""
        # TODO: 实现撤单
        return False

    def get_position(self, symbol: str) -> Optional[Position]:
        """获取持仓"""
        inst_id = symbol.replace('/', '-')
        positions = self.api.get_positions(inst_id)

        for pos_data in positions:
            size = float(pos_data.get('pos', 0) or 0)
            if abs(size) < 1e-12:
                continue
            return Position(
                symbol=symbol,
                size=size,
                avg_price=float(pos_data.get('avgPx', 0) or 0),
                entry_time=datetime.now(),  # OKX不返回入场时间
                unrealized_pnl=float(pos_data.get('upl', 0) or 0),
            )
        return None

    def get_all_positions(self) -> List[Position]:
        """获取所有持仓"""
        positions = self.api.get_positions()
        result = []
        for pos_data in positions:
            size = float(pos_data.get('pos', 0) or 0)
            if abs(size) < 1e-12:
                continue
            result.append(Position(
                symbol=pos_data.get('instId', '').replace('-', '/'),
                size=size,
                avg_price=float(pos_data.get('avgPx', 0) or 0),
                entry_time=datetime.now(),
                unrealized_pnl=float(pos_data.get('upl', 0) or 0),
            ))
        return result

    def get_cash(self) -> float:
        """获取可用资金"""
        balance = self.api.get_balance()
        if balance:
            return balance['availBal']
        return 0.0

    def get_equity(self) -> float:
        """获取总权益"""
        balance = self.api.get_balance()
        if balance:
            return balance['eq']
        return 0.0

    def sync_positions(self):
        """同步持仓信息（可用于定期同步）"""
        pass  # 每次 get_position 都实时查询
