import sys
import os
import numpy as np
from typing import List, Dict, Any, Optional

# --- 引入极轻量级的 ATS-20 协议核心，零 CTS1 依赖 ---
# 让 Agent 和任何三方系统都能无压力跑起本脚本
if "ats_core" not in sys.modules:
    # 临时把外层目录加入，方便独立测试
    ats_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    if ats_dir not in sys.path:
        sys.path.insert(0, ats_dir)
from ats_core import ATSStrategy, MarketDataDict, SignalDict

class Z71Indicators:
    """独立的指标算法类，不再依赖外部库如 ta-lib"""
    def __init__(self, rsi_period=20, boll_period=20, boll_std=2.0, macd_fast=12, macd_slow=26, macd_signal=9):
        self.rsi_period = rsi_period
        self.boll_period = boll_period
        self.boll_std = boll_std
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        
        self.closes = []
        self.bbw_history = []
        
        # 内置计算缓存
        self.last_rsi = 50.0
        self.last_macd = 0.0
        
    def update(self, close: float) -> dict:
        self.closes.append(close)
        if len(self.closes) > max(self.macd_slow + self.macd_signal, self.rsi_period, self.boll_period) + 50:
            self.closes = self.closes[-200:] # 保持轻量
            
        if len(self.closes) < self.macd_slow + self.macd_signal:
            return {}
            
        c_array = np.array(self.closes)
        
        # 简化版 RSI 均线算法
        diff = np.diff(c_array)
        up = np.maximum(diff, 0)
        down = np.abs(np.minimum(diff, 0))
        rs = np.mean(up[-self.rsi_period:]) / (np.mean(down[-self.rsi_period:]) + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        self.last_rsi = rsi
        
        # 简化版 BOLL
        b_slice = c_array[-self.boll_period:]
        mid = np.mean(b_slice)
        std = np.std(b_slice)
        upper = mid + self.boll_std * std
        lower = mid - self.boll_std * std
        bbw = (upper - lower) / mid
        self.bbw_history.append(bbw)
        if len(self.bbw_history) > 20:
            self.bbw_history.pop(0)
        bbw_ma20 = np.mean(self.bbw_history)
        
        # 简化版 MACD 动能 (非严谨 EMA，仅作趋势识别)
        fast_ma = np.mean(c_array[-self.macd_fast:])
        slow_ma = np.mean(c_array[-self.macd_slow:])
        macd_line = fast_ma - slow_ma
        self.last_macd = macd_line
        
        return {
            "rsi": rsi,
            "bbw": bbw,
            "bbw_ma20": bbw_ma20,
            "boll_mid": mid,
            "boll_upper": upper,
            "boll_lower": lower,
            "macd_hist": macd_line # 粗略动能
        }


class Zen71Strategy(ATSStrategy):
    """
    符合 ATS-20 标准的 Zen 7.1 并行网格共振策略
    不再依赖 `core.py`，全部数据交互依靠原生 Dictionary。
    """
    def __init__(self, name="zen-7-1", **params):
        super().__init__(name, **params)
        
        # 参数从 params kwargs 动态载入
        self.resample_min = params.get("resample_min", 60)
        self.capital = params.get("capital", 10000)
        self.grid_layers = params.get("grid_layers", 5)
        self.grid_drop_pct = params.get("grid_drop_pct", 0.02)
        self.hard_sl_pct = params.get("hard_sl_pct", -0.10)
        self.tp_min_profit_pct = params.get("tp_min_profit_pct", 0.03)
        self.symbol = params.get("symbol", "BTC-USDT-SWAP")
        
        self.indicators = Z71Indicators()
        
        # 简单的重采样器状态 (假设按 1m 喂入，60m 一切分)
        self.bar_counter = 0
        self.current_resample_close = 0.0
        
        # 网格状态 (因为是隔离的，这里先假设自己维护状态，或 Runner 通过 context 推入)
        self.layers = 0
        self.avg_cost = 0.0
        self.highest_close = 0.0

    def on_data(self, data: MarketDataDict, context: Dict[str, Any]) -> List[SignalDict]:
        """ATS-20 核心逻辑，纯 JSON IN / JSON OUT"""
        signals = []
        close = data["close"]
        
        self.bar_counter += 1
        is_resample_bar_completed = (self.bar_counter % self.resample_min == 0)
        
        # 更新指标
        inds = self.indicators.update(close)
        
        # (演示逻辑) 只有指标就位才计算
        if not inds:
            return signals

        # Context 中可以获取外部资金状态，这里为了演示直接覆盖自营变量
        # 实际 Agent 调用时，context 会包含：{"pnl_pct": -0.05, "layers_held": 2}
        pnl_pct = context.get("pnl_pct", 0.0)
        self.layers = context.get("layers", self.layers)
        self.avg_cost = context.get("avg_cost", self.avg_cost)

        # 1. 优先检查全局硬止损
        if self.layers > 0 and pnl_pct <= self.hard_sl_pct:
            return [{
                "skill_name": self.name,
                "symbol": data["symbol"],
                "side": "SELL",
                "type": "MARKET",
                "size": 1.0, # 全平
                "price": None,
                "rationale": f"Hard Stop Loss triggered at {pnl_pct*100:.2f}%"
            }]

        # 2. 检查止盈
        if self.layers > 0 and pnl_pct >= self.tp_min_profit_pct:
            # 大前提满足，检查动能衰竭
            if inds["rsi"] > 65 and close < self.highest_close:
                return [{
                    "skill_name": self.name,
                    "symbol": data["symbol"],
                    "side": "SELL",
                    "type": "MARKET",
                    "size": 1.0,
                    "price": None,
                    "rationale": "Dynamic Take Profit (RSI overbought, momentum exhausted)"
                }]
        
        self.highest_close = max(self.highest_close, close)

        # 3. 进场 / 网格补仓逻辑 (仅在重采样结束或特定极值检查)
        if is_resample_bar_completed:
            cond_resonance = (inds["bbw"] > inds["bbw_ma20"]) and (close > inds["boll_mid"]) and (inds["macd_hist"] > 0)
            
            # 首仓
            if self.layers == 0 and cond_resonance:
                base_trade_amount = self.capital / (self.grid_layers + 1)
                signals.append({
                    "skill_name": self.name,
                    "symbol": data["symbol"],
                    "side": "BUY",
                    "type": "MARKET",
                    "size": base_trade_amount,
                    "price": None,
                    "rationale": "Resonance Base Buy"
                })
                self.layers = 1
                self.avg_cost = close
                self.highest_close = close
            
            # 网格摊薄
            elif 0 < self.layers < self.grid_layers:
                if close <= self.avg_cost * (1 - self.grid_drop_pct):
                    base_trade_amount = self.capital / (self.grid_layers + 1)
                    signals.append({
                        "skill_name": self.name,
                        "symbol": data["symbol"],
                        "side": "BUY",
                        "type": "MARKET",
                        "size": base_trade_amount,
                        "price": None,
                        "rationale": f"Grid layer {self.layers+1} averaged down"
                    })
                    # 这里只是在 Agent 独立测试时的本地状态步进，实盘应监听 on_event 修正
                    total_value = self.avg_cost * self.layers + close * 1
                    self.layers += 1
                    self.avg_cost = total_value / self.layers

        return signals

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "layers": self.layers,
            "avg_cost": self.avg_cost,
            "rsi": self.indicators.last_rsi
        }
