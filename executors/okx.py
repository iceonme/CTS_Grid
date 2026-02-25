"""
OKX 实盘执行器
连接 OKX API 进行真实交易
"""

from datetime import datetime
import time
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
        self._last_trade_fetch = 0.0
        self._recent_trades: List[dict] = []
        
        # 本地持仓跟踪（用于解决demo模式balance API延迟问题）
        # symbol -> {'size': float, 'avg_price': float, 'entry_time': datetime}
        self._local_positions: dict = {}
        
        # 注册fill回调以更新本地持仓
        self.register_fill_callback(self._on_fill_update_position)

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """统一内部 symbol 形态为 BTC-USDT。"""
        return symbol.replace('/', '-')

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
    def _format_size(size: float, is_quote_currency: bool = False) -> str:
        """
        格式化订单数量，确保满足OKX精度要求
        
        Args:
            size: 订单数量
            is_quote_currency: 是否为报价币种（USDT金额），True时保留2位小数
        
        BTC-USDT: 精度 8位小数，最小下单量 0.00001 BTC，最小下单金额 10 USDT
        """
        if is_quote_currency:
            # USDT金额保留2位小数（货币精度）
            formatted = f"{size:.2f}"
            # 确保不小于最小下单金额 10 USDT
            if float(formatted) < 10:
                return "10.00"
            return formatted
        else:
            # 基础币种（BTC）保留8位小数
            formatted = f"{size:.8f}".rstrip('0').rstrip('.')
            # 如果格式化后为0或空，返回最小下单量 0.00001
            if not formatted or float(formatted) < 0.00001:
                return "0.00001"
            return formatted

    def submit_order(self, order: Order) -> str:
        """
        提交订单到 OKX
        """
        # OKX 使用 instId 格式: BTC-USDT
        inst_id = self._normalize_symbol(order.symbol)

        # 转换参数
        side = order.side.value
        ord_type = order.order_type.value
        
        # 调用 OKX API
        # 对于市价买入单，使用 ccy 参数指定按 USDT 金额下单，避免精度问题
        # 这样 sz 直接表示 USDT 金额，而不是 BTC 数量
        td_mode = 'cash'  # 现货模式
        
        # 市价买入单：使用 ccy 参数让 sz 表示 USDT 金额
        ccy = None
        sz = None
        resolved_size = None  # 用于后面的 fill 回调
        
        if ord_type == 'market' and side == 'buy' and order.meta.get('size_in_quote', False):
            # 对于市价买单，直接用 USDT 金额作为 sz，并设置 ccy='USDT'
            ccy = 'USDT'
            sz = self._format_size(float(order.size), is_quote_currency=True)  # 直接使用 USDT 金额
            # 对于 fill 回调，需要计算实际购买的 BTC 数量（预估）
            ref_price = self._get_reference_price(inst_id, order.price)
            if ref_price and float(order.size) > 0:
                resolved_size = float(order.size) / ref_price
            print(f"[下单调整] 市价买入单使用 ccy=USDT, sz={sz} (USDT金额)")
        else:
            # 其他情况（限价单、卖出单）：使用基础币种数量
            resolved_size = self._resolve_order_size(order, inst_id)
            if not resolved_size:
                order.status = OrderStatus.REJECTED
                order.meta['reject_reason'] = "invalid_order_size"
                return ""
            sz = self._format_size(resolved_size, is_quote_currency=False)

        px = str(order.price) if (order.price and order.order_type == OrderType.LIMIT) else None

        # 下单前打印关键参数与可用余额
        try:
            avail = self.get_cash()
            print(
                f"[下单] instId={inst_id} side={side} ordType={ord_type} "
                f"sz={sz} px={px} avail={avail:.8f}"
            )
        except Exception:
            print(
                f"[下单] instId={inst_id} side={side} ordType={ord_type} sz={sz} px={px}"
            )
        
        result = self.api.place_order(
            inst_id=inst_id,
            side=side,
            ord_type=ord_type,
            sz=sz,
            px=px,
            td_mode=td_mode,
            ccy=ccy,
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
                    # 计算报价币种金额（USDT金额）
                    if order.side == Side.BUY and order.meta.get('size_in_quote', False):
                        # 买入单：quote_amount 是下单的 USDT 金额
                        quote_amount = float(order.size)
                    else:
                        # 卖出单：quote_amount 是卖出获得的 USDT 金额
                        quote_amount = resolved_size * fill_price if resolved_size else 0.0
                    
                    fill = FillEvent(
                        order_id=okx_order_id,
                        symbol=order.symbol,
                        side=order.side,
                        filled_size=resolved_size,
                        filled_price=fill_price,
                        timestamp=datetime.now(),
                        fee=0.0,
                        quote_amount=quote_amount,
                    )
                    self._notify_fill(fill)

            return okx_order_id

        order.status = OrderStatus.REJECTED
        if result:
            code = result.get('code')
            msg = result.get('msg', '')
            s_code = ""
            s_msg = ""
            data = result.get('data') or []
            if isinstance(data, list) and len(data) > 0:
                s_code = data[0].get('sCode', '')
                s_msg = data[0].get('sMsg', '')
            order.meta['reject_reason'] = (
                f"okx_reject code={code} msg={msg} sCode={s_code} sMsg={s_msg}"
            )
        else:
            order.meta['reject_reason'] = "okx_request_failed"
        return ""

    def cancel_order(self, order_id: str) -> bool:
        """取消订单（待实现）"""
        # TODO: 实现撤单
        return False

    def get_position(self, symbol: str) -> Optional[Position]:
        """获取指定币种持仓（现货模式：从账户余额获取）"""
        inst_id = self._normalize_symbol(symbol)
        
        # 从所有持仓中筛选
        all_positions = self.get_all_positions()
        for pos in all_positions:
            if pos.symbol == inst_id:
                return pos
        return None

    def get_all_positions(self) -> List[Position]:
        """
        获取所有持仓（从OKX API查询真实交易持仓）
        
        Demo模式特殊处理：
        - balance API的spotBal有延迟，可能不及时反映最新成交
        - 因此会同时查询positions API（某些情况下demo模式也可用）
        - 并与本地跟踪的持仓数据合并，确保策略能看到正确的持仓
        """
        result: List[Position] = []
        
        try:
            if self.is_demo:
                # Demo模式：尝试多种方式获取持仓，并合并结果
                
                # 1. 从balance API获取（可能有延迟）
                balance_positions = self._get_positions_from_balance()
                
                # 2. 尝试从positions API获取（某些demo账户可能支持）
                api_positions = self._get_positions_from_api()
                
                # 3. 从本地跟踪获取（最实时）
                local_positions = []
                for symbol, pos_data in self._local_positions.items():
                    if abs(pos_data['size']) < 1e-12:
                        continue
                    current_px = self._get_reference_price(symbol)
                    upl = 0.0
                    if pos_data['avg_price'] > 0 and current_px:
                        upl = (current_px - pos_data['avg_price']) * pos_data['size']
                    local_positions.append(Position(
                        symbol=symbol,
                        size=pos_data['size'],
                        avg_price=pos_data['avg_price'],
                        entry_time=pos_data['entry_time'],
                        unrealized_pnl=upl,
                    ))
                
                # 4. 合并balance API和本地跟踪的数据
                # 优先使用balance API的数据，但当它返回零时使用本地数据
                merged = self._merge_positions(balance_positions, local_positions)
                
                # 5. 如果positions API也有数据，也考虑合并
                if api_positions:
                    merged = self._merge_positions(merged, api_positions)
                
                result = merged
                
                # 调试信息
                if balance_positions or local_positions:
                    print(f"[DEBUG持仓合并] balance数据: {[(p.symbol, p.size) for p in balance_positions]}, "
                          f"本地数据: {[(p.symbol, p.size) for p in local_positions]}, "
                          f"最终结果: {[(p.symbol, p.size) for p in result]}")
            else:
                # 实盘模式：使用positions API
                result = self._get_positions_from_api()
        except Exception as e:
            print(f"[获取持仓错误] {e}")
            import traceback
            traceback.print_exc()
        
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

    def get_total_value(self) -> float:
        """获取总权益（USDT + 其他币折算）"""
        balances = self.api.get_balances()
        if not balances:
            return 0.0

        total = 0.0
        for asset in balances.get('details', []):
            ccy = asset.get('ccy')
            if not ccy:
                continue
            eq = float(asset.get('eq', 0) or 0)
            if abs(eq) < 1e-12:
                continue
            if ccy == 'USDT':
                total += eq
                continue
            inst_id = f"{ccy}-USDT"
            px = self._get_reference_price(inst_id)
            if px:
                total += eq * px
        return total

    def get_recent_trades(self, inst_id: str, limit: int = 20, ttl_sec: int = 5) -> List[dict]:
        """从 OKX 拉取最近订单作为交易记录（带缓存）"""
        now = time.time()
        if now - self._last_trade_fetch < ttl_sec and self._recent_trades:
            return self._recent_trades

        res = self.api.get_order_history(inst_id=inst_id, limit=limit, inst_type='SPOT')
        trades: List[dict] = []
        if res and res.get('code') == '0':
            for o in res.get('data', []):
                ctime = o.get('cTime')
                try:
                    ts = datetime.fromtimestamp(int(ctime) / 1000).isoformat()
                except Exception:
                    ts = datetime.now().isoformat()
                
                side = (o.get('side') or '').upper()
                # 使用 avgPx（成交均价）替代 px（委托价）
                avg_px = float(o.get('avgPx') or o.get('px') or 0)
                
                # 获取成交数量（fillSz）或委托数量（sz）
                fill_sz = float(o.get('fillSz', 0) or o.get('sz', 0) or 0)
                
                # 判断是否使用了 ccy 参数（市价买入单按 USDT 金额下单）
                ccy = o.get('ccy', '')
                
                if side == 'BUY' and ccy == 'USDT':
                    # 市价买入单：sz 是 USDT 金额，需要计算 BTC 数量
                    quote_amount = float(o.get('sz', 0) or 0)  # USDT 金额
                    base_amount = fill_sz if fill_sz > 0 else (quote_amount / avg_px if avg_px > 0 else 0)
                    detail = f"花费 {quote_amount:.2f} USDT 买入 {base_amount:.6f} BTC"
                    size = base_amount
                elif side == 'SELL':
                    # 卖出单：sz 是 BTC 数量，计算获得的 USDT
                    base_amount = fill_sz
                    quote_amount = base_amount * avg_px if avg_px > 0 else 0
                    detail = f"卖出 {base_amount:.6f} BTC 获得 {quote_amount:.2f} USDT"
                    size = base_amount
                else:
                    # 其他情况（限价买入等）
                    size = fill_sz
                    detail = f"数量={size:.6f} 价格={avg_px:.2f}"
                    quote_amount = size * avg_px if avg_px > 0 else 0
                
                trades.append({
                    'type': side,
                    'symbol': o.get('instId', inst_id),
                    'price': avg_px,
                    'size': size,
                    'quote_amount': quote_amount,
                    'pnl': 0,
                    'time': ts,
                    'detail': detail
                })
        self._recent_trades = trades[:limit]
        self._last_trade_fetch = now
        return self._recent_trades

    def _on_fill_update_position(self, fill: FillEvent):
        """
        内部回调：根据成交事件更新本地持仓跟踪
        用于解决demo模式下balance API延迟导致的持仓信息不准确问题
        """
        inst_id = self._normalize_symbol(fill.symbol)
        
        if inst_id not in self._local_positions:
            self._local_positions[inst_id] = {
                'size': 0.0,
                'avg_price': 0.0,
                'entry_time': fill.timestamp,
                'total_cost': 0.0,  # 用于计算平均成本
            }
        
        pos = self._local_positions[inst_id]
        
        if fill.side == Side.BUY:
            # 买入：增加持仓，重新计算平均成本
            old_size = pos['size']
            old_cost = pos['total_cost']
            new_size = old_size + (fill.filled_size or 0)
            new_cost = old_cost + ((fill.filled_size or 0) * fill.filled_price)
            
            pos['size'] = new_size
            pos['total_cost'] = new_cost
            if new_size > 0:
                pos['avg_price'] = new_cost / new_size
            pos['entry_time'] = fill.timestamp
            
            print(f"[本地持仓更新] 买入 {inst_id}: +{fill.filled_size:.6f} @ {fill.filled_price:.2f}, "
                  f"总持仓={new_size:.6f}, 均价={pos['avg_price']:.2f}")
        else:
            # 卖出：减少持仓
            old_size = pos['size']
            new_size = old_size - (fill.filled_size or 0)
            
            # 按比例减少总成本
            if old_size > 0:
                pos['total_cost'] = pos['total_cost'] * (new_size / old_size) if new_size > 0 else 0.0
            
            pos['size'] = max(0.0, new_size)
            
            print(f"[本地持仓更新] 卖出 {inst_id}: -{fill.filled_size:.6f} @ {fill.filled_price:.2f}, "
                  f"剩余持仓={pos['size']:.6f}")
    
    def _get_positions_from_api(self) -> List[Position]:
        """从OKX API获取持仓（适用于实盘模式）"""
        result: List[Position] = []
        positions = self.api.get_positions()
        print(f"[DEBUG positions API] 返回: {positions}")
        if positions:
            for pos_data in positions:
                inst_id = pos_data.get('instId', '')
                pos_size = float(pos_data.get('pos', 0) or 0)
                
                # 跳过零持仓
                if abs(pos_size) < 1e-12:
                    continue
                
                # 获取平均持仓成本
                avg_px = float(pos_data.get('avgPx', 0) or 0)
                
                # 获取未实现盈亏
                upl = float(pos_data.get('upl', 0) or 0)
                
                # 获取持仓创建时间
                c_time = pos_data.get('cTime', '')
                try:
                    entry_time = datetime.fromtimestamp(int(c_time) / 1000) if c_time else datetime.now()
                except Exception:
                    entry_time = datetime.now()
                
                result.append(Position(
                    symbol=inst_id,
                    size=pos_size,  # 正数=多头，负数=空头
                    avg_price=avg_px,
                    entry_time=entry_time,
                    unrealized_pnl=upl,
                ))
        return result
    
    def _get_positions_from_balance(self) -> List[Position]:
        """从balance API获取持仓（适用于demo模式，但可能有延迟）"""
        result: List[Position] = []
        balances = self.api.get_balances()
        print(f"[DEBUG balances API] 返回: {balances}")
        if balances and balances.get('details'):
            for asset in balances['details']:
                ccy = asset.get('ccy', '')
                # 使用 spotBal（实际交易持仓）而不是 eq（总权益）
                spot_bal = float(asset.get('spotBal', 0) or 0)
                
                # 跳过零持仓和USDT（USDT是现金，不是持仓）
                if abs(spot_bal) < 1e-12 or ccy == 'USDT':
                    continue
                
                # 构建交易对符号
                inst_id = f"{ccy}-USDT"
                
                # 获取当前价格用于计算未实现盈亏
                avg_px = float(asset.get('avgPx', 0) or 0)
                current_px = self._get_reference_price(inst_id)
                
                # 计算未实现盈亏（简化计算：(当前价 - 成本价) * 数量）
                upl = 0.0
                if avg_px > 0 and current_px and current_px > 0:
                    upl = (current_px - avg_px) * spot_bal
                
                result.append(Position(
                    symbol=inst_id,
                    size=spot_bal,  # 正数=多头
                    avg_price=avg_px if avg_px > 0 else (current_px or 0),
                    entry_time=datetime.now(),
                    unrealized_pnl=upl,
                ))
        return result
    
    def _merge_positions(self, api_positions: List[Position], local_positions: List[Position]) -> List[Position]:
        """
        合并API持仓和本地跟踪持仓
        优先使用API数据，但当API返回零或较小时，使用本地数据作为补充
        """
        # 创建symbol到持仓的映射
        api_pos_map = {p.symbol: p for p in api_positions}
        local_pos_map = {p.symbol: p for p in local_positions}
        
        # 合并所有symbol
        all_symbols = set(api_pos_map.keys()) | set(local_pos_map.keys())
        result: List[Position] = []
        
        for symbol in all_symbols:
            api_pos = api_pos_map.get(symbol)
            local_pos = local_pos_map.get(symbol)
            
            if api_pos and abs(api_pos.size) >= 1e-12:
                # API有有效持仓数据，优先使用
                result.append(api_pos)
            elif local_pos and abs(local_pos.size) >= 1e-12:
                # API无数据或为零，但本地有跟踪数据，使用本地数据
                print(f"[持仓合并] {symbol}: API返回零持仓，使用本地跟踪数据: size={local_pos.size:.6f}")
                result.append(local_pos)
            elif api_pos:
                # 两者都接近零，使用API数据
                result.append(api_pos)
        
        return result
    
    def sync_positions(self):
        """同步持仓信息（可用于定期同步）"""
        pass  # 每次 get_position 都实时查询
