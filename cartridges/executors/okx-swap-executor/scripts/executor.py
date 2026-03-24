import time
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from console.core.types import Order, FillEvent, Position, OrderStatus, Side, OrderType
from cartridges.executors.base import BaseExecutor
from console.utils.okx_api import OKXAPI

class OKXSwapExecutorSkill(BaseExecutor):
    """
    OKX 永续合约 (Swap) 执行器技能包封装
    支持多空持仓、杠杆调整、资产/合约单位换算
    """
    
    def __init__(self, **params):
        super().__init__()
        
        # 1. 基础配置解析
        self.symbol = params.get('symbol', 'ETH-USDT-SWAP').replace('/', '-')
        self.leverage = params.get('leverage', 3)
        self.ct_val = params.get('ct_val', 0.1) # ETH-USDT-SWAP 默认为 0.1
        self.is_demo = params.get('is_demo', True)
        
        # API 配置
        api_key = params.get('api_key')
        api_secret = params.get('api_secret')
        passphrase = params.get('passphrase')
        
        self.api = OKXAPI(
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            is_demo=self.is_demo,
            simulate_slippage=False # 实盘/模拟 模式不建议使用本地滑点模拟，除非是本地回测
        )
        
        self._order_map: Dict[str, Order] = {}
        
        # 2. 初始化账户模式 (强制双向持仓)
        self._initialize_account()

    def _initialize_account(self):
        """同步设置 OKX 账户为双向持仓及初始杠杆"""
        print(f"\n[okx-swap] >>> 初始化 OKX 合约账户: {self.symbol} <<<")
        try:
            # 设置持仓模式
            res_mode = self.api.set_position_mode('long_short_mode')
            if res_mode and res_mode.get('code') != '0':
                print(f"[okx-swap] 提示: 设置持仓模式返回 {res_mode.get('msg')} (可能已在双向模式)")
            else:
                print(f"[okx-swap] 持仓模式已设为: 双向 (Long/Short)")

            # 设置初初始杠杆
            res_lev = self.api.set_leverage(self.symbol, self.leverage)
            if res_lev and res_lev.get('code') == '0':
                print(f"[okx-swap] 初始杠杆设置成功: {self.leverage}x")
            else:
                print(f"[okx-swap] 杠杆设置注意: {res_lev.get('msg') if res_lev else '请求超时'}")
        except Exception as e:
            print(f"[okx-swap] 初始化账户配置异常: {e}")

    def _asset_to_contracts(self, amount: float) -> str:
        """
        数量转换: 标的资产数量 (如 ETH) -> 合约张数 (Contracts)
        """
        # OKX 规定张数必须是整数
        contracts = int(round(amount / self.ct_val))
        return str(max(1, contracts))

    def _contracts_to_asset(self, contracts: float) -> float:
        """
        数量转换: 合约张数 -> 标的资产数量
        """
        return contracts * self.ct_val

    def submit_order(self, order: Order) -> str:
        """
        提交合约订单
        需要 meta 中携带 'posSide': 'long' | 'short'
        """
        inst_id = order.symbol.replace('/', '-')
        side = order.side.value # 'buy' or 'sell'
        ord_type = order.order_type.value # 'market' or 'limit'
        
        # 客户端 ID (用于去重和追踪)
        cl_ord_id = order.meta.get('cl_ord_id') or f"cts_{int(time.time()*1000)}"
        
        # 合约方向处理
        pos_side = order.meta.get('posSide')
        if not pos_side:
            # 简化逻辑：如果没有指定，自动推导 (注意：这在复杂的对冲策略中可能不可靠)
            pos_side = 'long' if order.side == Side.BUY else 'short'
        
        # 单位换算
        sz = self._asset_to_contracts(order.size)
        px = str(order.price) if order.price and order.order_type == OrderType.LIMIT else None
        
        print(f"[okx-swap] 发单: {side} {pos_side} {sz}张 ({order.size}币) | {inst_id} | Type:{ord_type}")
        
        res = self.api.place_order(
            inst_id=inst_id,
            side=side,
            ord_type=ord_type,
            sz=sz,
            px=px,
            td_mode='cross', #Swap通常使用全仓
            pos_side=pos_side,
            cl_ord_id=cl_ord_id
        )
        
        if res and res.get('code') == '0':
            ord_id = res['data'][0]['ordId']
            order.order_id = ord_id
            order.status = OrderStatus.SUBMITTED
            self._order_map[ord_id] = order
            
            # 如果是市价单，我们会尝试立即触发成交同步 (简化开发)
            if ord_type == 'market':
                self._sync_immediate_fill(order, ord_id, sz)
            
            return ord_id
        
        err_msg = res.get('msg', 'API Error') if res else 'Timeout'
        print(f"[okx-swap] 下单失败: {err_msg}")
        order.status = OrderStatus.REJECTED
        return ""

    def _sync_immediate_fill(self, order: Order, ord_id: str, contracts: str):
        """市价单成交后，快速产生一个 FillEvent 通知策略"""
        ticker = self.api.get_ticker(order.symbol.replace('/', '-'))
        price = float(ticker['last']) if ticker else (order.price or 0.0)
        
        fill = FillEvent(
            order_id=ord_id,
            symbol=order.symbol,
            side=order.side,
            filled_size=self._contracts_to_asset(float(contracts)),
            filled_price=price,
            timestamp=datetime.now(timezone.utc),
            meta={'posSide': order.meta.get('posSide')}
        )
        self._notify_fill(fill)

    def cancel_order(self, order_id: str) -> bool:
        # TODO: 实现在 OKX 撤单逻辑
        return False

    def get_position(self, symbol: str) -> Optional[Position]:
        all_pos = self.get_all_positions()
        for p in all_pos:
            if p.symbol == symbol:
                return p
        return None

    def get_all_positions(self) -> List[Position]:
        """获取并转换持仓状态"""
        raw_pos = self.api.get_positions(inst_type='SWAP')
        positions = []
        for p in raw_pos:
            inst_id = p.get('instId')
            # OKX Swap 中 pos 是张数
            pos_contracts = float(p.get('pos', 0))
            if pos_contracts == 0: continue
            
            pos_side = p.get('posSide')
            # 转换回标的资产数量
            asset_size = self._contracts_to_asset(pos_contracts)
            if pos_side == 'short':
                asset_size = -abs(asset_size)
            
            # 解析时间
            ts_ms = int(p.get('cTime', 0))
            entry_time = datetime.fromtimestamp(ts_ms/1000, tz=timezone.utc) if ts_ms else datetime.now(timezone.utc)
            
            positions.append(Position(
                symbol=inst_id,
                size=asset_size,
                avg_price=float(p.get('avgPx', 0)),
                entry_time=entry_time,
                unrealized_pnl=float(p.get('upl', 0))
            ))
        return positions

    def get_cash(self) -> float:
        """获取 USDT 可用余额"""
        bal = self.api.get_balance(ccy='USDT')
        return bal['availBal'] if bal else 0.0

    def set_leverage(self, leverage: float):
        """
        自定义方法：允许策略动态调整杠杆
        通常在 Signal.meta 或 context.meta 触发
        """
        res = self.api.set_leverage(self.symbol, int(leverage))
        if res and res.get('code') == '0':
            self.leverage = leverage
            return True
        return False
