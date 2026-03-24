#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V9.3-Innovation - ETH永续合约动态网格策略
版本: 2025-03-22 (创新版)
端口: 5090

核心创新:
- 3层网格架构: 实体3层(低/中/高) + 虚拟2层(极值缓冲)
- 动态RSI阈值: 基于波动率自适应调整
- 网格归并: 顺势归并保留敞口，逆势止损
- 无网格模式: 网格失效时RSI极值直接交易
- 动态杠杆: 1x-3x (基于ATR自适应)
- 双向交易: 做多(中层下半部) + 做空(低层上半部)
"""

import os
import json
import time
import hmac
import hashlib
import base64
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Optional, Any
import logging
import sys

# 导入系统组件
from .base import BaseStrategy
from core.types import Signal, MarketData, StrategyContext, Side, OrderType
from dashboard.server import create_dashboard

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('v93_innovation_5090.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('V9.3-Innovation')

class OKXAPI:
    """OKX API 封装"""
    
    def __init__(self, config: Dict):
        self.api_key = config['api_key']
        self.api_secret = config['api_secret']
        self.passphrase = config['passphrase']
        self.base_url = "https://www.okx.com"
        self.testnet = config.get('testnet', True)
        
        if self.testnet:
            self.base_url = "https://www.okx.com"
            
        self.symbol = config.get('symbol', 'ETH-USDT-SWAP')
        
    def _sign(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """生成签名"""
        message = timestamp + method.upper() + request_path + body
        mac = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode('utf-8')
    
    def _request(self, method: str, path: str, body: Dict = None) -> Dict:
        """发送请求并带有重试机制"""
        max_retries = 3
        for i in range(max_retries):
            timestamp = datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'
            body_json = json.dumps(body) if body else ""
            
            headers = {
                'OK-ACCESS-KEY': self.api_key,
                'OK-ACCESS-SIGN': self._sign(timestamp, method, path, body_json),
                'OK-ACCESS-TIMESTAMP': timestamp,
                'OK-ACCESS-PASSPHRASE': self.passphrase,
                'Content-Type': 'application/json'
            }
            
            if self.testnet:
                headers['x-simulated-trading'] = '1'
            
            url = self.base_url + path
            try:
                if method.upper() == 'GET':
                    response = requests.get(url, headers=headers, timeout=10)
                else:
                    response = requests.post(url, headers=headers, data=body_json, timeout=10)
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(f"API请求状态码异常 ({response.status_code}): {response.text} | 重试 {i+1}/{max_retries}")
                    time.sleep(1)
            except Exception as e:
                logger.error(f"API请求异常: {e} | 重试 {i+1}/{max_retries}")
                time.sleep(1)
        
        return {'code': '-1', 'msg': 'Max retries exceeded'}
    
    def get_ticker(self) -> Dict:
        """获取最新价格"""
        path = f"/api/v5/market/ticker?instId={self.symbol}"
        return self._request('GET', path)
    
    def get_candles(self, bar: str = "1m", limit: int = 100) -> pd.DataFrame:
        """获取K线数据, 支持超过100个的分页查询"""
        all_data = []
        last_ts = ""
        
        # 核心逻辑：分批获取，通过 history-candles 翻页
        remaining = limit
        while remaining > 0:
            current_limit = min(remaining, 100)
            if not last_ts:
                # 第一次：获取最新数据
                path = f"/api/v5/market/candles?instId={self.symbol}&bar={bar}&limit={current_limit}"
            else:
                # 后续：获取旧数据
                path = f"/api/v5/market/history-candles?instId={self.symbol}&bar={bar}&after={last_ts}&limit={current_limit}"
                
            data = self._request('GET', path)
            if data.get('code') == '0' and data.get('data'):
                batch = data['data']
                all_data.extend(batch)
                if len(batch) < current_limit:
                    break
                last_ts = batch[-1][0] # 最后一个点的时间戳用于翻页
                remaining -= len(batch)
            else:
                break
            
        if all_data:
            df = pd.DataFrame(all_data, columns=[
                'ts', 'open', 'high', 'low', 'close', 'vol', 'volCcy', 'volCcyQuote', 'confirm'
            ])
            df['ts'] = pd.to_datetime(df['ts'].astype(float), unit='ms', utc=True)
            df.set_index('ts', inplace=True)
            df = df.astype(float)
            # OKX 返回的是从新到旧，需要排序
            return df.sort_index()
            
        return pd.DataFrame()
    
    def get_position(self) -> Dict:
        """获取持仓"""
        path = f"/api/v5/account/positions?instId={self.symbol}"
        return self._request('GET', path)
    
    def place_order(self, side: str, sz: float, px: float = None, 
                   ord_type: str = "market", td_mode: str = "cross") -> Dict:
        """下单"""
        body = {
            "instId": self.symbol,
            "tdMode": td_mode,
            "side": side,
            "ordType": ord_type,
            "sz": str(sz)
        }
        if px and ord_type == "limit":
            body["px"] = str(px)
            
        return self._request('POST', '/api/v5/trade/order', body)
    
    def close_position(self, pos_side: str = None) -> Dict:
        """平仓"""
        body = {
            "instId": self.symbol,
            "mgnMode": "cross",
            "autoCxl": True
        }
        if pos_side:
            body["posSide"] = pos_side
        return self._request('POST', '/api/v5/trade/close-position', body)
    
    def set_leverage(self, lever: float, mgn_mode: str = "cross") -> Dict:
        """设置杠杆"""
        body = {
            "instId": self.symbol,
            "lever": str(lever),
            "mgnMode": mgn_mode
        }
        return self._request('POST', '/api/v5/account/set-leverage', body)


class V93Strategy(BaseStrategy):
    """V9.3-Innovation 策略核心 - 3层网格+动态RSI+网格归并"""
    
    def __init__(self, config: Dict = None, **kwargs):
        # 统一配置处理
        self.config = config or kwargs
        super().__init__(name="V9.3-Innovation-v1.1", **self.config)
        
        self.name = "V9.3-Innovation-v1.1" # 特色暗号：3实体2虚拟 360热身版
        self.symbol = self.config.get('symbol', 'ETH-USDT-SWAP')
        self.last_run_time = None
        
        # 处理 OKX API (仅在 Standalone 模式下需要，即 config 中包含 API 密钥时)
        self.api = None
        okx_config = self.config.get('okx', self.config)
        if isinstance(okx_config, dict) and 'api_key' in okx_config:
            self.api = OKXAPI(okx_config)
            logger.info("API 模块初始化成功 (Standalone 模式)")
        else:
            logger.info("API 模块未初始化 (Engine 模式)")
        
        # 初始化 Dashboard Server (仅在 Standalone 模式且未禁用时)
        self.server = None
        if self.config.get('standalone', False) or (self.api is not None and self.config.get('port')):
            port = self.config.get('port', 5090)
            self.server = create_dashboard(port=port)
            self.server.version = "Innovation-v1.1"
            logger.info(f"Dashboard Server 初始化成功 | 端口: {port}")
        else:
            logger.info("Dashboard Server 跳过初始化 (由外部引擎管理)")
        
        # 网格状态 - 3层实体 + 2层虚拟
        self.entity_grids: List[float] = []  # 3层实体: [低, 中, 高]
        self.virtual_grids: List[float] = []  # 2层虚拟: [极低, 极高]
        self.grid_top = 0.0
        self.grid_bottom = 0.0
        self.grid_middle = 0.0
        
        # 动态RSI阈值
        self.rsi_oversold = 25.0        # 做多入场
        self.rsi_overbought = 85.0      # 做空入场
        self.rsi_exit_oversold = 40.0   # 平空
        self.rsi_exit_overbought = 70.0 # 平多
        
        # 网格归并状态
        self.merged_grid_level: Optional[int] = None  # 归并后的网格层级
        self.position_entry_price: float = 0.0  # 入场价格
        self.position_direction: int = 0  # 1=多, -1=空, 0=无
        
        # 运行时状态
        self.last_reset_day: Optional[datetime.date] = None
        self.breakout_triggered = False
        self.breakout_time: Optional[datetime] = None
        self.current_leverage = self.config.get('leverage_base', 2.0)
        self.positions_snapshot: Dict[str, Any] = {}
        
        # 数据缓存
        self.price_history: List[float] = []
        self.df_history: pd.DataFrame = pd.DataFrame()
        
        # 统计
        self.trade_count = 0
        self.daily_reset_count = 0
        self.breakout_reset_count = 0
        
        # 网格计算记录（仅记录最近一次计算时间，不做定时强制重置）
        self.last_grid_calc_time: Optional[datetime] = None
        
        # 稳定性增强
        self.last_candle_ts: Optional[datetime] = None
        self.last_trade_time: float = 0.0 # 上次交易时间戳
        self.cooldown_seconds = 60 # 60秒冷却
        
        # 状态数据，用于 get_status
        self.status_data: Dict[str, Any] = {}
        
        # 尝试加载历史网格状态
        self._load_grid_state()
        
        logger.info(f"V9.3-Innovation 初始化完成 | 端口: {self.config.get('port', 5090)}")

    def on_start(self):
        """引擎启动时调用"""
        logger.info(f"策略 {self.name} 已启动")

    def _update_buffer(self, data: MarketData):
        """更新内部数据缓存 (对齐分钟级别，避免盘中抖动)"""
        # 如果是同分钟的数据，替换最后一个点；如果是新分钟，追加点
        if self.last_candle_ts == data.timestamp:
            if self.price_history:
                self.price_history[-1] = data.close
        else:
            self.price_history.append(data.close)
            self.last_candle_ts = data.timestamp
            
        if len(self.price_history) > 400:
            self.price_history = self.price_history[-400:]
            
        # 维护 DataFrame 用于 ATR 计算等 (同理对齐)
        if not self.df_history.empty and self.df_history.index[-1] == data.timestamp:
            self.df_history.iloc[-1] = [data.open, data.high, data.low, data.close, data.volume]
        else:
            new_row = pd.DataFrame([{
                'open': data.open, 'high': data.high, 
                'low': data.low, 'close': data.close, 'vol': data.volume
            }], index=[data.timestamp])
            self.df_history = pd.concat([self.df_history, new_row]).tail(400)

    def on_data(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        """分层架构核心：处理每一根K线并返回信号"""
        # 1. 更新缓存
        self._update_buffer(data)
        
        if len(self.df_history) < 20:
            return []
            
        current_price = data.close
        current_time = data.timestamp
        signals = []
        
        # 2. 计算指标
        rsi = self.calculate_rsi(self.price_history)
        atr = self.calculate_atr(self.df_history)
        trend = self.lstm_trend(self.price_history)
        
        # 3. 动态RSI阈值 (基于趋势强度)
        self._update_dynamic_rsi_thresholds(atr, current_price, trend)
        
        # 4. 动态杠杆 (通过 context 传递给引擎)
        self.calculate_dynamic_leverage_for_engine(atr, current_price, context)
        
        # 5. 初始化或重置网格
        reset_needed, reset_window = self.check_reset_conditions(current_price, current_time)
        if not self.entity_grids or reset_needed:
            # 用户要求重置时持仓保留原样，此处原有的 _handle_grid_merge 逻辑跳过或仅做记录
            if context.positions:
                logger.info(f"网格重置触发 | 当前持仓数量: {len(context.positions)} | 状态: 保留原样")
            
            # 执行网格计算 (自适应 6h 或 4h 窗口)
            self.calculate_grids(self.df_history, window_hours=reset_window)
            
        # 5.1 交易冷却检查
        time_now = time.time()
        if time_now - self.last_trade_time < self.cooldown_seconds:
             # 在冷却期内，跳过交易逻辑，仅更新状态
             self._update_status_only(rsi, current_price, trend)
             return []
            
        # 6. 获取当前层 (3层实体架构)
        layer = self.get_current_layer(current_price)
        
        # 7. 获取持仓状态 (从 context)
        has_long = False
        has_short = False
        for symbol, pos in context.positions.items():
            if symbol == self.symbol:
                if pos.size > 0: has_long = True
                if pos.size < 0: has_short = True
        
        # 8. 交易逻辑 - 3层网格 + 无网格模式
        # 8.1 无网格模式：在此定义为完全超出虚拟层或网格失效时
        if layer is None:
            signals.extend(self._no_grid_trading(rsi, has_long, has_short, current_price, current_time, trend, context))
        else:
            # 8.2 正常网格交易 (包含实体层与虚拟层)
            signals.extend(self._grid_trading(layer, rsi, has_long, has_short, current_price, current_time, trend, context))
                
        # 更新状态并记录冷却时间（如果有信号）
        if signals:
            self.last_trade_time = time_now
            
        self._update_status_only(rsi, current_price, trend, layer)
        return signals
    
    def _update_status_only(self, rsi, current_price, trend, layer=None):
        """仅更新状态数据"""
        self.last_rsi = rsi
        self.last_layer = layer if layer is not None else -1
        self.last_trend = trend
        
        self.status_data = {
            'rsi': rsi,
            'layer': layer,
            'trend': trend,
            'current_price': current_price
        }
        
        # 降低非信号状态的日志频率 (可选)
        logger.info(f"状态 | 价格: {current_price:.2f} | 层: {layer if layer is not None else 'N/A'} | "
                   f"RSI: {rsi:.1f} | 阈值: 入{self.rsi_oversold:.0f}/{self.rsi_overbought:.0f} 出{self.rsi_exit_oversold:.0f}/{self.rsi_exit_overbought:.0f} | "
                   f"杠杆: {self.current_leverage}x | 趋势: {trend} | "
                   f"重置: 日{self.daily_reset_count}/突{self.breakout_reset_count}")
    
    def _update_dynamic_rsi_thresholds(self, atr: float, price: float, trend: int):
        """动态RSI阈值：基于趋势强度调整
        
        弱趋势: 25/40/70/85 (更宽松，提高入场)
        强趋势: 30/45/65/80 (放宽止盈，让利润奔跑)
        """
        if abs(trend) >= 1:  # 强趋势
            self.rsi_oversold = 30.0      # 做多入场
            self.rsi_overbought = 80.0    # 做空入场
            self.rsi_exit_oversold = 45.0   # 平空
            self.rsi_exit_overbought = 65.0 # 平多
        else:  # 弱趋势/震荡
            self.rsi_oversold = 25.0      # 做多入场 (更宽松)
            self.rsi_overbought = 85.0    # 做空入场 (更宽松)
            self.rsi_exit_oversold = 40.0   # 平空 (更宽松)
            self.rsi_exit_overbought = 70.0 # 平多 (更宽松)
    
    def _handle_grid_merge(self, context: StrategyContext, current_price: float, trend: int) -> List[Signal]:
        """网格归并：顺势归并保留敞口，逆势止损"""
        signals = []
        
        for symbol, pos in context.positions.items():
            if pos.size == 0:
                continue
                
            is_long = pos.size > 0
            entry_price = pos.avg_price if hasattr(pos, 'avg_price') else current_price
            
            # 顺势归并：多+涨→归并，空+跌→归并
            if is_long and trend == 1 and current_price > entry_price:
                # 顺势做多，保留仓位，更新入场价为当前网格层
                self.position_direction = 1
                self.position_entry_price = current_price
                logger.info(f"网格归并(顺势) | 多仓保留 | 入场价更新: {entry_price:.2f} -> {current_price:.2f}")
                continue
            elif not is_long and trend == -1 and current_price < entry_price:
                # 顺势做空，保留仓位
                self.position_direction = -1
                self.position_entry_price = current_price
                logger.info(f"网格归并(顺势) | 空仓保留 | 入场价更新: {entry_price:.2f} -> {current_price:.2f}")
                continue
            else:
                # 逆势止损：多+跌或空+涨→平仓
                side = Side.SELL if is_long else Side.BUY
                signals.append(Signal(
                    symbol=symbol, side=side, size=abs(pos.size),
                    price=current_price, timestamp=datetime.now(timezone.utc),
                    meta={'reason': 'grid_merge_stop_loss', 'posSide': 'long' if is_long else 'short'}
                ))
                self.position_direction = 0
                logger.info(f"网格归并(逆势) | {'多' if is_long else '空'}仓止损 | 价格: {current_price:.2f}")
        
        return signals
    
    def _no_grid_trading(self, rsi: float, has_long: bool, has_short: bool, 
                         current_price: float, current_time: datetime, trend: int,
                         context: StrategyContext) -> List[Signal]:
        """无网格模式：网格失效时RSI极值直接交易"""
        signals = []
        
        # 1. 入场逻辑
        # RSI超卖 + 无多仓 → 做多
        if rsi <= self.rsi_oversold and not has_long:
            size = 0.2 * self.current_leverage
            if trend == 1:
                size = min(size * 2, 0.4 * self.current_leverage)
            
            signals.append(Signal(
                symbol=self.symbol, side=Side.BUY, size=size,
                price=current_price, timestamp=current_time,
                meta={'reason': 'no_grid_oversold', 'posSide': 'long'}
            ))
            logger.info(f"无网格交易 | RSI超卖做多 | RSI: {rsi:.1f}")
        
        # RSI超买 + 无空仓 → 做空
        elif rsi >= self.rsi_overbought and not has_short:
            size = 0.2 * self.current_leverage
            if trend == -1:
                size = min(size * 2, 0.4 * self.current_leverage)
            
            signals.append(Signal(
                symbol=self.symbol, side=Side.SELL, size=size,
                price=current_price, timestamp=current_time,
                meta={'reason': 'no_grid_overbought', 'posSide': 'short'}
            ))
            logger.info(f"无网格交易 | RSI超买做空 | RSI: {rsi:.1f}")
        
        # 2. 出场逻辑
        # 持多仓 + RSI达到平多阈值 → 平多
        if has_long and rsi >= self.rsi_exit_overbought:
            pos_size = 0
            for symbol, pos in context.positions.items():
                if symbol == self.symbol and pos.size > 0:
                    pos_size = pos.size
                    break
            if pos_size > 0:
                signals.append(Signal(
                    symbol=self.symbol, side=Side.SELL, size=pos_size,
                    price=current_price, timestamp=current_time,
                    meta={'reason': 'no_grid_exit_long', 'posSide': 'long'}
                ))
                logger.info(f"无网格交易 | RSI平多 | RSI: {rsi:.1f}")
        
        # 持空仓 + RSI达到平空阈值 → 平空
        elif has_short and rsi <= self.rsi_exit_oversold:
            pos_size = 0
            for symbol, pos in context.positions.items():
                if symbol == self.symbol and pos.size < 0:
                    pos_size = abs(pos.size)
                    break
            if pos_size > 0:
                signals.append(Signal(
                    symbol=self.symbol, side=Side.BUY, size=pos_size,
                    price=current_price, timestamp=current_time,
                    meta={'reason': 'no_grid_exit_short', 'posSide': 'short'}
                ))
                logger.info(f"无网格交易 | RSI平空 | RSI: {rsi:.1f}")
        
        return signals
    
    def _grid_trading(self, layer: int, rsi: float, has_long: bool, has_short: bool,
                      current_price: float, current_time: datetime, trend: int,
                      context: StrategyContext) -> List[Signal]:
        """正常网格交易：3层实体架构 + 虚拟缓冲区
        层级定义: -1=虚拟低, 0=低实体(做多), 1=中实体(缓冲), 2=高实体(做空), 3=虚拟高
        """
        signals = []
        
        # --- 入场逻辑 ---
        
        # 1. 做多 (在层 0 底实体区域)
        if layer == 0 and not has_long:
            # 要求在层 0 的下半部
            layer_mid = (self.entity_grids[0] + self.entity_grids[1]) / 2
            if current_price <= layer_mid and rsi <= self.rsi_oversold:
                size = 0.2 * self.current_leverage
                if trend == 1:
                    size = min(size * 2, 0.4 * self.current_leverage)
                
                signals.append(Signal(
                    symbol=self.symbol, side=Side.BUY, size=size,
                    price=current_price, timestamp=current_time,
                    meta={'reason': 'layer0_long_entry', 'posSide': 'long'}
                ))
                logger.info(f"入场信号 | 做多 (层0) | RSI: {rsi:.1f} | 价格: {current_price:.2f}")

        # 2. 做空 (在层 2 高实体区域)
        elif layer == 2 and not has_short:
            # 要求在层 2 的上半部
            layer_mid = (self.entity_grids[2] + self.entity_grids[3]) / 2
            if current_price >= layer_mid and rsi >= self.rsi_overbought:
                size = 0.2 * self.current_leverage
                if trend == -1:
                    size = min(size * 2, 0.4 * self.current_leverage)
                
                signals.append(Signal(
                    symbol=self.symbol, side=Side.SELL, size=size,
                    price=current_price, timestamp=current_time,
                    meta={'reason': 'layer2_short_entry', 'posSide': 'short'}
                ))
                logger.info(f"入场信号 | 做空 (层2) | RSI: {rsi:.1f} | 价格: {current_price:.2f}")

        # --- 出场逻辑 ---
        
        # 3. 平多 (中层、高层或虚拟高层触发 RSI 止盈)
        if has_long and layer >= 1:
            if rsi >= self.rsi_exit_overbought:
                pos_size = 0
                for symbol, pos in context.positions.items():
                    if symbol == self.symbol and pos.size > 0:
                        pos_size = pos.size
                        break
                if pos_size > 0:
                    signals.append(Signal(
                        symbol=self.symbol, side=Side.SELL, size=pos_size,
                        price=current_price, timestamp=current_time,
                        meta={'reason': f'exit_long_layer{layer}', 'posSide': 'long'}
                    ))
                    logger.info(f"出场信号 | 平多 (层{layer}) | RSI: {rsi:.1f}")

        # 4. 平空 (中层、低层或虚拟低层触发 RSI 止盈)
        elif has_short and layer <= 1:
            if rsi <= self.rsi_exit_oversold:
                pos_size = 0
                for symbol, pos in context.positions.items():
                    if symbol == self.symbol and pos.size < 0:
                        pos_size = abs(pos.size)
                        break
                if pos_size > 0:
                    signals.append(Signal(
                        symbol=self.symbol, side=Side.BUY, size=pos_size,
                        price=current_price, timestamp=current_time,
                        meta={'reason': f'exit_short_layer{layer}', 'posSide': 'short'}
                    ))
                    logger.info(f"出场信号 | 平空 (层{layer}) | RSI: {rsi:.1f}")
        
        return signals

    def calculate_dynamic_leverage_for_engine(self, atr: float, price: float, context: StrategyContext):
        """动态杠杆逻辑 - 适配引擎"""
        atr_pct = atr / price * 100
        if atr_pct < 1.5: lev = 3.0
        elif atr_pct < 3.0: lev = 2.0
        else: lev = 1.0
        
        if lev != self.current_leverage:
            logger.info(f"杠杆调整请求: {self.current_leverage}x -> {lev}x (ATR: {atr_pct:.2f}%)")
            self.current_leverage = lev
            # 将杠杆调整请求放入 context.meta，LiveEngine 会捕获它
            context.meta['requested_leverage'] = lev

    def get_status(self) -> Dict:
        """返回给 Dashboard 的状态 (适配 V93Innovation)"""
        current_price = self.status_data.get('current_price', 0.0)
        rsi = self.status_data.get('rsi', 50.0)
        
        # 重新计算完整的 6 线网格供前端显示 (VH, P3, P2, P1, P0, VL)
        grid_prices = []
        if self.entity_grids and len(self.entity_grids) >= 4 and self.virtual_grids:
            full_grids = [
                self.virtual_grids[1],  # 极高
                self.entity_grids[3],   # P3 (高层顶/实体顶)
                self.entity_grids[2],   # P2
                self.entity_grids[1],   # P1
                self.entity_grids[0],   # P0 (底层底/实体底)
                self.virtual_grids[0]   # 极低
            ]
            grid_prices = [float(p) for p in full_grids]
            
        return {
            'name': self.name,
            'rsi': float(rsi),
            'layer': int(self.status_data.get('layer', -1) if self.status_data.get('layer') is not None else -1),
            'trend': int(self.status_data.get('trend', 0) if self.status_data.get('trend') is not None else 0),
            'leverage': float(self.current_leverage),
            'grid_range': [float(self.grid_bottom), float(self.grid_top)],
            'grid_prices': grid_prices,
            'grid_count': 3,
            'signal_text': self.status_data.get('signal_text', '等待中...'),
            'signal_color': self.status_data.get('signal_color', 'neutral'),
            'signal_strength': self.status_data.get('confidence', 0.0),
            'rsi_thresholds': {
                'oversold': float(self.rsi_oversold),
                'overbought': float(self.rsi_overbought)
            },
            'daily_reset': int(self.daily_reset_count),
            'breakout_reset': int(self.breakout_reset_count),
            'trade_count': int(self.trade_count)
        }

    def _save_grid_state(self):
        """保存当前网格状态至文件 (最新值 + 增量历史)"""
        try:
            # 确保目录存在
            if not os.path.exists('ethswap'):
                os.makedirs('ethswap')
                
            state = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'grid_top': float(self.grid_top),
                'grid_bottom': float(self.grid_bottom),
                'entity_grids': [float(p) for p in self.entity_grids],
                'virtual_grids': [float(p) for p in self.virtual_grids],
                'daily_reset_count': int(self.daily_reset_count)
            }
            
            # 1. 保存最新状态 (覆盖)
            with open('ethswap/v93_state.json', 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=4)
            
            # 2. 保存增量历史 (追加)
            history_file = 'ethswap/v93_grid_history.json'
            history = []
            if os.path.exists(history_file):
                try:
                    with open(history_file, 'r', encoding='utf-8') as f:
                        history = json.load(f)
                except:
                    history = []
            
            history.append(state)
            # 保持历史记录不要无限大 (保留最近 150 条，约能覆盖 1-2 天的高频变动)
            if len(history) > 150:
                history = history[-150:]
                
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=4)
                
            logger.info("网格状态已持久化保存 (最新状态 + 增量历史)")
        except Exception as e:
            logger.error(f"保存网格状态失败: {e}")

    def _load_grid_state(self):
        """从文件加载历史网格状态"""
        state_file = 'ethswap/v93_state.json'
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                
                self.grid_top = float(state.get('grid_top', 0.0))
                self.grid_bottom = float(state.get('grid_bottom', 0.0))
                self.entity_grids = state.get('entity_grids', [])
                self.virtual_grids = state.get('virtual_grids', [])
                
                if self.entity_grids and self.virtual_grids:
                    logger.info(f"成功从文件恢复网格状态 | 区间: [{self.grid_bottom:.2f} ↔ {self.grid_top:.2f}]")
            except Exception as e:
                logger.error(f"加载网格状态失败: {e}")
        
    def calculate_grids(self, df: pd.DataFrame, window_hours: int = 6):
        """计算3层网格架构: 实体3层 + 虚拟2层 (分 5 段采样去极值)"""
        lookback = window_hours * 60  # 6小时=360, 4小时=240
        if len(df) < lookback:
            lookback = len(df)
        
        recent = df.tail(lookback)
        if recent.empty:
            return
            
        # --- 分 5 段截取每段最高最低点 ---
        seg_size = len(recent) // 5
        highs = []
        lows = []
        
        for i in range(5):
            # 确保最后一段包含所有剩余数据
            start_idx = i * seg_size
            end_idx = (i + 1) * seg_size if i < 4 else len(recent)
            segment = recent.iloc[start_idx:end_idx]
            
            if not segment.empty:
                highs.append(segment['high'].max())
                lows.append(segment['low'].min())
        
        # --- 去极值算法 (5高去最大，5低去最小) ---
        if len(highs) >= 2:
            # 排序后去掉最高的一个，取剩余平均
            self.grid_top = np.mean(np.sort(highs)[:-1])
        else:
            self.grid_top = recent['high'].max()
            
        if len(lows) >= 2:
            # 排序后去掉最低的一个，取剩余平均
            self.grid_bottom = np.mean(np.sort(lows)[1:])
        else:
            self.grid_bottom = recent['low'].min()
        
        # --- 五层空间布局 (3实体 + 2虚拟) ---
        step = (self.grid_top - self.grid_bottom) / 3
        self.entity_grids = [
            self.grid_bottom,              # P0
            self.grid_bottom + step,       # P1
            self.grid_bottom + 2 * step,   # P2
            self.grid_top                  # P3
        ]
        
        # 虚拟缓冲层
        self.virtual_grids = [
            self.grid_bottom - step,       # P_low_virtual
            self.grid_top + step           # P_high_virtual
        ]
        
        self.last_grid_calc_time = df.index[-1]
        
        logger.info(f"网格计算完成 | 窗口: {window_hours}h | 区间: [{self.grid_bottom:.2f} ↔ {self.grid_top:.2f}] | 步长: {step:.2f}")
        logger.info(f"实体层: {[round(x, 2) for x in self.entity_grids]} | 虚拟层: {[round(x, 2) for x in self.virtual_grids]}")
        
        # 持久化保存
        self._save_grid_state()
    
    def calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """计算标准 Wilder's RSI (平滑移动平均)"""
        if len(prices) < period + 1:
            return 50.0
        
        # 使用 pandas 计算以获得稳定的平滑效果
        s = pd.Series(prices)
        delta = s.diff()
        
        ups = delta.clip(lower=0)
        downs = -1 * delta.clip(upper=0)
        
        # 指数平滑移动平均 (Wilder's 方法)
        # alpha = 1 / period
        ma_up = ups.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        ma_down = downs.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        
        rs = ma_up / ma_down
        rsi = 100 - (100 / (1 + rs))
        
        val = rsi.iloc[-1]
        return float(val) if not np.isnan(val) else 50.0
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """计算ATR"""
        if len(df) < 2:
            return df['close'].iloc[-1] * 0.02
        
        recent = df.tail(min(period, len(df)))
        tr_list = []
        
        for i in range(1, len(recent)):
            high = recent['high'].iloc[i]
            low = recent['low'].iloc[i]
            prev_close = recent['close'].iloc[i-1]
            
            tr1 = high - low
            tr2 = abs(high - prev_close)
            tr3 = abs(low - prev_close)
            tr_list.append(max(tr1, tr2, tr3))
        
        return np.mean(tr_list) if tr_list else recent['close'].iloc[-1] * 0.02
    
    def calculate_dynamic_leverage(self, atr: float, price: float) -> float:
        """动态杠杆: 1x-3x"""
        atr_pct = atr / price * 100
        
        if atr_pct < 1.5:
            lev = 3.0
        elif atr_pct < 3.0:
            lev = 2.0
        else:
            lev = 1.0
        
        if lev != self.current_leverage:
            logger.info(f"杠杆调整: {self.current_leverage}x -> {lev}x (ATR: {atr_pct:.2f}%)")
            self.current_leverage = lev
            self.api.set_leverage(lev)
        
        return lev
    
    def lstm_trend(self, price_history: List[float]) -> int:
        """轻量LSTM趋势判断: -1=做空, 0=中性, 1=做多"""
        if len(price_history) < 60:
            return 0
        
        recent = price_history[-60:]
        returns = np.diff(recent) / recent[:-1]
        momentum = np.mean(returns) * 100
        volatility = np.std(returns) * 100
        
        if momentum > volatility * 0.5 and momentum > 0.02:
            return 1
        elif momentum < -volatility * 0.5 and momentum < -0.02:
            return -1
        return 0
    
    def check_reset_conditions(self, current_price: float, current_time: datetime) -> Tuple[bool, int]:
        """检查重置条件 (返回: 是否重置, 采样窗口)
        逻辑：
        1. 不做任何定时强制重置。
        2. 每日 00:00 (北京时间) 恢复当日 2 次重置配额，不触发数据重扫。
        3. 价格突破虚拟层 (VH/VL) 后开启 2 小时观察期。
        4. 2 小时后仍未回归且配额充足 -> 触发一次重置，并使用 4h 窗口重算网格。
        """
        # --- 1. 北京时间 00:00 恢复配额 ---
        # 假设服务器时间/K线时间为 UTC，转换为北京时间 (UTC+8)
        cst_time = current_time + timedelta(hours=8)
        current_day = cst_time.date()
        
        if self.last_reset_day != current_day:
            self.last_reset_day = current_day
            self.daily_reset_count = 0  # 恢复 2 次机会
            self.breakout_triggered = False
            logger.info(f"北京时间跨天: {current_day} | 重置配额已恢复 (2次) | 当前网格维持不变")
            # 注意：此处不返回 True，因为 00:00 仅恢复次数，不再强制重置网格
        
        # --- 2. 突破重置检查 ---
        if self.daily_reset_count >= 2:
            return False, 6
            
        if len(self.virtual_grids) >= 2:
            lower_bound = self.virtual_grids[0]
            upper_bound = self.virtual_grids[1]
            
            # 检测是否突破
            is_outside = current_price < lower_bound or current_price > upper_bound
            
            if not self.breakout_triggered:
                if is_outside:
                    self.breakout_triggered = True
                    self.breakout_time = current_time
                    logger.info(f"警告：价格突破虚拟层 | 价格: {current_price:.2f} | 观察期开始 (2h)")
            else:
                # 已在观察期内
                if not is_outside:
                    # 价格回归，取消观察
                    self.breakout_triggered = False
                    logger.info(f"价格回归网格内 | 价格: {current_price:.2f} | 观察期取消")
                else:
                    # 价格持续在外面，检查是否满 2 小时
                    elapsed = (current_time - self.breakout_time).total_seconds()
                    if elapsed >= 2 * 3600:
                        self.breakout_triggered = False
                        self.daily_reset_count += 1
                        self.breakout_reset_count += 1
                        logger.info(f"观察期满 2 小时未回归 | 触发紧急重置 | 第 {self.daily_reset_count} 次")
                        return True, 4  # 触发重置，且使用 4 小时窗口
        
        return False, 6
    
    def execute_trade(self, side: str, size: float, price: float, reason: str):
        """执行交易"""
        try:
            actual_size = size * self.current_leverage
            result = self.api.place_order(side=side, sz=actual_size)
            
            if result.get('code') == '0':
                self.trade_count += 1
                logger.info(f"交易执行 | {side} | 数量: {actual_size:.4f} | 价格: {price:.2f} | 原因: {reason}")
                return True
            else:
                logger.error(f"交易失败 | {result.get('msg')}")
                return False
                
        except Exception as e:
            logger.error(f"交易异常: {e}")
            return False
    
    def close_all_positions(self, current_price: float):
        """平仓所有持仓"""
        try:
            result = self.api.close_position()
            if result.get('code') == '0':
                logger.info("全部持仓已平仓")
                self.positions.clear()
                return True
            else:
                logger.error(f"平仓失败: {result.get('msg')}")
                return False
        except Exception as e:
            logger.error(f"平仓异常: {e}")
            return False
    
    def get_current_layer(self, price: float) -> Optional[int]:
        """确定当前价格所在层 (5层空间架构: 3实体 + 2虚拟)"""
        if len(self.entity_grids) < 4:
            return None
        
        # 虚拟层下界检查
        if price < self.virtual_grids[0]:
            return None
            
        # 层级映射:
        # -1: [VirtualLow, P0)
        #  0: [P0, P1) - 底层实体
        #  1: [P1, P2) - 中层实体
        #  2: [P2, P3) - 高层实体
        #  3: [P3, VirtualHigh)
        
        if price < self.entity_grids[0]:
            return -1
        elif price < self.entity_grids[1]:
            return 0
        elif price < self.entity_grids[2]:
            return 1
        elif price < self.entity_grids[3]:
            return 2
        elif price < self.virtual_grids[1]:
            return 3
        else:
            return None
    
    def run_cycle(self):
        """运行一个交易周期 (Standalone模式，适配 3层实体架构)"""
        try:
            if not self.api:
                logger.warning("API 模块未初始化，无法通过 run_cycle 独立运行。请检查配置或改用 Engine 模式。")
                return
                
            # 1. 获取数据 (360根预热)
            df = self.api.get_candles(bar="1m", limit=400)
            if df.empty:
                logger.warning("获取K线数据失败")
                return
            
            # 2. 转换数据为 MarketData
            row = df.iloc[-1]
            data = MarketData(
                symbol=self.symbol,
                timestamp=df.index[-1].to_pydatetime(),
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=float(row['vol'])
            )
            
            # 3. 构造 Mock Context (Standalone模式不依赖引擎)
            context = StrategyContext()
            context.cash = 10000.0  # 默认 Mock 资金
            
            # 获取实际持仓
            pos_info = self.api.get_position()
            if pos_info.get('code') == '0' and pos_info.get('data'):
                for p in pos_info['data']:
                    inst_id = p.get('instId')
                    size = float(p.get('pos', 0))
                    if size != 0:
                        from core.types import Position
                        context.positions[inst_id] = Position(
                            symbol=inst_id,
                            size=size,
                            avg_price=float(p.get('avgPx', 0)),
                            unrealized_pnl=float(p.get('upl', 0))
                        )
            
            # 4. 调用核心策略逻辑
            signals = self.on_data(data, context)
            
            # 5. 执行信号
            for sig in signals:
                side = "buy" if sig.side == Side.BUY else "sell"
                # Standalone 模式直接在这里通过 API 下单
                self.execute_trade(side, sig.size, sig.price, sig.meta.get('reason', 'on_data_signal'))
            
            # 6. 处理杠杆调整请求
            if 'requested_leverage' in context.meta:
                lev = context.meta['requested_leverage']
                self.api.set_leverage(lev)
                
        except Exception as e:
            logger.error(f"周期运行异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def run(self):
        """主循环 (Standalone模式)"""
        logger.info("="*60)
        logger.info(f"策略 {self.name} 启动")
        logger.info(f"端口: {self.config.get('port', 5090)}")
        logger.info(f"标的: {self.symbol}")
        logger.info(f"特色: 3层实体 + 2层虚拟 (v1.1)")
        logger.info("="*60)
        
        # 启动看板 (如果存在)
        if self.server:
            self.server.start_background()
        else:
            logger.info("看板未初始化或由外部管理")
        
        while True:
            try:
                self.run_cycle()
                
                # 同步状态到看板
                if self.server:
                    status = self.get_status()
                    # 补充一些全局信息
                    status.update({
                        'symbol': self.symbol,
                        'total_value': 0, # TODO: 获取账户余额
                        'cash': 0,
                        'position_value': 0,
                        'pnl_pct': 0,
                        'history_candles': self.df_history.reset_index().rename(columns={'ts': 'time'}).to_dict('records') if not self.df_history.empty else []
                    })
                    self.server.update(status)
                
                time.sleep(60)
                
            except KeyboardInterrupt:
                logger.info("策略停止")
                break
            except Exception as e:
                logger.error(f"主循环异常: {e}")
                time.sleep(60)


def main():
    """主入口"""
    try:
        with open('config.v93innovation.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        logger.error("配置文件不存在: config.v93innovation.json")
        return
    except json.JSONDecodeError:
        logger.error("配置文件格式错误")
        return
    
    config['standalone'] = True  # 强制开启独立模式组件
    if 'port' not in config:
        config['port'] = 5090
        
    strategy = V93Strategy(config)
    strategy.run()


if __name__ == "__main__":
    main()