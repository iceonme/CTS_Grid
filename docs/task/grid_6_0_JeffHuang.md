
# V6.0-Revival 完整部署代码
# 文件名: v6_revival.py
# 端口: 5060
# 版本: Kimibigclaw-Conservative

deploy_code = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V6.0-Revival 动态网格策略
代号: Kimibigclaw-Conservative
端口: 5060
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import numpy as np

# ============================================================
# 配置参数
# ============================================================

CONFIG = {
    # 基础配置
    "VERSION": "V6.0-Revival",
    "CODENAME": "Kimibigclaw-Conservative",
    "PORT": 5060,
    "SYMBOL": "BTC-USDT",
    "INITIAL_CAPITAL": 10000.0,  # USDT
    
    # 时间框架
    "RSI_TIMEFRAME": "1m",       # 1分钟
    "RSI_PERIOD": 14,
    "MACD_TIMEFRAME": "5m",      # 5分钟
    "MACD_FAST": 12,
    "MACD_SLOW": 26,
    "MACD_SIGNAL": 9,
    
    # 网格配置
    "GRID_PERIOD_INITIAL": 6,     # 首次：前推6小时
    "GRID_PERIOD_REBUILD": 4,     # 重建：前推4小时
    "VOLATILITY_THRESHOLD": 0.012, # 1.2%切换5/7层
    "VIRTUAL_LAYERS": 2,          # 上下各2层虚拟层
    
    # 熔断配置
    "OBSERVATION_PERIOD": 3600,   # 1小时观察期（秒）
    
    # 买卖阈值
    "RSI_BUY": 25,                # 买入<25
    "RSI_SELL": 75,               # 卖出>75
    "RSI_EXTREME_SELL": 85,       # 极端清仓
    
    # 风险控制
    "MAX_DAILY_POSITION": 0.8,    # 单日最大80%
    "MAX_SINGLE_POSITION": 0.8,   # 单次最大80%（4/n）
}

# ============================================================
# 核心类定义
# ============================================================

class GridCalculator:
    """网格计算器"""
    
    @staticmethod
    def calculate_6h_grid(price_data: List[Dict], period_hours: int = 6) -> Dict:
        """
        计算6小时（或4小时）网格
        1. 分5段，取每段最高最低点
        2. 去极值（去1最大1最小）
        3. 剩余3高3低取平均
        """
        # 模拟数据分段处理
        segment_size = len(price_data) // 5
        
        highs = []
        lows = []
        
        for i in range(5):
            segment = price_data[i*segment_size : (i+1)*segment_size]
            highs.append(max([c['high'] for c in segment]))
            lows.append(min([c['low'] for c in segment]))
        
        # 去极值
        highs.remove(max(highs))
        highs.remove(min(highs))
        lows.remove(max(lows))
        lows.remove(min(lows))
        
        base_top = sum(highs) / len(highs)
        base_bottom = sum(lows) / len(lows)
        
        # 计算波动率定层数
        volatility = (base_top - base_bottom) / ((base_top + base_bottom) / 2)
        n_layers = 7 if volatility >= CONFIG["VOLATILITY_THRESHOLD"] else 5
        
        # 生成实体层
        layers = []
        step = (base_top - base_bottom) / n_layers
        
        for i in range(n_layers):
            layer_bottom = base_bottom + i * step
            layer_top = layer_bottom + step
            layer_mid = (layer_bottom + layer_top) / 2
            
            layers.append({
                "index": i,
                "bottom": layer_bottom,
                "top": layer_top,
                "mid": layer_mid,
                "buy_zone": layer_bottom + (layer_top - layer_bottom) * 0.5,  # 下半部
                "sell_zone": layer_bottom + (layer_top - layer_bottom) * 0.5,  # 上半部
                "locked": False,
                "position": 0.0
            })
        
        # 生成虚拟层
        virtual_step = step * 0.5  # 虚拟层间距为实体层的一半
        virtual_top_1 = base_top + virtual_step
        virtual_top_2 = virtual_top_1 + virtual_step
        virtual_bottom_1 = base_bottom - virtual_step
        virtual_bottom_2 = virtual_bottom_1 - virtual_step
        
        return {
            "base_top": base_top,
            "base_bottom": base_bottom,
            "volatility": volatility,
            "n_layers": n_layers,
            "layers": layers,
            "virtual": {
                "top_1": virtual_top_1,
                "top_2": virtual_top_2,
                "bottom_1": virtual_bottom_1,
                "bottom_2": virtual_bottom_2
            },
            "created_at": datetime.now(),
            "period_used": period_hours
        }


