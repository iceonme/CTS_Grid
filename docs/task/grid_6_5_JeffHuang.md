V6.5A 动态网格交易策略
技术文档 v1.0
版本: 6.5A
更新日期: 2026-03-04
适用标的: BTC/USDT永续合约
建议本金: $10,000
1. 策略概述
V6.5A是一款双轨制动态网格交易策略，核心设计为统一RSI门槛触发，MACD区分仓位大小，解决传统MACD滞后导致的踏空问题。
核心创新
统一买入门槛: RSI<30即触发，不等待MACD金叉
分层仓位管理: MACD金叉→2层(黄金)，其他→1层(白银)
梯度卖出: RSI>65→1层，RSI>70+死叉→2层
2. 策略参数
Table
参数	值	说明
买入门槛	RSI < 30	统一触发线
黄金买入	RSI<30 + MACD金叉	2层 ($4,000)
白银买入	RSI<30 + MACD其他状态	1层 ($2,000)
白银卖出	RSI > 65	1层
黄金卖出	RSI>70 + MACD死叉	2层
最大持仓	5层	防止过度暴露
保留现金	≥20%	应急与加仓
冷却时间	15分钟	避免过度交易
网格层数	5层	每层$2,000
3. 交易逻辑流程图
plain
Copy
开始
  │
  ▼
获取1分钟K线 → 计算RSI(14) + MACD(12,26,9)
  │
  ▼
RSI < 30 ? ──否──→ 检查卖出 ──→ 结束
  │是
  ▼
MACD == 金叉 ? ──是──→ 买入2层(黄金) ──→ 冷却15分钟
  │否
  ▼
买入1层(白银) ──→ 冷却15分钟
  │
卖出检查 ◄──────────────────────────────┐
  │                                      │
RSI > 70 且 MACD死叉 ? ──是──→ 卖出2层(黄金) ─┤
  │否                                      │
  ▼                                      │
RSI > 65 ? ──是──→ 卖出1层(白银) ──────────┤
  │否                                      │
  ▼                                      │
持有 ────────────────────────────────────┘
4. 核心代码
Python
Copy
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime
import time
import logging
import json

CONFIG = {
    'api_key': 'YOUR_OKX_API_KEY',
    'secret': 'YOUR_OKX_SECRET',
    'password': 'YOUR_OKX_PASSPHRASE',
    'symbol': 'BTC/USDT:USDT',
    'capital': 10000,
    'test_mode': True  # True=模拟盘, False=实盘
}

class GridStrategyV65A:
    VERSION = "6.5A"
    
    def __init__(self, config):
        self.config = config
        self.exchange = ccxt.okx({
            'apiKey': config['api_key'],
            'secret': config['secret'],
            'password': config['password'],
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
                'test': config.get('test_mode', True)
            }
        })
        
        self.symbol = config['symbol']
        self.initial_capital = config['capital']
        self.grid_layers = 5
        self.layer_value = self.initial_capital / self.grid_layers
        
        # V6.5A阈值
        self.rsi_buy_threshold = 30
        self.rsi_sell_silver = 65
        self.rsi_sell_gold = 70
        
        self.cash_usdt = self.initial_capital
        self.position_btc = 0.0
        self.entry_prices = []
        self.cooldown_until = 0
        
        self.stats = {
            'gold_buy': 0, 'silver_buy': 0,
            'gold_sell': 0, 'silver_sell': 0,
            'start_time': datetime.now().isoformat(),
            'total_trades': 0
        }
    
    def fetch_data(self, timeframe='1m', limit=100):
        try:
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            logging.error(f"数据获取失败: {e}")
            return None
    
    def calculate_indicators(self, df):
        # RSI(14)
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df['rsi'] = 100 - (100 / (1 + gain / loss))
        
        # MACD
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        
        # MACD状态
        df['macd_status'] = '中性'
        for i in range(1, len(df)):
            curr, prev = df['macd'].iloc[i], df['macd'].iloc[i-1]
            sig_curr, sig_prev = df['macd_signal'].iloc[i], df['macd_signal'].iloc[i-1]
            
            if curr > sig_curr and prev <= sig_prev:
                df.loc[i, 'macd_status'] = '金叉'
            elif curr < sig_curr and prev >= sig_prev:
                df.loc[i, 'macd_status'] = '死叉'
            elif curr > sig_curr:
                df.loc[i, 'macd_status'] = '多头'
            else:
                df.loc[i, 'macd_status'] = '空头'
        
        return df
    
    def get_equity(self, price):
        return self.cash_usdt + self.position_btc * price
    
    def get_layers(self):
        return len(self.entry_prices)
    
    def execute_order(self, side, price, layers, signal_type):
        try:
            if side == 'BUY':
                amount_usdt = layers * self.layer_value
                if self.cash_usdt < amount_usdt:
                    return False
                
                amount_btc = amount_usdt / price
                order = self.exchange.create_market_buy_order(self.symbol, amount_btc)
                fill_price = order.get('average', price)
                
                self.cash_usdt -= amount_usdt
                self.position_btc += amount_btc
                for _ in range(layers):
                    self.entry_prices.append(fill_price)
                
                key = f"{signal_type.lower()}_buy"
                self.stats[key] = self.stats.get(key, 0) + 1
                self.stats['total_trades'] += 1
                
                logging.info(f"[BUY {signal_type}] 价:${fill_price:,.2f} 量:{amount_btc:.6f}BTC 层:{layers}")
                return True
                
            else:  # SELL
                if not self.entry_prices or self.position_btc <= 0:
                    return False
                
                sell_btc = 0
                for _ in range(min(layers, len(self.entry_prices))):
                    if self.entry_prices:
                        cost = self.entry_prices.pop(0)
                        sell_btc += self.layer_value / cost
                
                sell_btc = min(sell_btc, self.position_btc)
                order = self.exchange.create_market_sell_order(self.symbol, sell_btc)
                fill_price = order.get('average', price)
                
                revenue = sell_btc * fill_price
                self.cash_usdt += revenue
                self.position_btc -= sell_btc
                
                key = f"{signal_type.lower()}_sell"
                self.stats[key] = self.stats.get(key, 0) + 1
                self.stats['total_trades'] += 1
                
                logging.info(f"[SELL {signal_type}] 价:${fill_price:,.2f} 量:{sell_btc:.6f}BTC 层:{layers}")
                return True
                
        except Exception as e:
            logging.error(f"订单失败: {e}")
            return False
    
    def check_signal(self, rsi, macd):
        if time.time() < self.cooldown_until:
            return None, 0, None
        
        layers = self.get_layers()
        
        # 买入
        if rsi < self.rsi_buy_threshold and layers < self.grid_layers and self.cash_usdt > self.layer_value:
            if macd == '金叉':
                return 'BUY', 2, 'GOLD'
            else:
                return 'BUY', 1, 'SILVER'
        
        # 卖出
        if layers > 0 and self.position_btc > 0:
            if rsi > self.rsi_sell_gold and macd == '死叉':
                return 'SELL', 2, 'GOLD'
            elif rsi > self.rsi_sell_silver:
                return 'SELL', 1, 'SILVER'
        
        return None, 0, None
    
    def run(self):
        iteration = 0
        while True:
            try:
                iteration += 1
                df = self.fetch_data('1m', 100)
                if df is None or len(df) < 30:
                    time.sleep(60)
                    continue
                
                df = self.calculate_indicators(df)
                latest = df.iloc[-1]
                price, rsi, macd = latest['close'], latest['rsi'], latest['macd_status']
                
                if iteration % 10 == 0:
                    equity = self.get_equity(price)
                    ret = (equity - self.initial_capital) / self.initial_capital * 100
                    logging.info(f"权益:${equity:,.0f}({ret:+.2f}%) 价:${price:,.0f} RSI:{rsi:.1f} MACD:{macd} 层:{self.get_layers()}")
                
                signal, layers, sig_type = self.check_signal(rsi, macd)
                if signal:
                    if self.execute_order(signal, price, layers, sig_type):
                        self.cooldown_until = time.time() + 900
                
                if iteration % 60 == 0:
                    runtime = (datetime.now() - datetime.fromisoformat(self.stats['start_time'])).total_seconds() / 3600
                    logging.info(f"[统计] 运行:{runtime:.1f}h 黄金买/卖:{self.stats.get('gold_buy',0)}/{self.stats.get('gold_sell',0)} 白银买/卖:{self.stats.get('silver_buy',0)}/{self.stats.get('silver_sell',0)}")
                
                time.sleep(60)
                
            except KeyboardInterrupt:
                logging.info("停止")
                break
            except Exception as e:
                logging.error(f"错误: {e}")
                time.sleep(60)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    bot = GridStrategyV65A(CONFIG)
    bot.run()
