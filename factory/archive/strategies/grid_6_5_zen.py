import numpy as np
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from console.core import MarketData, Signal, Side, StrategyContext, FillEvent
from cartridges.strategies.base import BaseStrategy
from cartridges.strategies.grid_jeff_6_5 import GridJeff65Strategy, JeffIndicators, StrategyState

class GridZen65Strategy(GridJeff65Strategy):
    """
    Zen 6.5 绛栫暐锛?
    1. 缁ф壙 Jeff 6.5A 閫昏緫 (RSI 瑙﹀彂, MACD 浠撲綅娴?
    2. 鍥哄畾鏈噾: 浠撲綅濮嬬粓鍩轰簬鍒濆 10000 璁＄畻锛屼笉澶嶅埄銆?
    3. 鍏ㄤ粨姝㈡崯: 褰撳叏浠撶泩浜忎綆浜?-2.5% 鏃讹紝娓呬粨绂诲満銆?
    """
    def __init__(self, name="Grid_Zen_65", **params):
        # 寮哄埗璁剧疆 min_profit_filter 涓?True锛岀鍚?Zen 鐨勨€滅泩鍒╂彁鍙栤€濋€昏緫锛堝繀椤荤泩鍒╂墠鍑猴級
        params['min_profit_filter'] = True
        super().__init__(name, **params)
        
        self.stop_loss_threshold = params.get('stop_loss_threshold', -0.10) # 淇涓?-10%
        self.fixed_capital = params.get('fixed_capital', 10000.0)
        self.layer_value = self.fixed_capital / self.grid_layers
        
        self._prev_rsi = 50.0
        self._prev_hist = 0.0
        
    def on_data(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        # 棣栧厛鏇存柊鎸囨爣
        rsi, macd, macdsig, hist = self.indicators.update(data.close)
        
        # 璁板綍鍓嶅€间互渚垮垽鏂€滈挬澶粹€濆拰鈥滆浆寮扁€?
        prev_rsi = self._prev_rsi
        prev_hist = self._prev_hist
        self._prev_rsi = rsi
        self._prev_hist = hist
        
        # 鏇存柊鐘舵€?
        self.state.current_rsi = rsi
        self.state.macd = macd
        self.state.macdsignal = macdsig
        self.state.macdhist = hist

        # 姝㈡崯妫€鏌?
        pos = context.positions.get(data.symbol)
        if pos and pos.size > 0:
            if self.state.entry_prices:
                cost_basis = sum(self.state.entry_prices) / len(self.state.entry_prices)
                pnl_pct = (data.close / cost_basis) - 1
                
                if pnl_pct <= self.stop_loss_threshold:
                    self.log(f"[{data.timestamp}] STOP LOSS triggered! Price: {data.close:.2f} | Cost: {cost_basis:.2f} | PnL: {pnl_pct*100:.2f}%")
                    self.state.cooldown_until = data.timestamp + timedelta(minutes=self.cooldown_min * 2)
                    return [Signal(
                        timestamp=data.timestamp,
                        symbol=data.symbol,
                        side=Side.SELL,
                        size=pos.size,
                        meta={'layers': len(self.state.entry_prices), 'type': 'STOP_LOSS'},
                        reason=f"STOP LOSS triggered: {pnl_pct*100:.2f}%"
                    )]

        # 璧板父瑙勯€昏緫鍓嶇殑鐘舵€佹洿鏂伴€昏緫澶嶇敤鑷熀绫伙紝浣嗘垜浠渶瑕佺◢寰慨鏀瑰崠鐐瑰垽鏂?
        if self.indicators.count < 30:
            return []
        if self.state.cooldown_until and data.timestamp < self.state.cooldown_until:
            return []

        # 鐘舵€佹満锛歁ACD 鐘舵€佸垽鏂?(閫昏緫淇濇寔鍚屽師绛栫暐)
        curr_sig = macdsig
        prev_macd = self.state.macd # 涓婃淇濆瓨鍦ㄧ姸鎬侀噷鐨?
        prev_sig = self.state.macdsignal
        
        status = '涓€?
        if macd > curr_sig and prev_macd <= prev_sig: status = '閲戝弶'
        elif macd < curr_sig and prev_macd >= prev_sig: status = '姝诲弶'
        elif macd > curr_sig: status = '澶氬ご'
        else: status = '绌哄ご'
        self.state.macd_status = status

        signals = []
        layers = len(self.state.entry_prices)
        pos_size = pos.size if pos else 0
        cash = context.cash
        
        # 涔板叆閫昏緫 (淇濇寔鍘熸牱: RSI 浣庡惛)
        if rsi < self.rsi_buy and layers < self.grid_layers and cash > self.layer_value:
            if status == '閲戝弶':
                buy_layers = min(2, self.grid_layers - layers)
                sig_type = 'GOLD'
            else:
                buy_layers = 1
                sig_type = 'SILVER'
            
            buy_usdt = buy_layers * self.layer_value
            if cash >= buy_usdt:
                signals.append(Signal(
                    timestamp=data.timestamp, symbol=data.symbol, side=Side.BUY,
                    size=buy_usdt, meta={'size_in_quote': True, 'layers': buy_layers, 'type': sig_type},
                    reason=f"{sig_type} Buy: RSI={rsi:.1f}"
                ))
                self.state.cooldown_until = data.timestamp + timedelta(minutes=self.cooldown_min)

        # 鍗栧嚭閫昏緫 (浼樺寲鍗栫偣)
        elif layers > 0 and pos_size > 0:
            sell_layers = 0
            sig_type = 'SILVER'
            
            # 鍘熸湁寮哄姏鍗栫偣
            if rsi > self.rsi_sell_gold and status == '姝诲弶':
                sell_layers = min(2, layers)
                sig_type = 'GOLD'
            elif rsi > self.rsi_sell_silver:
                sell_layers = 1
                sig_type = 'SILVER'
            # 浼樺寲鍔犻锛氬姩閲忓噺寮卞崠鐐?
            elif rsi > 60 and rsi < prev_rsi and hist < prev_hist and hist > 0:
                # RSI 閽╁ご鍚戜笅 涓?MACD 绾㈡煴缂╃煭 涓?澶勪簬瓒呬拱鍖鸿竟缂?
                sell_layers = 1
                sig_type = 'MOMENTUM_EXIT'
                
            if sell_layers > 0:
                # 鐩堝埄鏍￠獙
                cost_sum = sum(self.state.entry_prices[:sell_layers])
                avg_cost = cost_sum / (sell_layers * (self.layer_value / cost_basis)) if layers > 0 else 0 # 绠€鍖栦及绠?
                # 閲嶆柊绮剧‘璁＄畻
                sell_btc_est = 0
                cost_sum_exact = 0
                for i in range(sell_layers):
                    if i < len(self.state.entry_prices):
                        c = self.state.entry_prices[i]
                        sell_btc_est += self.layer_value / c
                        cost_sum_exact += self.layer_value
                
                exact_avg_cost = cost_sum_exact / sell_btc_est if sell_btc_est > 0 else 999999
                
                if data.close > exact_avg_cost * (1 + self.min_profit_ratio):
                    # 鍙湁鐩堝埄鎵嶅嚭 (Zen鐨勬牳蹇冪泩鍒╀繚鎶?
                    if sell_layers >= layers or (pos_size - sell_btc_est) * data.close < 10:
                        sell_btc_est = pos_size
                    
                    signals.append(Signal(
                        timestamp=data.timestamp, symbol=data.symbol, side=Side.SELL,
                        size=sell_btc_est, meta={'layers': sell_layers, 'type': sig_type},
                        reason=f"{sig_type} Exit: RSI={rsi:.1f} Momentum Weakening"
                    ))
                    self.state.cooldown_until = data.timestamp + timedelta(minutes=self.cooldown_min)

        return signals

    def on_fill(self, fill: FillEvent):
        # 瑕嗗啓 on_fill 浠ヤ究鍦ㄦ鎹熷钩浠撴椂鎵撳嵃鐗规畩鏃ュ織
        sig_type = fill.meta.get('type', 'SILVER')
        if fill.side == Side.SELL and sig_type == 'STOP_LOSS':
            popped_costs = []
            while self.state.entry_prices:
                popped_costs.append(self.state.entry_prices.pop(0))
            
            avg_pop = sum(popped_costs)/len(popped_costs) if popped_costs else 0
            pnl_pct = (fill.filled_price - avg_pop) / avg_pop * 100 if avg_pop else 0
            self.state.stats['total_trades'] += 1
            self.log(f"[{fill.timestamp}] 鉂?姝㈡崯瀹屾垚 | 浠锋牸: {fill.filled_price:.2f} | 鐩堜簭: {pnl_pct:+.2f}% | 鏁伴噺: {fill.filled_size:.4f}")
        else:
            super().on_fill(fill)