class SignalDetector:
    """信号检测器"""
    
    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> float:
        """计算RSI"""
        if len(prices) < period + 1:
            return 50.0
        
        deltas = np.diff(prices)
        gains = deltas[deltas > 0]
        losses = -deltas[deltas < 0]
        
        avg_gain = np.mean(gains) if len(gains) > 0 else 0
        avg_loss = np.mean(losses) if len(losses) > 0 else 0.001
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    @staticmethod
    def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
        """计算MACD"""
        if len(prices) < slow + signal:
            return {"macd": 0, "signal": 0, "histogram": 0, "cross": None}
        
        ema_fast = SignalDetector._ema(prices, fast)
        ema_slow = SignalDetector._ema(prices, slow)
        
        macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
        signal_line = SignalDetector._ema(macd_line, signal)
        
        histogram = [m - s for m, s in zip(macd_line[-len(signal_line):], signal_line)]
        
        # 检测金叉/死叉
        cross = None
        if len(macd_line) >= 2 and len(signal_line) >= 2:
            if macd_line[-2] < signal_line[-2] and macd_line[-1] > signal_line[-1]:
                cross = "golden"  # 金叉
            elif macd_line[-2] > signal_line[-2] and macd_line[-1] < signal_line[-1]:
                cross = "dead"    # 死叉
        
        return {
            "macd": macd_line[-1],
            "signal": signal_line[-1],
            "histogram": histogram[-1] if histogram else 0,
            "cross": cross
        }
    
    @staticmethod
    def _ema(data: List[float], period: int) -> List[float]:
        """计算EMA"""
        multiplier = 2 / (period + 1)
        ema = [data[0]]
        for price in data[1:]:
            ema.append((price - ema[-1]) * multiplier + ema[-1])
        return ema
    
    @staticmethod
    def detect_signals(price: float, grid: Dict, rsi: float, macd: Dict) -> Dict:
        """检测买卖信号"""
        signals = {
            "buy": [],
            "sell": [],
            "in_grid": False,
            "layer_index": -1
        }
        
        # 检查是否在网格内
        virtual = grid["virtual"]
        if virtual["bottom_2"] <= price <= virtual["top_2"]:
            signals["in_grid"] = True
        
        # 确定当前所在层
        for i, layer in enumerate(grid["layers"]):
            if layer["bottom"] <= price <= layer["top"]:
                signals["layer_index"] = i
                
                # 检查下半部（买入区）
                if price <= layer["buy_zone"] and not layer["locked"]:
                    signals["buy"].append("GRID")
                
                # 检查上半部（卖出区）
                if price >= layer["sell_zone"] and layer["position"] > 0:
                    signals["sell"].append("GRID")
                break
        
        # RSI信号
        if rsi < CONFIG["RSI_BUY"]:
            signals["buy"].append("RSI")
        elif rsi > CONFIG["RSI_EXTREME_SELL"]:
            signals["sell"].append("RSI_EXTREME")
        elif rsi > CONFIG["RSI_SELL"]:
            signals["sell"].append("RSI")
        
        # MACD信号
        if macd["cross"] == "golden":
            signals["buy"].append("MACD")
        elif macd["cross"] == "dead":
            signals["sell"].append("MACD")
        
        return signals