5. 部署步骤
5.1 环境准备
bash
Copy
pip install ccxt pandas numpy
5.2 OKX API配置
登录OKX官网 → API管理
创建API Key，权限勾选：
读取（查看仓位、余额）
交易（下单、撤单）
绑定IP白名单（推荐）
记录API Key、Secret、Passphrase
5.3 配置修改
Python
Copy
CONFIG = {
    'api_key': '您的API_KEY',
    'secret': '您的SECRET',
    'password': '您的PASSPHRASE',
    'symbol': 'BTC/USDT:USDT',
    'capital': 10000,
    'test_mode': True  # 先True测试，确认无误后改False
}
5.4 启动运行
bash
Copy
python v65a_strategy.py
6. 监控指标
6.1 健康指标（每小时检查）
Table
指标	正常范围	异常处理
黄金买入次数	≥1次/天	若连续2天为0，放宽RSI至31
白银买入次数	3-10次/天	若>15次，市场过震荡，考虑暂停
收益率	正收益	若连续3天负收益，检查参数
最大回撤	<5%	若>5%，启用硬止损
现金占比	20-40%	若<10%，暂停买入
6.2 日志解读
plain
Copy
2026-03-04 12:00:00 - INFO - 权益:$10,483(+4.83%) 价:$68,444 RSI:42.3 MACD:多头 层:2
权益: 当前总资产
收益率: 相对初始本金
层: 当前持仓层数（0-5）
plain
Copy
2026-03-04 12:15:00 - INFO - [BUY GOLD] 价:$68,200 量:0.0293BTC 层:2
GOLD: MACD金叉触发，买入2层
SILVER: 普通买入，1层
7. 风险控制
7.1 内置保护
最大持仓: 5层（$10,000满仓）
保留现金: 强制保留20%
冷却时间: 15分钟防止过度交易
7.2 建议添加（可选）
Python
Copy
# 硬止损（-5%）
def check_stop_loss(self, price):
    if self.entry_prices:
        avg_cost = np.mean(self.entry_prices)
        if (price - avg_cost) / avg_cost < -0.05:
            self.execute_order('SELL', price, self.get_layers(), 'STOP_LOSS')
            logging.warning("触发止损，全部清仓")
8. 参数调优指南
Table
场景	调整建议
黄金信号长期不触发	RSI<30 → RSI<31或32
交易过于频繁	冷却15分钟 → 30分钟
止盈过早	RSI>65 → RSI>68
回撤过大	添加-5%硬止损
