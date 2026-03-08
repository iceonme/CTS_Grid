import os
import json
import subprocess
import time

def run_test(resample, layers, drop, sl, tp):
    params = {
        "resample_min": resample,
        "grid_layers": layers,
        "grid_drop_pct": drop,
        "hard_sl_pct": sl,
        "tp_min_profit_pct": tp
    }
    
    cmd = [
        "python",
        "run_backtest_arena.py",
        "--strategy", "zen_7_1",
        "--params", json.dumps(params).replace('"', "'")
    ]
    
    print(f"Testing Resample:{resample}m, Layers:{layers}, Drop:{drop}, SL:{sl}, TP:{tp}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Parse output
    lines = result.stdout.split('\n')
    ret = 0
    win = 0
    trades = 0
    for line in lines:
        if "总收益率:" in line:
            ret = float(line.split(':')[1].replace('%', '').strip())
        if "胜率:" in line:
            win = float(line.split(':')[1].replace('%', '').strip())
        if "交易总数:" in line:
            trades = int(line.split(':')[1].strip())
            
    print(f"Result -> Return: {ret}%, WinRate: {win}%, Trades: {trades}")
    return {"ret": ret, "win": win, "trades": trades, "params": params}

if __name__ == "__main__":
    configs = [
        (30, 8, 0.02, -0.25, 0.02),
        (30, 10, 0.03, -0.30, 0.02),
        (30, 12, 0.02, -0.30, 0.015),
        (15, 10, 0.02, -0.25, 0.02),
        (15, 12, 0.03, -0.30, 0.015)
    ]
    
    results = []
    print("Starting Optimization Round 3 (Timeframe Tuning)...")
    for c in configs:
        res = run_test(*c)
        results.append(res)
        
    print("\n--- Best Results ---")
    results.sort(key=lambda x: x['ret'], reverse=True)
    for r in results:
        print(f"Return: {r['ret']:6.2f}% | Trades: {r['trades']:4d} | Params: {r['params']}")