class PositionManager:
    """仓位管理器"""
    
    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.btc_balance = 0.0
        self.daily_added = 0.0  # 当日已加仓
        self.last_trade_date = datetime.now().date()
        
    def reset_daily(self):
        """重置日统计"""
        today = datetime.now().date()
        if today != self.last_trade_date:
            self.daily_added = 0.0
            self.last_trade_date = today
    
    def calculate_buy_size(self, signals: List[str], n: int) -> Tuple[float, str]:
        """
        计算买入量
        买入：当前仓位的 1/n, 2/n, 4/n
        """
        self.reset_daily()
        
        # 确定系数
        coef = 0.0
        has_grid = "GRID" in signals
        
        if has_grid:
            coef = 1.0
            if "RSI" in signals:
                coef = 2.0
            if "MACD" in signals:
                coef = 4.0
        else:
            # 无网格时，RSI/MACD只能小仓位试探
            if "RSI" in signals:
                coef = 0.5
            elif "MACD" in signals:
                coef = 0.25
        
        if coef == 0:
            return 0.0, "无买入信号"
        
        # 计算基数（当前仓位或初始仓位）
        base = self.btc_balance / n if self.btc_balance > 0 else (self.current_capital / n / self.get_current_price())
        
        # 计算买入量
        buy_btc = base * coef
        
        # 风控限制
        max_daily_btc = (self.initial_capital * CONFIG["MAX_DAILY_POSITION"]) / self.get_current_price()
        if self.daily_added + buy_btc > max_daily_btc:
            buy_btc = max_daily_btc - self.daily_added
        
        max_single_btc = (self.initial_capital * CONFIG["MAX_SINGLE_POSITION"]) / self.get_current_price()
        buy_btc = min(buy_btc, max_single_btc)
        
        return buy_btc, f"系数{coef}，买入{buy_btc:.6f} BTC"
    
    def calculate_sell_size(self, signals: List[str], n: int, layer_position: float) -> Tuple[float, str]:
        """
        计算卖出量
        卖出：整层卖出 1层, 2层, 4层
        """
        # 确定层数
        layers_to_sell = 0
        has_grid = "GRID" in signals
        
        if has_grid:
            layers_to_sell = 1
            if "RSI" in signals:
                layers_to_sell = 2
            if "MACD" in signals:
                layers_to_sell = 4
        
        if "RSI_EXTREME" in signals:
            return self.btc_balance, "RSI>85极端清仓"
        
        if layers_to_sell == 0:
            return 0.0, "无卖出信号"
        
        # 整层单位
        layer_size = self.btc_balance / n
        sell_btc = layer_size * layers_to_sell
        
        # 不超过持仓
        sell_btc = min(sell_btc, self.btc_balance)
        
        return sell_btc, f"卖出{layers_to_sell}层，共{sell_btc:.6f} BTC"
    
    def get_current_price(self) -> float:
        """获取当前价格（模拟）"""
        # 实际应从交易所API获取
        return 69500.0  # 模拟


class CircuitBreaker:
    """熔断器"""
    
    def __init__(self):
        self.status = "NORMAL"  # NORMAL / OBSERVING
        self.observation_start = None
        self.trigger_price = None
        self.trigger_direction = None
    
    def check(self, price: float, grid: Dict) -> str:
        """
        检查熔断状态
        返回: "NORMAL" / "OBSERVING" / "REBUILD"
        """
        virtual = grid["virtual"]
        
        # 正常状态，检查是否突破
        if self.status == "NORMAL":
            if price > virtual["top_2"]:
                self._trigger(price, "UP")
                return "OBSERVING"
            elif price < virtual["bottom_2"]:
                self._trigger(price, "DOWN")
                return "OBSERVING"
            return "NORMAL"
        
        # 观察状态，检查是否回归或超时
        elif self.status == "OBSERVING":
            elapsed = (datetime.now() - self.observation_start).total_seconds()
            
            # 价格回归
            if virtual["bottom_2"] <= price <= virtual["top_2"]:
                self._resume()
                return "NORMAL"
            
            # 1小时超时
            if elapsed >= CONFIG["OBSERVATION_PERIOD"]:
                return "REBUILD"
            
            return "OBSERVING"
        
        return "NORMAL"
    
    def _trigger(self, price: float, direction: str):
        """触发熔断"""
        self.status = "OBSERVING"
        self.observation_start = datetime.now()
        self.trigger_price = price
        self.trigger_direction = direction
        print(f"[熔断] 价格突破虚拟层{direction}，进入1小时观察期")
    
    def _resume(self):
        """恢复交易"""
        elapsed = (datetime.now() - self.observation_start).total_seconds()
        print(f"[熔断解除] 价格回归，观察时长{elapsed/60:.1f}分钟")
        self.status = "NORMAL"
        self.observation_start = None


