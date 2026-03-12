import os
import sys
# 自动处理路径 - 向上寻找项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)

import json
import os
import sys
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import pandas as pd

def plot_results(json_path: str):
    if not os.path.exists(json_path):
        print(f"File not found: {json_path}")
        return

    with open(json_path, 'r') as f:
        data = json.load(f)

    series = data.get('hourly_series', [])
    if not series:
        print("No hourly_series found in JSON.")
        return

    df = pd.DataFrame(series)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # 计算累计收益和回撤
    df['equity_pct'] = (df['equity'] / data['initial_capital'] - 1) * 100
    df['benchmark_pct'] = (df['benchmark'] / df['benchmark'].iloc[0] - 1) * 100
    
    peak = df['equity'].cummax()
    df['drawdown'] = (df['equity'] - peak) / peak * 100

    # 绘图配置
    plt.style.use('dark_background')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)
    fig.subplots_adjust(hspace=0.05)

    # --- 主图: 权益 vs 基准 ---
    color_equity = '#00ffc8'
    color_bench = '#ff9500'
    
    lns1 = ax1.plot(df['timestamp'], df['equity'], color=color_equity, linewidth=2, label='Strategy Equity (USDT)')
    ax1.set_ylabel('Account Value (USDT)', color=color_equity, fontsize=12)
    ax1.tick_params(axis='y', labelcolor=color_equity)
    ax1.grid(True, alpha=0.2)
    
    # 次坐标轴画价格
    ax1_bench = ax1.twinx()
    lns2 = ax1_bench.plot(df['timestamp'], df['benchmark'], color=color_bench, linewidth=1.5, alpha=0.6, linestyle='--', label='BTC Price (Benchmark)')
    ax1_bench.set_ylabel('BTC Price ($)', color=color_bench, fontsize=12)
    ax1_bench.tick_params(axis='y', labelcolor=color_bench)

    # 合并图例
    lns = lns1 + lns2
    labs = [l.get_label() for l in lns]
    ax1.legend(lns, labs, loc='upper left', frameon=True, framealpha=0.8)
    
    title = f"Backtest Results Analysis\n{os.path.basename(json_path)}"
    ax1.set_title(title, fontsize=16, pad=20, weight='bold')

    # --- 副图: 回撤 ---
    ax2.fill_between(df['timestamp'], df['drawdown'], 0, color='#ff3b30', alpha=0.3, label='Drawdown %')
    ax2.plot(df['timestamp'], df['drawdown'], color='#ff3b30', linewidth=1)
    ax2.set_ylabel('Drawdown %', color='#ff3b30')
    ax2.set_ylim(None, 0.5) # 给上方留一点点空间
    ax2.grid(True, alpha=0.2)
    ax2.legend(loc='lower left')

    # 格式化 X 轴
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax2.xaxis.set_major_locator(mdates.MonthLocator())
    plt.xticks(rotation=45)

    # 保存图片
    output_png = json_path.replace('.json', '.png')
    
    # 确保保存目录存在
    img_dir = "docs/assets/backtest"
    os.makedirs(img_dir, exist_ok=True)
    img_path = os.path.join(img_dir, os.path.basename(output_png))
    
    plt.savefig(img_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"\n[Visualizer] Plot saved to: {img_path}")
    return img_path

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python plot_arena_results.py <result_json>")
    else:
        plot_results(sys.argv[1])
