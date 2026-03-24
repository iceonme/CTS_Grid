"""
鍔ㄦ€佺綉鏍间氦鏄撶瓥鐣?V4.0 - RSI澧炲己鐗?
浣滆€? AI Assistant
鏃ユ湡: 2024
鍔熻兘: 鍩轰簬RSI鎸囨爣鐨勫姩鎬佺綉鏍间氦鏄撶郴缁燂紝鏀寔鍥炴祴鍜屾ā鎷熶氦鏄?
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

# 璁剧疆鏃ュ織
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """甯傚満鐘舵€佹灇涓?""
    TRENDING_UP = "涓婃定瓒嬪娍"
    TRENDING_DOWN = "涓嬭穼瓒嬪娍"
    RANGING = "闇囪崱鍖洪棿"
    UNKNOWN = "鏈煡"


@dataclass
class Trade:
    """浜ゆ槗璁板綍鏁版嵁绫?""
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
    """鎸佷粨鏁版嵁绫?""
    entry_price: float
    size: float
    grid_level: float
    entry_time: datetime
    stop_loss_price: float


class DynamicGridStrategyV4:
    """
    V4.0 鍔ㄦ€佺綉鏍肩瓥鐣?- RSI澧炲己鐗?
    
    鏍稿績鐗规€?
    1. 鑷€傚簲RSI鍙傛暟 (鏍规嵁娉㈠姩鐜囧姩鎬佽皟鏁撮槇鍊?
    2. 澶氭椂闂存鏋惰秼鍔胯瘑鍒?(ADX + 鍧囩嚎)
    3. 鍑埄鍏紡鍔ㄦ€佷粨浣嶇鐞?
    4. 鏅鸿兘缃戞牸鍋忕Щ (RSI淇″彿鍔犳潈)
    5. 鍒嗗眰姝㈡崯鏈哄埗
    6. 甯傚満鐘舵€佽瘑鍒笌绛栫暐鍒囨崲
    """
    
    def __init__(self, 
                 # 鍩虹鍙傛暟
                 initial_capital: float = 10000.0,
                 symbol: str = "BTCUSDT",
                 
                 # 缃戞牸鍙傛暟
                 grid_levels: int = 10,
                 grid_refresh_period: int = 100,  # 澶氬皯鏍筀绾垮埛鏂扮綉鏍?
                 grid_buffer_pct: float = 0.1,    # 缃戞牸缂撳啿甯︽瘮渚?
                 
                 # RSI鍙傛暟
                 rsi_period: int = 14,
                 rsi_weight: float = 0.4,         # RSI瀵圭綉鏍艰皟鏁寸殑褰卞搷鏉冮噸
                 rsi_oversold: float = 35,        # 瓒呭崠闃堝€?
                 rsi_overbought: float = 65,      # 瓒呬拱闃堝€?
                 rsi_extreme_buy: float = 80,     # 鏋佺瓒呬拱鏆傚仠涔板叆
                 rsi_extreme_sell: float = 20,    # 鏋佺瓒呭崠鏆傚仠鍗栧嚭
                 adaptive_rsi: bool = True,       # 鏄惁鍚敤鑷€傚簲RSI闃堝€?
                 
                 # 瓒嬪娍杩囨护鍙傛暟
                 use_trend_filter: bool = True,
                 adx_period: int = 14,
                 adx_threshold: float = 25,       # ADX > 25 璁や负鏈夎秼鍔?
                 ma_period: int = 50,             # 鍧囩嚎鍛ㄦ湡
                 
                 # 浠撲綅绠＄悊鍙傛暟
                 base_position_pct: float = 0.1,  # 鍩虹浠撲綅姣斾緥 (1/N)
                 max_positions: int = 5,          # 鏈€澶ф寔浠撳眰鏁?
                 use_kelly_sizing: bool = True,   # 鏄惁浣跨敤鍑埄鍏紡
                 kelly_fraction: float = 0.3,     # 鍑埄鍏紡淇濆畧绯绘暟 (鍗婂嚡鍒?
                 max_position_multiplier: float = 2.0,  # 鏈€澶т粨浣嶅€嶆暟
                 min_position_multiplier: float = 0.5,  # 鏈€灏忎粨浣嶅€嶆暟
                 
                 # 姝㈡崯鍙傛暟
                 stop_loss_pct: float = 0.05,     # 鍩虹姝㈡崯姣斾緥
                 trailing_stop: bool = True,      # 鏄惁鍚敤绉诲姩姝㈡崯
                 trailing_stop_pct: float = 0.03, # 绉诲姩姝㈡崯姣斾緥
                 
                 # 鍛ㄦ湡绠＄悊鍙傛暟
                 cycle_reset_period: int = 5000,  # 寮哄埗閲嶇疆鍛ㄦ湡 (K绾挎暟)
                 max_drawdown_reset: float = 0.30, # 鏈€澶у洖鎾よЕ鍙戦噸缃?
                 
                 # 浜ゆ槗璐圭敤
                 maker_fee: float = 0.001,        # 鎸傚崟鎵嬬画璐?0.1%
                 taker_fee: float = 0.001,        # 鍚冨崟鎵嬬画璐?0.1%
                 ):
        
        # 淇濆瓨鍙傛暟
        self.params = {k: v for k, v in locals().items() if k != 'self'}
        
        # 璐︽埛鐘舵€?
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.symbol = symbol
        
        # 缃戞牸鐘舵€?
        self.grid_upper = None
        self.grid_lower = None
        self.grid_prices = []
        self.last_grid_update = 0
        
        # 鎸佷粨鍜屼氦鏄撹褰?
        self.positions: List[Position] = []
        self.trades: List[Trade] = []
        self.equity_curve = []
        
        # 缁熻鎸囨爣
        self.win_count = 0
        self.loss_count = 0
        self.total_pnl = 0.0
        
        # 甯傚満鐘舵€?
        self.current_regime = MarketRegime.UNKNOWN
        self.current_rsi = 50.0
        self.current_adx = 0.0
        
        logger.info(f"绛栫暐V4.0鍒濆鍖栧畬鎴?- 浜ゆ槗瀵? {symbol}, 鍒濆璧勯噾: ${initial_capital:,.2f}")
    
    def calculate_rsi(self, prices: pd.Series, period: int = None) -> float:
        """璁＄畻RSI鎸囨爣"""
        period = period or self.params['rsi_period']
        if len(prices) < period + 1:
            return 50.0
        
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        # 澶勭悊闄ら浂
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        
        return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50.0
    
    def calculate_adx(self, high: pd.Series, low: pd.Series, close: pd.Series) -> float:
        """璁＄畻ADX瓒嬪娍寮哄害鎸囨爣"""
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
        """璇嗗埆甯傚満鐘舵€?""
        if not self.params['use_trend_filter'] or len(df) < self.params['ma_period']:
            return MarketRegime.RANGING
        
        # 璁＄畻ADX
        self.current_adx = self.calculate_adx(df['high'], df['low'], df['close'])
        
        # 璁＄畻鍧囩嚎
        ma = df['close'].rolling(window=self.params['ma_period']).mean().iloc[-1]
        current_price = df['close'].iloc[-1]
        
        # 鍒ゆ柇瓒嬪娍
        if self.current_adx > self.params['adx_threshold']:
            if current_price > ma * 1.02:  # 浠锋牸鏄捐憲楂樹簬鍧囩嚎
                return MarketRegime.TRENDING_UP
            elif current_price < ma * 0.98:  # 浠锋牸鏄捐憲浣庝簬鍧囩嚎
                return MarketRegime.TRENDING_DOWN
        
        return MarketRegime.RANGING
    
    def get_adaptive_rsi_thresholds(self, df: pd.DataFrame) -> Tuple[float, float]:
        """鑾峰彇鑷€傚簲RSI闃堝€?""
        if not self.params['adaptive_rsi']:
            return self.params['rsi_oversold'], self.params['rsi_overbought']
        
        # 鍩轰簬杩戞湡娉㈠姩鐜囪皟鏁撮槇鍊?
        returns = df['close'].pct_change().dropna()
        volatility = returns.std() * np.sqrt(1440)  # 骞村寲娉㈠姩鐜?(鍋囪1鍒嗛挓绾?
        
        # 楂樻尝鍔ㄦ椂鏀惧闃堝€硷紝浣庢尝鍔ㄦ椂鏀剁揣
        base_oversold = self.params['rsi_oversold']
        base_overbought = self.params['rsi_overbought']
        
        # 娉㈠姩鐜囪皟鏁村洜瀛?(鍋囪姝ｅ父娉㈠姩鐜?50%)
        vol_factor = min(max(volatility / 0.5, 0.5), 2.0)
        
        adjusted_oversold = max(20, min(40, base_oversold / vol_factor))
        adjusted_overbought = min(80, max(60, 100 - (100 - base_overbought) / vol_factor))
        
        return adjusted_oversold, adjusted_overbought
    
    def get_rsi_signal(self, rsi: float, oversold: float, overbought: float) -> float:
        """
        灏哛SI杞崲涓?[-1, 1] 淇″彿
        -1: 寮虹儓鐪嬬┖ (瓒呬拱)
        +1: 寮虹儓鐪嬪 (瓒呭崠)
        """
        if rsi <= oversold:
            return 1.0
        elif rsi >= overbought:
            return -1.0
        else:
            # 绾挎€ф彃鍊?
            mid = 50
            if rsi < mid:
                return (mid - rsi) / (mid - oversold) * 0.5
            else:
                return (mid - rsi) / (overbought - mid) * 0.5
    
    def calculate_dynamic_grid(self, df: pd.DataFrame) -> Tuple[float, float]:
        """璁＄畻鍔ㄦ€佺綉鏍煎尯闂?""
        lookback = min(self.params['grid_refresh_period'], len(df))
        recent_data = df.iloc[-lookback:]
        
        recent_high = recent_data['high'].max()
        recent_low = recent_data['low'].min()
        
        # 娣诲姞缂撳啿甯?
        range_size = recent_high - recent_low
        buffer = range_size * self.params['grid_buffer_pct']
        
        upper = recent_high + buffer
        lower = recent_low - buffer
        
        # 鏍规嵁RSI璋冩暣缃戞牸浣嶇疆
        if self.params['rsi_weight'] > 0:
            oversold, overbought = self.get_adaptive_rsi_thresholds(df)
            rsi_signal = self.get_rsi_signal(self.current_rsi, oversold, overbought)
            
            # 缃戞牸鍋忕Щ
            shift = range_size * rsi_signal * self.params['rsi_weight'] * 0.2
            upper += shift
            lower += shift
        
        return upper, lower
    
    def calculate_position_size(self, rsi_signal: float, is_buy: bool) -> float:
        """璁＄畻鍔ㄦ€佷粨浣嶅ぇ灏?""
        base_size = self.current_capital * self.params['base_position_pct']
        
        # 鏍规嵁甯傚満鐘舵€佽皟鏁?
        regime_multiplier = 1.0
        if self.current_regime == MarketRegime.TRENDING_UP and is_buy:
            regime_multiplier = 0.7  # 涓婃定瓒嬪娍鍑忓皯涔板叆
        elif self.current_regime == MarketRegime.TRENDING_DOWN and not is_buy:
            regime_multiplier = 0.7  # 涓嬭穼瓒嬪娍鍑忓皯鍗栧嚭(鍗冲噺灏戦€嗗娍鎿嶄綔)
        
        # RSI淇″彿璋冩暣
        if self.params['use_kelly_sizing']:
            # 绠€鍖栧嚡鍒╁叕寮? f = (p*b - q)/b
            # 鍋囪鑳滅巼涓嶳SI鏋佺绋嬪害鐩稿叧
            if is_buy:
                win_prob = 0.5 + rsi_signal * 0.2  # 瓒呭崠鏃惰儨鐜囨洿楂?
            else:
                win_prob = 0.5 - rsi_signal * 0.2  # 瓒呬拱鏃惰儨鐜囨洿楂?
            
            win_prob = np.clip(win_prob, 0.3, 0.8)
            loss_prob = 1 - win_prob
            avg_win = avg_loss = 1.0  # 绠€鍖栧亣璁?
            
            kelly_pct = (win_prob * avg_win - loss_prob * avg_loss) / avg_win
            kelly_pct = max(0, kelly_pct) * self.params['kelly_fraction']
            
            rsi_multiplier = 1 + kelly_pct
        else:
            # 绠€鍗曠嚎鎬ц皟鏁?
            if is_buy:
                rsi_multiplier = 1 + rsi_signal * 0.5  # 瓒呭崠鏃跺姞浠?
            else:
                rsi_multiplier = 1 - rsi_signal * 0.5  # 瓒呬拱鏃跺姞浠撳崠鍑?
            
            rsi_multiplier = np.clip(
                rsi_multiplier, 
                self.params['min_position_multiplier'],
                self.params['max_position_multiplier']
            )
        
        final_size = base_size * regime_multiplier * rsi_multiplier
        return min(final_size, self.current_capital * 0.95)  # 淇濈暀5%鐜伴噾
    
    def check_stop_loss(self, current_price: float, current_time: datetime) -> List[Trade]:
        """妫€鏌ュ苟鎵ц姝㈡崯"""
        executed_stops = []
        
        for pos in self.positions[:]:
            # 璁＄畻姝㈡崯浠锋牸
            if self.params['trailing_stop']:
                # 绉诲姩姝㈡崯: 浠庢渶楂樼偣鍥炴挙trailing_stop_pct
                highest_price = max(pos.entry_price, current_price)  # 绠€鍖栧鐞?
                stop_price = highest_price * (1 - self.params['trailing_stop_pct'])
                effective_stop = max(pos.stop_loss_price, stop_price)
            else:
                effective_stop = pos.stop_loss_price
            
            if current_price <= effective_stop:
                # 鎵ц姝㈡崯
                pnl = (current_price - pos.entry_price) / pos.entry_price * pos.size
                pnl -= pos.size * self.params['taker_fee']  # 鎵ｉ櫎鎵嬬画璐?
                
                self.current_capital += pos.size + pnl
                
                trade = Trade(
                    timestamp=current_time,
                    type='stop_loss',
                    price=current_price,
                    size=pos.size,
                    pnl=pnl,
                    rsi=self.current_rsi,
                    grid_level=pos.grid_level,
                    reason=f"姝㈡崯瑙﹀彂 (姝㈡崯浠? ${effective_stop:.2f})"
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
        """鎵ц涔板叆"""
        if size > self.current_capital * 0.95:
            return None
        
        # 鎵ｉ櫎鎵嬬画璐?
        fee = size * self.params['taker_fee']
        actual_size = size - fee
        
        self.current_capital -= size
        
        # 鍒涘缓鎸佷粨
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
        """鎵ц鍗栧嚭"""
        pnl = (price - position.entry_price) / position.entry_price * position.size
        pnl -= position.size * self.params['taker_fee']  # 鎵ｉ櫎鎵嬬画璐?
        
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
        """鍒ゆ柇鏄惁搴旈噸缃懆鏈?""
        # 妫€鏌ュ己鍒堕噸缃懆鏈?
        if current_idx - self.last_grid_update >= self.params['cycle_reset_period']:
            return True, "杈惧埌寮哄埗閲嶇疆鍛ㄦ湡"
        
        # 妫€鏌ユ渶澶у洖鎾?
        if len(self.equity_curve) > 0:
            recent_equity = [e['equity'] for e in self.equity_curve[-1000:]]
            peak = max(recent_equity)
            current = recent_equity[-1]
            drawdown = (current - peak) / peak
            
            if drawdown <= -self.params['max_drawdown_reset']:
                return True, f"瑙﹀彂鏈€澶у洖鎾ら檺鍒?({drawdown:.2%})"
        
        return False, ""
    
    def reset_cycle(self, df: pd.DataFrame, current_idx: int):
        """閲嶇疆浜ゆ槗鍛ㄦ湡"""
        logger.info(f"鍛ㄦ湡閲嶇疆 - 鍘熷洜: {self.should_reset_cycle(current_idx)[1]}")
        
        # 骞虫帀鎵€鏈夋寔浠?
        current_price = df['close'].iloc[current_idx]
        current_time = df.index[current_idx]
        
        for pos in self.positions[:]:
            self.execute_sell(pos, current_price, current_time, "鍛ㄦ湡閲嶇疆骞充粨")
        
        # 閲嶇疆缃戞牸
        self.grid_upper = None
        self.grid_lower = None
        self.last_grid_update = current_idx
        
        logger.info(f"閲嶇疆瀹屾垚 - 褰撳墠璧勯噾: ${self.current_capital:,.2f}")
    
    def run_backtest(self, df: pd.DataFrame, verbose: bool = True) -> Dict:
        """
        杩愯鍥炴祴
        
        Parameters:
        -----------
        df : pd.DataFrame
            鍖呭惈鍒? open, high, low, close, volume (鍙€?
        verbose : bool
            鏄惁鎵撳嵃杩涘害
            
        Returns:
        --------
        Dict : 鍥炴祴缁撴灉缁熻
        """
        logger.info(f"寮€濮嬪洖娴?- 鏁版嵁閲? {len(df)} 鏍筀绾?)
        
        # 纭繚鏁版嵁鍖呭惈蹇呰鍒?
        required_cols = ['open', 'high', 'low', 'close']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"缂哄皯蹇呰鍒? {col}")
        
        # 璁＄畻鎶€鏈寚鏍?
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
            
            # 鏇存柊甯傚満鐘舵€?
            self.current_regime = self.detect_market_regime(df.iloc[:i])
            
            # 妫€鏌ュ懆鏈熼噸缃?
            should_reset, reset_reason = self.should_reset_cycle(i)
            if should_reset:
                self.reset_cycle(df, i)
            
            # 鏇存柊缃戞牸
            if i - self.last_grid_update >= self.params['grid_refresh_period'] or self.grid_upper is None:
                self.grid_upper, self.grid_lower = self.calculate_dynamic_grid(df.iloc[:i])
                self.grid_prices = np.linspace(self.grid_lower, self.grid_upper, self.params['grid_levels'])
                self.last_grid_update = i
            
            # 妫€鏌ユ鎹?
            self.check_stop_loss(current_price, current_time)
            
            # 鑾峰彇鑷€傚簲闃堝€?
            oversold, overbought = self.get_adaptive_rsi_thresholds(df.iloc[:i])
            rsi_signal = self.get_rsi_signal(self.current_rsi, oversold, overbought)
            
            # 鎵ц缃戞牸浜ゆ槗
            for grid_price in self.grid_prices:
                # 涔板叆鏉′欢: 浠锋牸涓嬬┛缃戞牸绾?
                if (df['low'].iloc[i-1] > grid_price and current_low <= grid_price):
                    if len(self.positions) < self.params['max_positions']:
                        # RSI杩囨护: 鏋佺瓒呬拱鏃舵殏鍋滀拱鍏?
                        if self.current_rsi < self.params['rsi_extreme_buy']:
                            size = self.calculate_position_size(rsi_signal, is_buy=True)
                            if size > 100:  # 鏈€灏忎氦鏄撻噾棰?
                                self.execute_buy(
                                    current_price, size, grid_price, current_time,
                                    f"缃戞牸涔板叆 (RSI: {self.current_rsi:.1f})"
                                )
                
                # 鍗栧嚭鏉′欢: 浠锋牸涓婄┛缃戞牸绾夸笖鏈夌泩鍒╂寔浠?
                if (df['high'].iloc[i-1] < grid_price and current_high >= grid_price):
                    for pos in self.positions[:]:
                        if pos.entry_price < current_price * 0.995:  # 鑷冲皯0.5%鐩堝埄
                            # RSI杩囨护: 鏋佺瓒呭崠鏃舵殏鍋滃崠鍑?鍙兘鍙嶅脊)
                            if self.current_rsi > self.params['rsi_extreme_sell']:
                                self.execute_sell(
                                    pos, current_price, current_time,
                                    f"缃戞牸鍗栧嚭 (RSI: {self.current_rsi:.1f})"
                                )
                                break  # 鍙崠鍑轰竴灞?
            
            # 璁板綍鏉冪泭
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
            
            # 鎵撳嵃杩涘害
            if verbose and i % 5000 == 0:
                progress = (i - start_idx) / (len(df) - start_idx) * 100
                logger.info(f"鍥炴祴杩涘害: {progress:.1f}% - 褰撳墠鏉冪泭: ${total_equity:,.2f}")
        
        return self.get_results()
    
    def get_results(self) -> Dict:
        """鑾峰彇鍥炴祴缁撴灉缁熻"""
        if len(self.equity_curve) == 0:
            return {}
        
        equity_df = pd.DataFrame(self.equity_curve)
        
        # 鍩虹鎸囨爣
        total_return = (equity_df['equity'].iloc[-1] - self.initial_capital) / self.initial_capital
        
        # 鏈€澶у洖鎾?
        equity_df['peak'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['peak']) / equity_df['peak']
        max_drawdown = equity_df['drawdown'].min()
        
        # 澶忔櫘姣旂巼 (绠€鍖栫増锛屽亣璁炬棤椋庨櫓鍒╃巼涓?)
        returns = equity_df['equity'].pct_change().dropna()
        sharpe_ratio = returns.mean() / returns.std() * np.sqrt(525600) if returns.std() != 0 else 0
        
        # 浜ゆ槗缁熻
        buy_trades = [t for t in self.trades if t.type == 'buy']
        sell_trades = [t for t in self.trades if t.type == 'sell']
        stop_trades = [t for t in self.trades if t.type == 'stop_loss']
        
        winning_sells = [t for t in sell_trades if t.pnl > 0]
        win_rate = len(winning_sells) / len(sell_trades) if sell_trades else 0
        
        avg_win = np.mean([t.pnl for t in winning_sells]) if winning_sells else 0
        losing_sells = [t for t in sell_trades if t.pnl <= 0]
        avg_loss = np.mean([t.pnl for t in losing_sells]) if losing_sells else 0
        
        # 鐩堜簭姣?
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
        """鎵撳嵃鍥炴祴鎶ュ憡"""
        if results is None:
            results = self.get_results()
        
        print("\n" + "=" * 80)
        print("鍔ㄦ€佺綉鏍肩瓥鐣?V4.0 - 鍥炴祴鎶ュ憡")
        print("=" * 80)
        
        print(f"\n銆愬熀纭€淇℃伅銆?)
        print(f"浜ゆ槗瀵? {self.symbol}")
        print(f"鍥炴祴鍛ㄦ湡: {len(self.equity_curve)} 鏍筀绾?)
        print(f"鍒濆璧勯噾: ${results['initial_capital']:,.2f}")
        print(f"鏈€缁堟潈鐩? ${results['final_equity']:,.2f}")
        
        print(f"\n銆愭敹鐩婃寚鏍囥€?)
        print(f"鎬绘敹鐩婄巼: {results['total_return']:.2%}")
        print(f"鏈€澶у洖鎾? {results['max_drawdown']:.2%}")
        print(f"澶忔櫘姣旂巼: {results['sharpe_ratio']:.2f}")
        
        print(f"\n銆愪氦鏄撶粺璁°€?)
        print(f"鎬讳氦鏄撴鏁? {results['total_trades']}")
        print(f"涔板叆娆℃暟: {results['buy_count']}")
        print(f"鍗栧嚭娆℃暟: {results['sell_count']}")
        print(f"姝㈡崯娆℃暟: {results['stop_loss_count']}")
        print(f"鑳滅巼: {results['win_rate']:.2%}")
        print(f"鐩堜簭姣? {results['profit_factor']:.2f}")
        print(f"骞冲潎鐩堝埄: ${results['avg_win']:,.2f}")
        print(f"骞冲潎浜忔崯: ${results['avg_loss']:,.2f}")
        
        print(f"\n銆愮瓥鐣ュ弬鏁般€?)
        for key, value in list(results['params'].items())[:10]:
            print(f"  {key}: {value}")
        
        print("=" * 80)
    
    def plot_results(self, save_path: str = None):
        """缁樺埗鍥炴祴缁撴灉鍥捐〃"""
        if len(self.equity_curve) == 0:
            logger.warning("娌℃湁鏁版嵁鍙粯鍒?)
            return
        
        equity_df = pd.DataFrame(self.equity_curve)
        
        fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=True)
        
        # 1. 鏉冪泭鏇茬嚎鍜屼环鏍?
        ax1 = axes[0]
        ax1_twin = ax1.twinx()
        
        ax1.plot(equity_df['timestamp'], equity_df['equity'], 
                label='璐︽埛鏉冪泭', color='blue', linewidth=1.5)
        ax1.axhline(y=self.initial_capital, color='gray', linestyle='--', alpha=0.5)
        ax1.set_ylabel('鏉冪泭 (USDT)', color='blue')
        ax1.tick_params(axis='y', labelcolor='blue')
        
        # 閲囨牱鏄剧ず浠锋牸閬垮厤杩囦簬瀵嗛泦
        sample_idx = range(0, len(equity_df), max(1, len(equity_df)//1000))
        ax1_twin.plot(equity_df['timestamp'].iloc[sample_idx], 
                     equity_df['price'].iloc[sample_idx],
                     label='浠锋牸', color='gray', alpha=0.3, linewidth=0.5)
        ax1_twin.set_ylabel('浠锋牸', color='gray')
        ax1_twin.tick_params(axis='y', labelcolor='gray')
        
        ax1.set_title('鍔ㄦ€佺綉鏍肩瓥鐣?V4.0 - 鍥炴祴缁撴灉', fontsize=14, fontweight='bold')
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)
        
        # 2. 鍥炴挙
        ax2 = axes[1]
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['equity'].cummax()) / equity_df['equity'].cummax()
        ax2.fill_between(equity_df['timestamp'], equity_df['drawdown'], 0, 
                        alpha=0.5, color='red', label='鍥炴挙')
        ax2.set_ylabel('鍥炴挙姣斾緥')
        ax2.legend(loc='lower left')
        ax2.grid(True, alpha=0.3)
        
        # 3. RSI鍜屾寔浠?
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
                     label='鎸佷粨灞傛暟', color='orange', alpha=0.7)
        ax3_twin.set_ylabel('鎸佷粨灞傛暟', color='orange')
        
        ax3.legend(loc='upper left')
        ax3_twin.legend(loc='upper right')
        ax3.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            logger.info(f"鍥捐〃宸蹭繚瀛? {save_path}")
        
        plt.show()


# ============================================
# 浣跨敤绀轰緥鍜屾祴璇?
# ============================================

def generate_test_data(periods: int = 10000, volatility: float = 0.02) -> pd.DataFrame:
    """鐢熸垚娴嬭瘯鏁版嵁"""
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=periods, freq='1min')
    
    # 鐢熸垚浠锋牸璺緞 (闅忔満娓歌蛋 + 鍧囧€煎洖褰?
    returns = np.random.normal(0, volatility, periods)
    # 娣诲姞鍧囧€煎洖褰掓垚鍒?
    for i in range(1, periods):
        if i % 1000 < 500:  # 鍓嶅崐娈佃秼鍔?
            returns[i] += 0.0001
        else:  # 鍚庡崐娈甸渿鑽?
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
    """涓诲嚱鏁?- 绀轰緥杩愯"""
    # 鐢熸垚娴嬭瘯鏁版嵁
    print("鐢熸垚娴嬭瘯鏁版嵁...")
    df = generate_test_data(periods=20000, volatility=0.015)
    
    # 鍒濆鍖栫瓥鐣?
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
    
    # 杩愯鍥炴祴
    results = strategy.run_backtest(df, verbose=True)
    
    # 鎵撳嵃鎶ュ憡
    strategy.print_report(results)
    
    # 缁樺埗鍥捐〃
    strategy.plot_results(save_path='/mnt/kimi/output/strategy_v4_results.png')
    
    return strategy, results


if __name__ == "__main__":
    strategy, results = main()
