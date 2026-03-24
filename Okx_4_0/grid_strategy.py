"""
动态网格交易策略 V4.0 - RSI增强版
作者: AI Assistant
日期: 2024
功能: 基于RSI指标的动态网格交易系统，支持回测和模拟交易
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json
import logging
import warnings
warnings.filterwarnings('ignore')

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """市场状态枚举"""
    TRENDING_UP = "上涨趋势"
    TRENDING_DOWN = "下跌趋势"
    RANGING = "震荡区间"
    UNKNOWN = "未知"


@dataclass
class Trade:
    """交易记录数据类"""
    timestamp: datetime
    type: str  # 'buy', 'sell', 'stop_loss'
    price: float
    size: float
    pnl: float = 0.0
    rsi: float = 50.0
    grid_level: float = 0.0
    reason: str = ""


@dataclass
class Position:
    """持仓数据类"""
    entry_price: float
    size: float
    grid_level: float
    entry_time: datetime
    stop_loss_price: float


class DynamicGridStrategyV4:
    """
    V4.0 动态网格策略 - RSI增强版
    
    核心特性:
    1. 自适应RSI参数 (根据波动率动态调整阈值)
    2. 多时间框架趋势识别 (ADX + 均线)
    3. 凯利公式动态仓位管理
    4. 智能网格偏移 (RSI信号加权)
    5. 分层止损机制
    6. 市场状态识别与策略切换
    """
    
    def __init__(self, 
                 # 基础参数
                 initial_capital: float = 10000.0,
                 symbol: str = "BTCUSDT",
                 
                 # 网格参数
                 grid_levels: int = 10,
                 grid_refresh_period: int = 100,  # 多少根K线刷新网格
                 grid_buffer_pct: float = 0.1,    # 网格缓冲带比例
                 
                 # RSI参数
                 rsi_period: int = 14,
                 rsi_weight: float = 0.4,         # RSI对网格调整的影响权重
                 rsi_oversold: float = 35,        # 超卖阈值
                 rsi_overbought: float = 65,      # 超买阈值
                 rsi_extreme_buy: float = 80,     # 极端超买暂停买入
                 rsi_extreme_sell: float = 20,    # 极端超卖暂停卖出
                 adaptive_rsi: bool = True,       # 是否启用自适应RSI阈值
                 
                 # 趋势过滤参数
                 use_trend_filter: bool = True,
                 adx_period: int = 14,
                 adx_threshold: float = 25,       # ADX > 25 认为有趋势
                 ma_period: int = 50,             # 均线周期
                 
                 # 仓位管理参数
                 base_position_pct: float = 0.1,  # 基础仓位比例 (1/N)
                 max_positions: int = 5,          # 最大持仓层数
                 use_kelly_sizing: bool = True,   # 是否使用凯利公式
                 kelly_fraction: float = 0.3,     # 凯利公式保守系数 (半凯利)
                 max_position_multiplier: float = 2.0,  # 最大仓位倍数
                 min_position_multiplier: float = 0.5,  # 最小仓位倍数
                 
                 # 止损参数
                 stop_loss_pct: float = 0.05,     # 基础止损比例
                 trailing_stop: bool = True,      # 是否启用移动止损
                 trailing_stop_pct: float = 0.03, # 移动止损比例
                 
                 # 周期管理参数
                 cycle_reset_period: int = 5000,  # 强制重置周期 (K线数)
                 max_drawdown_reset: float = 0.30, # 最大回撤触发重置
                 
                 # 交易费用
                 maker_fee: float = 0.001,        # 挂单手续费 0.1%
                 taker_fee: float = 0.001,        # 吃单手续费 0.1%
                 ):
        
        # 保存参数
        self.params = {k: v for k, v in locals().items() if k != 'self'}
        
        # 账户状态
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.symbol = symbol
        
        # 网格状态
        self.grid_upper = None
        self.grid_lower = None
        self.grid_prices = []
        self.last_grid_update = 0
        
        # 持仓和交易记录
        self.positions: List[Position] = []
        self.trades: List[Trade] = []
        self.equity_curve = []
        
        # 统计指标
        self.win_count = 0
        self.loss_count = 0
        self.total_pnl = 0.0
        
        # 市场状态
        self.current_regime = MarketRegime.UNKNOWN
        self.current_rsi = 50.0
        self.current_adx = 0.0
        
        logger.info(f"策略V4.0初始化完成 - 交易对: {symbol}, 初始资金: ${initial_capital:,.2f}")
    
    def calculate_rsi(self, prices: pd.Series, period: int = None) -> float:
        """计算RSI指标"""
        period = period or self.params['rsi_period']
        if len(prices) < period + 1:
            return 50.0
        
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        # 处理除零
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        
        return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50.0
    
    def calculate_adx(self, high: pd.Series, low: pd.Series, close: pd.Series) -> float:
        """计算ADX趋势强度指标"""
        period = self.params['adx_period']
        if len(close) < period * 2:
            return 0.0
        
        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Directional Movement
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        
        # Smooth
        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
        
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
        adx = dx.rolling(window=period).mean()
        
        return adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else 0.0
    
    def detect_market_regime(self, df: pd.DataFrame) -> MarketRegime:
        """识别市场状态"""
        if not self.params['use_trend_filter'] or len(df) < self.params['ma_period']:
            return MarketRegime.RANGING
        
        # 计算ADX
        self.current_adx = self.calculate_adx(df['high'], df['low'], df['close'])
        
        # 计算均线
        ma = df['close'].rolling(window=self.params['ma_period']).mean().iloc[-1]
        current_price = df['close'].iloc[-1]
        
        # 判断趋势
        if self.current_adx > self.params['adx_threshold']:
            if current_price > ma * 1.02:  # 价格显著高于均线
                return MarketRegime.TRENDING_UP
            elif current_price < ma * 0.98:  # 价格显著低于均线
                return MarketRegime.TRENDING_DOWN
        
        return MarketRegime.RANGING
    
    def get_adaptive_rsi_thresholds(self, df: pd.DataFrame) -> Tuple[float, float]:
        """获取自适应RSI阈值"""
        if not self.params['adaptive_rsi']:
            return self.params['rsi_oversold'], self.params['rsi_overbought']
        
        # 基于近期波动率调整阈值
        returns = df['close'].pct_change().dropna()
        volatility = returns.std() * np.sqrt(1440)  # 年化波动率 (假设1分钟线)
        
        # 高波动时放宽阈值，低波动时收紧
        base_oversold = self.params['rsi_oversold']
        base_overbought = self.params['rsi_overbought']
        
        # 波动率调整因子 (假设正常波动率 50%)
        vol_factor = min(max(volatility / 0.5, 0.5), 2.0)
        
        adjusted_oversold = max(20, min(40, base_oversold / vol_factor))
        adjusted_overbought = min(80, max(60, 100 - (100 - base_overbought) / vol_factor))
        
        return adjusted_oversold, adjusted_overbought
    
    def get_rsi_signal(self, rsi: float, oversold: float, overbought: float) -> float:
        """
        将RSI转换为 [-1, 1] 信号
        -1: 强烈看空 (超买)
        +1: 强烈看多 (超卖)
        """
        if rsi <= oversold:
            return 1.0
        elif rsi >= overbought:
            return -1.0
        else:
            # 线性插值
            mid = 50
            if rsi < mid:
                return (mid - rsi) / (mid - oversold) * 0.5
            else:
                return (mid - rsi) / (overbought - mid) * 0.5
    
    def calculate_dynamic_grid(self, df: pd.DataFrame) -> Tuple[float, float]:
        """计算动态网格区间"""
        lookback = min(self.params['grid_refresh_period'], len(df))
        recent_data = df.iloc[-lookback:]
        
        recent_high = recent_data['high'].max()
        recent_low = recent_data['low'].min()
        
        # 添加缓冲带
        range_size = recent_high - recent_low
        buffer = range_size * self.params['grid_buffer_pct']
        
        upper = recent_high + buffer
        lower = recent_low - buffer
        
        # 根据RSI调整网格位置
        if self.params['rsi_weight'] > 0:
            oversold, overbought = self.get_adaptive_rsi_thresholds(df)
            rsi_signal = self.get_rsi_signal(self.current_rsi, oversold, overbought)
            
            # 网格偏移
            shift = range_size * rsi_signal * self.params['rsi_weight'] * 0.2
            upper += shift
            lower += shift
        
        return upper, lower
    
    def calculate_position_size(self, rsi_signal: float, is_buy: bool) -> float:
        """计算动态仓位大小"""
        base_size = self.current_capital * self.params['base_position_pct']
        
        # 根据市场状态调整
        regime_multiplier = 1.0
        if self.current_regime == MarketRegime.TRENDING_UP and is_buy:
            regime_multiplier = 0.7  # 上涨趋势减少买入
        elif self.current_regime == MarketRegime.TRENDING_DOWN and not is_buy:
            regime_multiplier = 0.7  # 下跌趋势减少卖出(即减少逆势操作)
        
        # RSI信号调整
        if self.params['use_kelly_sizing']:
            # 简化凯利公式: f = (p*b - q)/b
            # 假设胜率与RSI极端程度相关
            if is_buy:
                win_prob = 0.5 + rsi_signal * 0.2  # 超卖时胜率更高
            else:
                win_prob = 0.5 - rsi_signal * 0.2  # 超买时胜率更高
            
            win_prob = np.clip(win_prob, 0.3, 0.8)
            loss_prob = 1 - win_prob
            avg_win = avg_loss = 1.0  # 简化假设
            
            kelly_pct = (win_prob * avg_win - loss_prob * avg_loss) / avg_win
            kelly_pct = max(0, kelly_pct) * self.params['kelly_fraction']
            
            rsi_multiplier = 1 + kelly_pct
        else:
            # 简单线性调整
            if is_buy:
                rsi_multiplier = 1 + rsi_signal * 0.5  # 超卖时加仓
            else:
                rsi_multiplier = 1 - rsi_signal * 0.5  # 超买时加仓卖出
            
            rsi_multiplier = np.clip(
                rsi_multiplier, 
                self.params['min_position_multiplier'],
                self.params['max_position_multiplier']
            )
        
        final_size = base_size * regime_multiplier * rsi_multiplier
        return min(final_size, self.current_capital * 0.95)  # 保留5%现金
    
    def check_stop_loss(self, current_price: float, current_time: datetime) -> List[Trade]:
        """检查并执行止损"""
        executed_stops = []
        
        for pos in self.positions[:]:
            # 计算止损价格
            if self.params['trailing_stop']:
                # 移动止损: 从最高点回撤trailing_stop_pct
                highest_price = max(pos.entry_price, current_price)  # 简化处理
                stop_price = highest_price * (1 - self.params['trailing_stop_pct'])
                effective_stop = max(pos.stop_loss_price, stop_price)
            else:
                effective_stop = pos.stop_loss_price
            
            if current_price <= effective_stop:
                # 执行止损
                pnl = (current_price - pos.entry_price) / pos.entry_price * pos.size
                pnl -= pos.size * self.params['taker_fee']  # 扣除手续费
                
                self.current_capital += pos.size + pnl
                
                trade = Trade(
                    timestamp=current_time,
                    type='stop_loss',
                    price=current_price,
                    size=pos.size,
                    pnl=pnl,
                    rsi=self.current_rsi,
                    grid_level=pos.grid_level,
                    reason=f"止损触发 (止损价: ${effective_stop:.2f})"
                )
                
                self.trades.append(trade)
                executed_stops.append(trade)
                self.positions.remove(pos)
                
                if pnl > 0:
                    self.win_count += 1
                else:
                    self.loss_count += 1
                self.total_pnl += pnl
        
        return executed_stops
    
    def execute_buy(self, price: float, size: float, grid_level: float, 
                    current_time: datetime, reason: str = "") -> Optional[Trade]:
        """执行买入"""
        if size > self.current_capital * 0.95:
            return None
        
        # 扣除手续费
        fee = size * self.params['taker_fee']
        actual_size = size - fee
        
        self.current_capital -= size
        
        # 创建持仓
        position = Position(
            entry_price=price,
            size=actual_size,
            grid_level=grid_level,
            entry_time=current_time,
            stop_loss_price=price * (1 - self.params['stop_loss_pct'])
        )
        self.positions.append(position)
        
        trade = Trade(
            timestamp=current_time,
            type='buy',
            price=price,
            size=actual_size,
            rsi=self.current_rsi,
            grid_level=grid_level,
            reason=reason
        )
        self.trades.append(trade)
        
        return trade
    
    def execute_sell(self, position: Position, price: float, 
                     current_time: datetime, reason: str = "") -> Trade:
        """执行卖出"""
        pnl = (price - position.entry_price) / position.entry_price * position.size
        pnl -= position.size * self.params['taker_fee']  # 扣除手续费
        
        self.current_capital += position.size + pnl
        
        trade = Trade(
            timestamp=current_time,
            type='sell',
            price=price,
            size=position.size,
            pnl=pnl,
            rsi=self.current_rsi,
            grid_level=position.grid_level,
            reason=reason
        )
        
        self.trades.append(trade)
        self.positions.remove(position)
        
        if pnl > 0:
            self.win_count += 1
        else:
            self.loss_count += 1
        self.total_pnl += pnl
        
        return trade
    
    def should_reset_cycle(self, current_idx: int) -> Tuple[bool, str]:
        """判断是否应重置周期"""
        # 检查强制重置周期
        if current_idx - self.last_grid_update >= self.params['cycle_reset_period']:
            return True, "达到强制重置周期"
        
        # 检查最大回撤
        if len(self.equity_curve) > 0:
            recent_equity = [e['equity'] for e in self.equity_curve[-1000:]]
            peak = max(recent_equity)
            current = recent_equity[-1]
            drawdown = (current - peak) / peak
            
            if drawdown <= -self.params['max_drawdown_reset']:
                return True, f"触发最大回撤限制 ({drawdown:.2%})"
        
        return False, ""
    
    def reset_cycle(self, df: pd.DataFrame, current_idx: int):
        """重置交易周期"""
        logger.info(f"周期重置 - 原因: {self.should_reset_cycle(current_idx)[1]}")
        
        # 平掉所有持仓
        current_price = df['close'].iloc[current_idx]
        current_time = df.index[current_idx]
        
        for pos in self.positions[:]:
            self.execute_sell(pos, current_price, current_time, "周期重置平仓")
        
        # 重置网格
        self.grid_upper = None
        self.grid_lower = None
        self.last_grid_update = current_idx
        
        logger.info(f"重置完成 - 当前资金: ${self.current_capital:,.2f}")
    
    def run_backtest(self, df: pd.DataFrame, verbose: bool = True) -> Dict:
        """
        运行回测
        
        Parameters:
        -----------
        df : pd.DataFrame
            包含列: open, high, low, close, volume (可选)
        verbose : bool
            是否打印进度
            
        Returns:
        --------
        Dict : 回测结果统计
        """
        logger.info(f"开始回测 - 数据量: {len(df)} 根K线")
        
        # 确保数据包含必要列
        required_cols = ['open', 'high', 'low', 'close']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"缺少必要列: {col}")
        
        # 计算技术指标
        df['rsi'] = df['close'].rolling(window=self.params['rsi_period']).apply(
            lambda x: self.calculate_rsi(x, self.params['rsi_period'])
        )
        
        start_idx = max(self.params['rsi_period'], self.params['ma_period']) + 100
        
        for i in range(start_idx, len(df)):
            current_price = df['close'].iloc[i]
            current_high = df['high'].iloc[i]
            current_low = df['low'].iloc[i]
            current_time = df.index[i]
            self.current_rsi = df['rsi'].iloc[i] if 'rsi' in df.columns else 50.0
            
            # 更新市场状态
            self.current_regime = self.detect_market_regime(df.iloc[:i])
            
            # 检查周期重置
            should_reset, reset_reason = self.should_reset_cycle(i)
            if should_reset:
                self.reset_cycle(df, i)
            
            # 更新网格
            if i - self.last_grid_update >= self.params['grid_refresh_period'] or self.grid_upper is None:
                self.grid_upper, self.grid_lower = self.calculate_dynamic_grid(df.iloc[:i])
                self.grid_prices = np.linspace(self.grid_lower, self.grid_upper, self.params['grid_levels'])
                self.last_grid_update = i
            
            # 检查止损
            self.check_stop_loss(current_price, current_time)
            
            # 获取自适应阈值
            oversold, overbought = self.get_adaptive_rsi_thresholds(df.iloc[:i])
            rsi_signal = self.get_rsi_signal(self.current_rsi, oversold, overbought)
            
            # 执行网格交易
            for grid_price in self.grid_prices:
                # 买入条件: 价格下穿网格线
                if (df['low'].iloc[i-1] > grid_price and current_low <= grid_price):
                    if len(self.positions) < self.params['max_positions']:
                        # RSI过滤: 极端超买时暂停买入
                        if self.current_rsi < self.params['rsi_extreme_buy']:
                            size = self.calculate_position_size(rsi_signal, is_buy=True)
                            if size > 100:  # 最小交易金额
                                self.execute_buy(
                                    current_price, size, grid_price, current_time,
                                    f"网格买入 (RSI: {self.current_rsi:.1f})"
                                )
                
                # 卖出条件: 价格上穿网格线且有盈利持仓
                if (df['high'].iloc[i-1] < grid_price and current_high >= grid_price):
                    for pos in self.positions[:]:
                        if pos.entry_price < current_price * 0.995:  # 至少0.5%盈利
                            # RSI过滤: 极端超卖时暂停卖出(可能反弹)
                            if self.current_rsi > self.params['rsi_extreme_sell']:
                                self.execute_sell(
                                    pos, current_price, current_time,
                                    f"网格卖出 (RSI: {self.current_rsi:.1f})"
                                )
                                break  # 只卖出一层
            
            # 记录权益
            unrealized = sum([
                (current_price - p.entry_price) / p.entry_price * p.size 
                for p in self.positions
            ])
            total_equity = self.current_capital + sum([p.size for p in self.positions]) + unrealized
            
            self.equity_curve.append({
                'timestamp': current_time,
                'equity': total_equity,
                'price': current_price,
                'rsi': self.current_rsi,
                'adx': self.current_adx,
                'regime': self.current_regime.value,
                'positions': len(self.positions)
            })
            
            # 打印进度
            if verbose and i % 5000 == 0:
                progress = (i - start_idx) / (len(df) - start_idx) * 100
                logger.info(f"回测进度: {progress:.1f}% - 当前权益: ${total_equity:,.2f}")
        
        return self.get_results()
    
    def get_results(self) -> Dict:
        """获取回测结果统计"""
        if len(self.equity_curve) == 0:
            return {}
        
        equity_df = pd.DataFrame(self.equity_curve)
        
        # 基础指标
        total_return = (equity_df['equity'].iloc[-1] - self.initial_capital) / self.initial_capital
        
        # 最大回撤
        equity_df['peak'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['peak']) / equity_df['peak']
        max_drawdown = equity_df['drawdown'].min()
        
        # 夏普比率 (简化版，假设无风险利率为0)
        returns = equity_df['equity'].pct_change().dropna()
        sharpe_ratio = returns.mean() / returns.std() * np.sqrt(525600) if returns.std() != 0 else 0
        
        # 交易统计
        buy_trades = [t for t in self.trades if t.type == 'buy']
        sell_trades = [t for t in self.trades if t.type == 'sell']
        stop_trades = [t for t in self.trades if t.type == 'stop_loss']
        
        winning_sells = [t for t in sell_trades if t.pnl > 0]
        win_rate = len(winning_sells) / len(sell_trades) if sell_trades else 0
        
        avg_win = np.mean([t.pnl for t in winning_sells]) if winning_sells else 0
        losing_sells = [t for t in sell_trades if t.pnl <= 0]
        avg_loss = np.mean([t.pnl for t in losing_sells]) if losing_sells else 0
        
        # 盈亏比
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
        
        results = {
            'initial_capital': self.initial_capital,
            'final_equity': equity_df['equity'].iloc[-1],
            'total_return': total_return,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'total_trades': len(self.trades),
            'buy_count': len(buy_trades),
            'sell_count': len(sell_trades),
            'stop_loss_count': len(stop_trades),
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'total_pnl': self.total_pnl,
            'equity_curve': equity_df,
            'trades': self.trades,
            'params': self.params
        }
        
        return results
    
    def print_report(self, results: Dict = None):
        """打印回测报告"""
        if results is None:
            results = self.get_results()
        
        print("\n" + "=" * 80)
        print("动态网格策略 V4.0 - 回测报告")
        print("=" * 80)
        
        print(f"\n【基础信息】")
        print(f"交易对: {self.symbol}")
        print(f"回测周期: {len(self.equity_curve)} 根K线")
        print(f"初始资金: ${results['initial_capital']:,.2f}")
        print(f"最终权益: ${results['final_equity']:,.2f}")
        
        print(f"\n【收益指标】")
        print(f"总收益率: {results['total_return']:.2%}")
        print(f"最大回撤: {results['max_drawdown']:.2%}")
        print(f"夏普比率: {results['sharpe_ratio']:.2f}")
        
        print(f"\n【交易统计】")
        print(f"总交易次数: {results['total_trades']}")
        print(f"买入次数: {results['buy_count']}")
        print(f"卖出次数: {results['sell_count']}")
        print(f"止损次数: {results['stop_loss_count']}")
        print(f"胜率: {results['win_rate']:.2%}")
        print(f"盈亏比: {results['profit_factor']:.2f}")
        print(f"平均盈利: ${results['avg_win']:,.2f}")
        print(f"平均亏损: ${results['avg_loss']:,.2f}")
        
        print(f"\n【策略参数】")
        for key, value in list(results['params'].items())[:10]:
            print(f"  {key}: {value}")
        
        print("=" * 80)
    
    def plot_results(self, save_path: str = None):
        """绘制回测结果图表"""
        if len(self.equity_curve) == 0:
            logger.warning("没有数据可绘制")
            return
        
        equity_df = pd.DataFrame(self.equity_curve)
        
        fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=True)
        
        # 1. 权益曲线和价格
        ax1 = axes[0]
        ax1_twin = ax1.twinx()
        
        ax1.plot(equity_df['timestamp'], equity_df['equity'], 
                label='账户权益', color='blue', linewidth=1.5)
        ax1.axhline(y=self.initial_capital, color='gray', linestyle='--', alpha=0.5)
        ax1.set_ylabel('权益 (USDT)', color='blue')
        ax1.tick_params(axis='y', labelcolor='blue')
        
        # 采样显示价格避免过于密集
        sample_idx = range(0, len(equity_df), max(1, len(equity_df)//1000))
        ax1_twin.plot(equity_df['timestamp'].iloc[sample_idx], 
                     equity_df['price'].iloc[sample_idx],
                     label='价格', color='gray', alpha=0.3, linewidth=0.5)
        ax1_twin.set_ylabel('价格', color='gray')
        ax1_twin.tick_params(axis='y', labelcolor='gray')
        
        ax1.set_title('动态网格策略 V4.0 - 回测结果', fontsize=14, fontweight='bold')
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)
        
        # 2. 回撤
        ax2 = axes[1]
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['equity'].cummax()) / equity_df['equity'].cummax()
        ax2.fill_between(equity_df['timestamp'], equity_df['drawdown'], 0, 
                        alpha=0.5, color='red', label='回撤')
        ax2.set_ylabel('回撤比例')
        ax2.legend(loc='lower left')
        ax2.grid(True, alpha=0.3)
        
        # 3. RSI和持仓
        ax3 = axes[2]
        ax3_twin = ax3.twinx()
        
        ax3.plot(equity_df['timestamp'], equity_df['rsi'], 
                label='RSI(14)', color='purple', alpha=0.7, linewidth=0.8)
        ax3.axhline(y=self.params['rsi_overbought'], color='red', linestyle='--', alpha=0.5)
        ax3.axhline(y=self.params['rsi_oversold'], color='green', linestyle='--', alpha=0.5)
        ax3.fill_between(equity_df['timestamp'], 30, 70, alpha=0.1, color='gray')
        ax3.set_ylabel('RSI', color='purple')
        ax3.set_ylim(0, 100)
        
        ax3_twin.plot(equity_df['timestamp'], equity_df['positions'], 
                     label='持仓层数', color='orange', alpha=0.7)
        ax3_twin.set_ylabel('持仓层数', color='orange')
        
        ax3.legend(loc='upper left')
        ax3_twin.legend(loc='upper right')
        ax3.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            logger.info(f"图表已保存: {save_path}")
        
        plt.show()


# ============================================
# 使用示例和测试
# ============================================

def generate_test_data(periods: int = 10000, volatility: float = 0.02) -> pd.DataFrame:
    """生成测试数据"""
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=periods, freq='1min')
    
    # 生成价格路径 (随机游走 + 均值回归)
    returns = np.random.normal(0, volatility, periods)
    # 添加均值回归成分
    for i in range(1, periods):
        if i % 1000 < 500:  # 前半段趋势
            returns[i] += 0.0001
        else:  # 后半段震荡
            returns[i] -= 0.00005
    
    prices = 40000 * np.exp(np.cumsum(returns))
    
    df = pd.DataFrame({
        'open': prices * (1 + np.random.normal(0, 0.001, periods)),
        'high': prices * (1 + abs(np.random.normal(0, 0.01, periods))),
        'low': prices * (1 - abs(np.random.normal(0, 0.01, periods))),
        'close': prices,
        'volume': np.random.normal(100, 20, periods)
    }, index=dates)
    
    return df


def main():
    """主函数 - 示例运行"""
    # 生成测试数据
    print("生成测试数据...")
    df = generate_test_data(periods=20000, volatility=0.015)
    
    # 初始化策略
    strategy = DynamicGridStrategyV4(
        initial_capital=10000,
        symbol="BTCUSDT",
        grid_levels=10,
        rsi_weight=0.4,
        rsi_oversold=35,
        rsi_overbought=65,
        adaptive_rsi=True,
        use_trend_filter=True,
        use_kelly_sizing=True,
        trailing_stop=True
    )
    
    # 运行回测
    results = strategy.run_backtest(df, verbose=True)
    
    # 打印报告
    strategy.print_report(results)
    
    # 绘制图表
    strategy.plot_results(save_path='/mnt/kimi/output/strategy_v4_results.png')
    
    return strategy, results


if __name__ == "__main__":
    strategy, results = main()