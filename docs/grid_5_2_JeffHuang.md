# 放置于 /openclaw/config/strategies/
strategy:
  name: "V5.2_5min_TrendForce"
  version: "5.2.0"
  description: "5分钟趋势确认+强制满仓+动态止盈"
  
  # 核心周期
  kline_interval: "5m"
  max_history_bars: 100
  
  # 交易对
  symbol: "BTC/USDT"
  exchange: "okx"
  
  # 资金配置
  initial_capital: 10000
  max_layers: 5
  layer_size_usdt: 2000  # 每层2000U
  
  # MACD参数（5分钟）
  macd:
    fast: 12
    slow: 26
    signal: 9
    
  # RSI分层（5分钟）
  rsi:
    periods: [6, 12, 24]  # RSI1, RSI2, RSI3
    buy_threshold: 40
    sell_threshold: 65
    extreme_overbought: 75
    
  # 网格参数
  grid:
    range_percent: 0.04      # ±4%
    dynamic_step: 0.015      # 1.5%上移
    min_grid_width: 0.02     # 最小网格宽度2%
    
  # 趋势评分与强制仓位（核心）
  trend_position:
    score_high: 4
    target_high: 5           # 强制满仓
    score_mid: 2
    target_mid: 3            # 试探建仓
    score_low: 0
    target_low: 1            # 轻仓观望
    
  # 成交量确认
  volume:
    enable: true
    ma_period: 20
    threshold: 1.3           # >MA20*1.3
    
  # 动态止盈（新增）
  take_profit:
    enable: true
    rsi_levels: [65, 70, 75]  # 分批止盈
    sell_layers: [2, 1, 1]    # 对应卖出层数
    
  # 反转保护（新增）
  stop_loss:
    enable: true
    ma_cross: true            # MA5下穿MA10
    macd_cross: true          # MACD死叉
    rsi_drop: 15              # 1小时内RSI跌15点
    volume_spike: 1.5         # 放量下跌


# 参考代码

# 放置于 /openclaw/strategies/
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from openclaw.core import Strategy, Signal, OrderSide

