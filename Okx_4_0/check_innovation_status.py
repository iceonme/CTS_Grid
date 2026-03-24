import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# 路径设置
sys.path.insert(0, os.path.join(os.getcwd(), 'ethswap'))

from ethswap.config.api_config import OKX_CONFIG
from ethswap.config.okx_config import OKXAPI

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)[-period:]
    losses = np.where(deltas < 0, -deltas, 0)[-period:]
    avg_gain = np.mean(gains) if len(gains) > 0 else 0
    avg_loss = np.mean(losses) if len(losses) > 0 else 0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_atr(df, period=14):
    if len(df) < 2:
        return df['close'].iloc[-1] * 0.02
    recent = df.tail(min(period, len(df)))
    tr_list = []
    for i in range(1, len(recent)):
        high = recent['high'].iloc[i]; low = recent['low'].iloc[i]; prev_close = recent['close'].iloc[i-1]
        tr = max(high-low, abs(high-prev_close), abs(low-prev_close))
        tr_list.append(tr)
    return np.mean(tr_list)

def get_trend(price_history):
    if len(price_history) < 60: return 0
    recent = price_history[-60:]
    returns = np.diff(recent) / recent[:-1]
    momentum = np.mean(returns) * 100
    volatility = np.std(returns) * 100
    if momentum > volatility * 0.5 and momentum > 0.02: return 1
    elif momentum < -volatility * 0.5 and momentum < -0.02: return -1
    return 0

def main():
    api = OKXAPI(
        api_key=OKX_CONFIG['api_key'],
        api_secret=OKX_CONFIG['api_secret'],
        passphrase=OKX_CONFIG['passphrase'],
        is_demo=True
    )
    
    # 1. 获取最近 K 线
    df = api.get_candles(limit=400)
    if df is None or df.empty:
        print("Error: Could not fetch candles")
        return
        
    current_price = df['close'].iloc[-1]
    last_ts = df.index[-1]
    price_history = df['close'].values
    rsi = calculate_rsi(price_history)
    atr = calculate_atr(df)
    trend = get_trend(price_history)
    
    # 2. 计算网格 (3层实体: P0, P1, P2, P3)
    lookback = 360
    recent = df.tail(lookback)
    highs = recent['high'].nlargest(5).values
    lows = recent['low'].nsmallest(5).values
    grid_top = np.mean(np.sort(highs)[1:])
    grid_bottom = np.mean(np.sort(lows)[:-1])
    
    step = (grid_top - grid_bottom) / 3
    entity_grids = [
        grid_bottom,              # P0
        grid_bottom + step,       # P1
        grid_bottom + 2 * step,   # P2
        grid_top                  # P3
    ]
    virtual_grids = [grid_bottom - step, grid_top + step]
    
    # 动态 RSI 阈值
    if abs(trend) >= 1:
        rsi_oversold, rsi_overbought = 30.0, 80.0
        rsi_exit_oversold, rsi_exit_overbought = 45.0, 65.0
    else:
        rsi_oversold, rsi_overbought = 25.0, 85.0
        rsi_exit_oversold, rsi_exit_overbought = 40.0, 70.0

    # 3. 确定层级 (5层空间)
    layer = None
    if current_price < virtual_grids[0]: layer = None
    elif current_price < entity_grids[0]: layer = -1 # 虚拟低
    elif current_price < entity_grids[1]: layer = 0  # 底层实体
    elif current_price < entity_grids[2]: layer = 1  # 中层实体
    elif current_price < entity_grids[3]: layer = 2  # 高层实体
    elif current_price < virtual_grids[1]: layer = 3 # 虚拟高
            
    # 4. 输出分析
    print("-" * 40)
    print(f"策略版本: V9.3-Innovation (修正版)")
    print(f"数据时间: {last_ts}")
    print(f"当前价格: {current_price:.2f}")
    print(f"当前 RSI: {rsi:.2f} | 趋势: {trend}")
    print(f"RSI 阈值: 入场 {rsi_oversold}/{rsi_overbought} | 止盈 {rsi_exit_oversold}/{rsi_exit_overbought}")
    print(f"实体区间: [{grid_bottom:.2f} (P0) ↔ {grid_top:.2f} (P3)] | 步长: {step:.2f}")
    print(f"虚拟边界: [{virtual_grids[0]:.2f}, {virtual_grids[1]:.2f}]")
    print(f"当前层级: {layer if layer is not None else '超出虚拟层'} (Zone {layer})")
    
    if layer is not None:
        if layer == 0: # 底层实体
            layer_mid = (entity_grids[0] + entity_grids[1]) / 2
            print(f"层 0 (底层实体) 中线: {layer_mid:.2f} | 逻辑: 做多 (需 RSI <= {rsi_oversold})")
            if current_price <= layer_mid:
                print(f"结论: 处于做多观察区")
                if rsi <= rsi_oversold: print(">>> 符合做多入场条件! <<<")
            else: print("结论: 处于底层上部，观望")
        elif layer == 2: # 高层实体
            layer_mid = (entity_grids[2] + entity_grids[3]) / 2
            print(f"层 2 (高层实体) 中线: {layer_mid:.2f} | 逻辑: 做空 (需 RSI >= {rsi_overbought})")
            if current_price >= layer_mid:
                print(f"结论: 处于做空观察区")
                if rsi >= rsi_overbought: print(">>> 符合做空入场条件! <<<")
            else: print("结论: 处于高层下部，观望")
        elif layer == 1:
            print("层 1 (中层实体) | 逻辑: 震荡缓冲/平仓区")
        elif layer == -1:
            print("层 -1 (虚拟低层) | 逻辑: 允许平空")
        elif layer == 3:
            print("层 3 (虚拟高层) | 逻辑: 允许平多")
    else:
        print("状态: 处于极端无网格模式")

if __name__ == "__main__":
    main()
