
import sys
import os
import numpy as np
from pathlib import Path

# 添加策略目录到路径
sys.path.append(r'c:\CS\grid_multi')

from strategies.grid_rsi_5_2 import GridEngine, StrategyState

def test_pivot_fix():
    params = {
        'pivot_window': 5,
        'pivot_n': 3,
        'pivot_lookback': 100,
        'grid_levels': 10,
        'grid_buffer_pct': 0.1,
        'grid_spacing_min': 0.003,
        'grid_spacing_max': 0.02,
        'rsi_weight': 0.4,
        'trend_shift_strong_u': 0.20, 'trend_shift_strong_l': 0.10,
        'trend_shift_weak_u': 0.10, 'trend_shift_weak_l': 0.05,
    }
    engine = GridEngine(params)
    state = StrategyState()
    
    # 模拟数据：120 根线
    # 放置 5 个低点和 5 个高点
    highs = np.ones(120) * 110
    lows = np.ones(120) * 100
    
    # 放置 5 个不同深度的低点
    low_indices = [25, 45, 65, 85, 105]
    low_prices = [80, 85, 90, 92, 95] # 80, 85, 90 是最显著的 3 个
    for idx, prc in zip(low_indices, low_prices):
        lows[idx] = prc
        highs[idx] = prc + 5
        
    # 放置 5 个不同高度的高点
    high_indices = [20, 40, 60, 80, 100]
    high_prices = [120, 118, 115, 112, 111] # 120, 118, 115 是最显著的 3 个
    for idx, prc in zip(high_indices, high_prices):
        highs[idx] = prc
        lows[idx] = prc - 5
        
    price = 105.0
    
    print(f"Testing with price={price}, lookback={params['pivot_lookback']}")
    upper, lower, meta = engine.calculate(highs, lows, price, state, 0.0)
    
    ph_count = len(meta['pivots_high'])
    pl_count = len(meta['pivots_low'])
    
    print(f"Calculated Upper: {upper:.2f}")
    print(f"Calculated Lower: {lower:.2f}")
    print(f"Found Pivot Highs: {ph_count}")
    print(f"Found Pivot Lows: {pl_count}")
    
    # 验证逻辑：点数不能超过 3
    if ph_count <= 3 and pl_count <= 3:
        print("SUCCESS: Pivot count limited to 3.")
    else:
        print(f"FAILURE: Too many pivots (H:{ph_count}, L:{pl_count}).")
        
    # 验证显著性：Lower 应该包含 80 这个全局最低点
    expected_low = min(low_prices)
    actual_low_pivot = min(p['price'] for p in meta['pivots_low'])
    if actual_low_pivot == expected_low:
        print(f"SUCCESS: Most significant low ({expected_low}) captured!")
    else:
        print(f"FAILURE: Significant low missed. Got {actual_low_pivot}")

if __name__ == "__main__":
    test_pivot_fix()
