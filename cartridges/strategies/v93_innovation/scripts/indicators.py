import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, field

@dataclass
class GridState:
    """网格运行状态数据类"""
    grid_top: float = 0.0
    grid_bottom: float = 0.0
    entity_grids: List[float] = field(default_factory=list) # [P0, P1, P2, P3]
    virtual_grids: List[float] = field(default_factory=list) # [VL, VH]
    daily_reset_count: int = 0
    breakout_triggered: bool = False
    breakout_time: Optional[datetime] = None
    last_reset_day: Optional[str] = None # YYYY-MM-DD
    last_grid_calc_time: Optional[str] = None

def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """计算标准 Wilder's RSI"""
    if len(prices) < period + 1:
        return 50.0
    
    s = pd.Series(prices)
    delta = s.diff()
    ups = delta.clip(lower=0)
    downs = -1 * delta.clip(upper=0)
    
    ma_up = ups.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    ma_down = downs.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    rs = ma_up / ma_down
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return float(val) if not np.isnan(val) else 50.0

def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """计算 ATR 波动率"""
    if len(df) < 2:
        return df['close'].iloc[-1] * 0.02 if not df.empty else 0.0
    
    recent = df.tail(min(period + 1, len(df)))
    high = recent['high']
    low = recent['low']
    prev_close = recent['close'].shift(1)
    
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    
    return tr.tail(period).mean()

def lstm_trend(price_history: List[float]) -> int:
    """轻量趋势判断: -1=空, 0=中, 1=多"""
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

def calculate_grids(df: pd.DataFrame, window_hours: int = 6) -> Dict[str, Any]:
    """计算 3实体 + 2虚拟网格"""
    lookback = window_hours * 60
    recent = df.tail(lookback)
    if recent.empty: return {}
    
    # 5段采样去极值
    seg_size = len(recent) // 5
    highs, lows = [], []
    for i in range(5):
        segment = recent.iloc[i*seg_size : (i+1)*seg_size if i<4 else len(recent)]
        if not segment.empty:
            highs.append(segment['high'].max())
            lows.append(segment['low'].min())
    
    grid_top = np.mean(np.sort(highs)[:-1]) if len(highs) >= 2 else recent['high'].max()
    grid_bottom = np.mean(np.sort(lows)[1:]) if len(lows) >= 2 else recent['low'].min()
    
    step = (grid_top - grid_bottom) / 3
    entity_grids = [grid_bottom, grid_bottom + step, grid_bottom + 2*step, grid_top]
    virtual_grids = [grid_bottom - step, grid_top + step]
    
    return {
        'grid_top': grid_top,
        'grid_bottom': grid_bottom,
        'entity_grids': entity_grids,
        'virtual_grids': virtual_grids,
        'calc_time': df.index[-1].isoformat()
    }

def get_current_layer(price: float, entity_grids: List[float], virtual_grids: List[float]) -> Optional[int]:
    """确定当前价格所在层级 (-1 到 3)"""
    if not entity_grids or not virtual_grids: return None
    if price < virtual_grids[0] or price > virtual_grids[1]: return None
    
    if price < entity_grids[0]: return -1
    elif price < entity_grids[1]: return 0
    elif price < entity_grids[2]: return 1
    elif price < entity_grids[3]: return 2
    else: return 3

def check_reset_conditions(state: GridState, current_price: float, current_time: datetime) -> Tuple[bool, int]:
    """检查重置条件控制逻辑"""
    # 跨天恢复配额 (北京时间 UTC+8)
    cst_time = current_time + timedelta(hours=8)
    current_day_str = cst_time.strftime('%Y-%m-%d')
    
    if state.last_reset_day != current_day_str:
        state.last_reset_day = current_day_str
        state.daily_reset_count = 0
        state.breakout_triggered = False
        
    if state.daily_reset_count >= 2: return False, 6
    if not state.virtual_grids: return True, 6 # 首次计算
    
    is_outside = current_price < state.virtual_grids[0] or current_price > state.virtual_grids[1]
    
    if not state.breakout_triggered:
        if is_outside:
            state.breakout_triggered = True
            state.breakout_time = current_time
    else:
        if not is_outside:
            state.breakout_triggered = False
        else:
            elapsed = (current_time - state.breakout_time).total_seconds()
            if elapsed >= 2 * 3600:
                state.breakout_triggered = False
                state.daily_reset_count += 1
                return True, 4 # 紧急重置，收缩窗口
                
    return False, 6