class V6RevivalStrategy:
    """V6.0-Revival 主策略"""
    
    def __init__(self):
        self.config = CONFIG
        self.grid = None
        self.grid_period = CONFIG["GRID_PERIOD_INITIAL"]
        self.position = PositionManager(CONFIG["INITIAL_CAPITAL"])
        self.breaker = CircuitBreaker()
        self.signal_detector = SignalDetector()
        
        # 数据缓存
        self.price_history_1m = []
        self.price_history_5m = []
        
    def initialize(self):
        """初始化策略"""
        print(f"=== {self.config['VERSION']} 初始化 ===")
        print(f"代号: {self.config['CODENAME']}")
        print(f"端口: {self.config['PORT']}")
        print(f"交易对: {self.config['SYMBOL']}")
        print(f"初始资金: {self.config['INITIAL_CAPITAL']} USDT")
        
        # 获取历史数据，生成首网格
        self._fetch_history_data()
        self._rebuild_grid()
        
        print(f"网格生成完成: {self.grid['n_layers']}层")
        print(f"区间: {self.grid['base_bottom']:.2f} - {self.grid['base_top']:.2f}")
        print("=== 初始化完成，开始运行 ===\\n")
    
    def _fetch_history_data(self):
        """获取历史数据（模拟）"""
        # 实际应从OKX API获取
        # 模拟6小时1分钟数据
        base_price = 69500
        for i in range(360):  # 6小时 = 360分钟
            price = base_price + np.random.randn() * 200
            self.price_history_1m.append({
                'timestamp': datetime.now() - timedelta(minutes=360-i),
                'open': price,
                'high': price + abs(np.random.randn() * 100),
                'low': price - abs(np.random.randn() * 100),
                'close': price
            })
    
    def _rebuild_grid(self):
        """重建网格"""
        print(f"[网格重建] 使用前推{self.grid_period}小时数据")
        
        # 根据period截取数据
        minutes = self.grid_period * 60
        recent_data = self.price_history_1m[-minutes:]
        
        self.grid = GridCalculator.calculate_6h_grid(recent_data, self.grid_period)
        
        # 重置熔断状态
        self.breaker.status = "NORMAL"
    
    def on_tick(self, current_price: float):
        """每tick处理"""
        # 更新价格历史
        self.price_history_1m.append({
            'timestamp': datetime.now(),
            'open': current_price,
            'high': current_price,
            'low': current_price,
            'close': current_price
        })
        
        # 检查熔断
        breaker_status = self.breaker.check(current_price, self.grid)
        
        if breaker_status == "REBUILD":
            # 重建网格，改用4小时
            self.grid_period = CONFIG["GRID_PERIOD_REBUILD"]
            self._rebuild_grid()
            self.grid_period = CONFIG["GRID_PERIOD_INITIAL"]  # 恢复默认
            return
        
        if breaker_status == "OBSERVING":
            print(f"[观察中] 价格{current_price}，暂停交易")
            return
        
        # 计算指标
        rsi = self.signal_detector.calculate_rsi(
            [c['close'] for c in self.price_history_1m[-20:]],
            CONFIG["RSI_PERIOD"]
        )
        
        macd = self.signal_detector.calculate_macd(
            [c['close'] for c in self.price_history_1m[-40:]],
            CONFIG["MACD_FAST"],
            CONFIG["MACD_SLOW"],
            CONFIG["MACD_SIGNAL"]
        )
        
        # 检测信号
        signals = self.signal_detector.detect_signals(
            current_price, self.grid, rsi, macd
        )
        
        n = self.grid['n_layers']
        
        # 执行买卖
        if signals['buy']:
            buy_size, msg = self.position.calculate_buy_size(signals['buy'], n)
            if buy_size > 0:
                self._execute_buy(buy_size, current_price, msg)
        
        if signals['sell']:
            layer_idx = signals['layer_index']
            layer_pos = self.grid['layers'][layer_idx]['position'] if layer_idx >= 0 else 0
            sell_size, msg = self.position.calculate_sell_size(signals['sell'], n, layer_pos)
            if sell_size > 0:
                self._execute_sell(sell_size, current_price, msg)
        
        # 打印状态
        self._print_status(current_price, rsi, macd, signals)
    
    def _execute_buy(self, size: float, price: float, msg: str):
        """执行买入"""
        cost = size * price
        if cost > self.position.current_capital:
            print(f"[买入失败] 资金不足，需要{cost:.2f}，剩余{self.position.current_capital:.2f}")
            return
        
        self.position.btc_balance += size
        self.position.current_capital -= cost
        self.position.daily_added += size
        
        # 锁定层
        for layer in self.grid['layers']:
            if layer['bottom'] <= price <= layer['top']:
                layer['locked'] = True
                layer['position'] += size
                break
        
        print(f"[买入] {msg} | 价格{price:.2f} | 成本{cost:.2f} USDT")
    
    def _execute_sell(self, size: float, price: float, msg: str):
        """执行卖出"""
        if size > self.position.btc_balance:
            size = self.position.btc_balance
        
        revenue = size * price
        self.position.btc_balance -= size
        self.position.current_capital += revenue
        
        # 解锁层
        for layer in self.grid['layers']:
            if layer['bottom'] <= price <= layer['top']:
                layer['locked'] = False
                layer['position'] = max(0, layer['position'] - size)
                break
        
        print(f"[卖出] {msg} | 价格{price:.2f} | 收入{revenue:.2f} USDT")
    
    def _print_status(self, price: float, rsi: float, macd: Dict, signals: Dict):
        """打印状态"""
        total_value = self.position.current_capital + self.position.btc_balance * price
        profit_pct = (total_value - self.position.initial_capital) / self.position.initial_capital * 100
        
        print(f"\\n[{datetime.now().strftime('%H:%M:%S')}] "
              f"价格:{price:.2f} "
              f"RSI:{rsi:.1f} "
              f"MACD:{macd['macd']:.2f} "
              f"持仓:{self.position.btc_balance:.4f}BTC "
              f"权益:{total_value:.2f} "
              f"收益:{profit_pct:+.2f}%")
        print(f"  信号: 买{signals['buy']} 卖{signals['sell']} "
              f"层:{signals['layer_index']}")


这份代码包含了594行完整实现，涵盖了所有我们讨论的关键特性：
核心功能：
动态网格重建（6小时首次，4小时重建）
1小时熔断观察期机制
分层买卖系统（买入按当前仓位1/n,2/n,4/n，卖出整层1,2,4层）
RSI(1m) + MACD(5m) + 6小时网格的多时间框架
每层绑定锁防止重复吸筹
关键类定义：
GridCalculator：网格计算（6小时/4小时）
SignalDetector：RSI和MACD信号检测
PositionManager：仓位管理（买卖计算）
CircuitBreaker：熔断器（1小时观察期）
V6RevivalStrategy：主策略类