class V5_2_5min_Strategy(Strategy):
    """
    V5.2 5分钟趋势确认 + 强制满仓策略
    TG通知集成版本
    """
    
    def __init__(self, config, tg_bot=None):
        super().__init__(config)
        self.tg_bot = tg_bot  # Telegram通知
        self.current_layers = 0
        self.grid_center = None
        self.trend_score_history = []
        
    async def on_bar(self, bar):
        """每5分钟K线触发"""
        df = self.get_ohlcv(self.config['kline_interval'], limit=50)
        
        # 计算指标
        trend_score, metrics = self.calculate_trend_score(df)
        target_layers = self.get_target_position(trend_score, df)
        
        # 检查反转保护
        stop_signal = self.check_reversal_protection(df, metrics)
        if stop_signal:
            await self.execute_signal(stop_signal, "反转保护")
            return
            
        # 正常交易逻辑
        signals = self.generate_signals(df, trend_score, target_layers, metrics)
        
        for sig in signals:
            await self.execute_signal(sig, f"趋势分{trend_score}")
            
        # 记录状态
        self.trend_score_history.append({
            'time': datetime.now(),
            'score': trend_score,
            'target': target_layers,
            'current': self.current_layers,
            'price': bar['close']
        })
        
        # TG通知（每小时或信号时）
        if len(self.trend_score_history) % 12 == 0 or signals:  # 12*5min=1h
            await self.send_status_update(trend_score, target_layers, metrics)
    
    def calculate_trend_score(self, df):
        """趋势强度评分 0-5"""
        closes = df['close']
        score = 0
        metrics = {}
        
        # MACD
        exp1 = closes.ewm(span=12, adjust=False).mean()
        exp2 = closes.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        
        macd_val, signal_val = macd.iloc[-1], signal.iloc[-1]
        metrics['macd'] = macd_val
        metrics['signal'] = signal_val
        
        if macd_val > signal_val and macd_val > 0:
            score += 2
        elif macd_val > signal_val:
            score += 1
            
        # RSI分层
        def rsi_calc(prices, period):
            delta = prices.diff()
            gain = delta.where(delta > 0, 0).rolling(period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
            return 100 - (100 / (1 + gain/loss))
        
        rsi1 = rsi_calc(closes, 6).iloc[-1]
        rsi2 = rsi_calc(closes, 12).iloc[-1]
        rsi3 = rsi_calc(closes, 24).iloc[-1]
        
        metrics['rsi'] = [rsi1, rsi2, rsi3]
        
        if rsi1 < 40:
            score += 2
        elif rsi1 < 50:
            score += 1
            
        if rsi3 > 50:
            score += 1
            
        # 成交量
        if len(df) >= 20:
            vol_ma = df['volume'].rolling(20).mean().iloc[-1]
            vol_now = df['volume'].iloc[-1]
            metrics['volume_ratio'] = vol_now / vol_ma if vol_ma > 0 else 1
            
            if vol_now > vol_ma * 1.3:
                score += 1
                
        return min(score, 5), metrics
    
    def get_target_position(self, trend_score, df):
        """强制仓位管理"""
        if trend_score >= 4:
            # 强趋势：强制满仓，关闭动态网格
            self.dynamic_grid = False
            if self.grid_center is None:
                self.grid_center = df['close'].iloc[-1]
            return 5
            
        elif trend_score >= 2:
            # 中等趋势：动态网格，试探建仓
            self.dynamic_grid = True
            return 3
            
        else:
            # 震荡或弱势：轻仓
            self.dynamic_grid = True
            return 1
    
    def check_reversal_protection(self, df, metrics):
        """趋势反转保护"""
        closes = df['close']
        current_price = closes.iloc[-1]
        
        # MA5下穿MA10
        ma5 = closes.rolling(5).mean().iloc[-1]
        ma10 = closes.rolling(10).mean().iloc[-1]
        ma5_prev = closes.rolling(5).mean().iloc[-2] if len(closes) > 1 else ma5
        ma10_prev = closes.rolling(10).mean().iloc[-2] if len(closes) > 1 else ma10
        
        if ma5 < ma10 and ma5_prev >= ma10_prev and self.current_layers > 0:
            return Signal(
                side=OrderSide.SELL,
                layers=min(2, self.current_layers),
                reason="MA5下穿MA10，减仓保护",
                urgency="high"
            )
        
        # MACD死叉
        if metrics['macd'] < metrics['signal'] and metrics['macd'] > 0:
            if self.current_layers > 0:
                return Signal(
                    side=OrderSide.SELL,
                    layers=min(1, self.current_layers),
                    reason="MACD死叉预警",
                    urgency="medium"
                )
        
        # RSI快速下跌
        if len(self.trend_score_history) >= 12:  # 1小时前
            old_rsi = self.trend_score_history[-12].get('rsi', [50,50,50])[0]
            if old_rsi - metrics['rsi'][0] > 15 and self.current_layers > 0:
                return Signal(
                    side=OrderSide.SELL,
                    layers=min(2, self.current_layers),
                    reason=f"RSI快速下跌{old_rsi-metrics['rsi'][0]:.1f}点",
                    urgency="high"
                )
        
        return None
    
    def generate_signals(self, df, trend_score, target_layers, metrics):
        """生成交易信号"""
        signals = []
        current_price = df['close'].iloc[-1]
        rsi1 = metrics['rsi'][0]
        
        # 买入逻辑
        if self.current_layers < target_layers:
            # 强趋势放宽RSI
            rsi_threshold = 55 if trend_score >= 4 else self.config['rsi']['buy_threshold']
            
            if rsi1 < rsi_threshold:
                buy_layers = min(target_layers - self.current_layers, 
                               max(1, (target_layers - self.current_layers) // 2))
                
                signals.append(Signal(
                    side=OrderSide.BUY,
                    layers=buy_layers,
                    price=current_price,
                    reason=f"趋势{trend_score}，RSI{rsi1:.1f}，建{buy_layers}层",
                    urgency="high" if trend_score >= 4 else "normal"
                ))
        
        # 动态止盈
        elif self.current_layers > 0:
            tp_levels = self.config['take_profit']['rsi_levels']
            tp_layers = self.config['take_profit']['sell_layers']
            
            for i, (tp_rsi, tp_layer) in enumerate(zip(tp_levels, tp_layers)):
                if rsi1 > tp_rsi and self.current_layers > 0:
                    sell = min(tp_layer, self.current_layers)
                    signals.append(Signal(
                        side=OrderSide.SELL,
                        layers=sell,
                        price=current_price,
                        reason=f"RSI{rsi1:.1f}>{tp_rsi}，止盈{sell}层({i+1}/3)",
                        urgency="normal"
                    ))
                    break  # 只触发一层
        
        # 震荡网格（低趋势分时）
        if trend_score < 2 and self.grid_center:
            lower = self.grid_center * (1 - self.config['grid']['range_percent'])
            upper = self.grid_center * (1 + self.config['grid']['range_percent'])
            
            if current_price < lower and self.current_layers < 5:
                signals.append(Signal(
                    side=OrderSide.BUY,
                    layers=1,
                    price=current_price,
                    reason=f"网格下轨{lower:.0f}买入",
                    urgency="low"
                ))
            elif current_price > upper and self.current_layers > 0:
                signals.append(Signal(
                    side=OrderSide.SELL,
                    layers=1,
                    price=current_price,
                    reason=f"网格上轨{upper:.0f}卖出",
                    urgency="low"
                ))
        
        return signals
    
    async def execute_signal(self, signal, context):
        """执行信号并通知"""
        # 执行交易
        order = await self.place_order(signal)
        
        # 更新仓位
        if signal.side == OrderSide.BUY:
            self.current_layers += signal.layers
        else:
            self.current_layers -= signal.layers
        
        # TG通知
        if self.tg_bot:
            msg = f"""
🤖 *V5.2_5min 交易信号*

📊 操作：{'买入' if signal.side == OrderSide.BUY else '卖出'} {signal.layers}层
💰 价格：${signal.price:,.2f}
📈 原因：{signal.reason}
⚡ 紧急度：{signal.urgency}
🎯 当前持仓：{self.current_layers}/5层
📍 网格中心：{self.grid_center:.0f if self.grid_center else '动态'}

_Context: {context}_
            """
            await self.tg_bot.send_message(msg, parse_mode='Markdown')
    
    async def send_status_update(self, trend_score, target_layers, metrics):
        """TG状态更新"""
        if not self.tg_bot:
            return
            
        rsi_str = '/'.join([f"{r:.1f}" for r in metrics['rsi']])
        
        msg = f"""
📊 *V5.2_5min 状态报告*

⏰ 时间：{datetime.now().strftime('%m-%d %H:%M')}
💰 价格：${self.last_price:,.2f}
📈 趋势分：{trend_score}/5 {'🔥强趋势' if trend_score>=4 else '⚡中等' if trend_score>=2 else '💤观望'}
🎯 目标/当前：{target_layers}/{self.current_layers}层
📉 RSI：{rsi_str}
📊 MACD：{metrics['macd']:.2f}/{metrics['signal']:.2f}
💹 量比：{metrics.get('volume_ratio', 1):.2f}

{'✅ 强制满仓已激活' if trend_score>=4 and not self.dynamic_grid else '🔧 动态网格运行中' if self.dynamic_grid else '⏸️ 待机'}
        """
        await self.tg_bot.send_message(msg, parse_mode='Markdown')

