import os
import json
import subprocess
import random
import time
import sys

# --- Configuration ---
STRATEGY = "zen_7_1"
DATA = "data/btc_1m_2025.csv"
MAX_ITER = 30
LOG_FILE = "optimizer/evolution_progress.json"

# Ranges
PARAM_SPACE = {
    "resample_min": [30, 60, 90, 120],
    "grid_layers": [6, 8, 10, 12, 14, 16],
    "grid_drop_pct": [0.02, 0.025, 0.03, 0.035, 0.04, 0.045],
    "hard_sl_pct": [-0.15, -0.20, -0.25, -0.30],
    "tp_min_profit_pct": [0.015, 0.02, 0.025, 0.03, 0.035]
}

def load_checkpoint():
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

def save_checkpoint(history, best):
    with open(LOG_FILE, 'w') as f:
        json.dump({"best": best, "history": history}, f, indent=4)

def run_backtest(params):
    param_str = json.dumps(params).replace('"', "'")
    cmd = ["python", "run_backtest_arena.py", "--strategy", STRATEGY, "--params", param_str, "--data", DATA]
    
    print(f"  [Eval] Params: {params}")
    try:
        # Avoid capture_output=True to prevent buffering issues
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
        stdout = result.stdout
        
        # Parse output
        ret, mdd, sharpe, win, trades = 0.0, 0.0, 0.0, 0.0, 0
        
        for line in stdout.split('\n'):
            if "总收益率:" in line:
                ret = float(line.split(':')[1].replace('%', '').strip()) / 100.0
            if "最大回撤:" in line:
                mdd = float(line.split(':')[1].replace('%', '').strip()) / 100.0
            if "夏普比率:" in line:
                sharpe = float(line.split(':')[1].strip())
            if "胜率:" in line:
                win = float(line.split(':')[1].replace('%', '').strip()) / 100.0
            if "交易总数:" in line:
                trades = int(line.split(':')[1].strip())
        
        # Sharper Score: (Return / (DD + 0.1)) * (Sharpe + 0.5)
        # We target 30% return.
        score = (ret * 100.0) * (sharpe + 0.5) / (mdd * 100.0 + 5.0)
        
        if trades < 30: score *= 0.1
        
        return {
            "ret": round(ret, 4), "mdd": round(mdd, 4), "sharpe": round(sharpe, 4), 
            "win": round(win, 4), "trades": trades, "score": round(score, 4), "params": params
        }
    except Exception as e:
        print(f"  [Error] {e}")
        return None

def get_random_params():
    return {k: random.choice(v) for k, v in PARAM_SPACE.items()}

def mutate_params(current):
    new_params = current.copy()
    key = random.choice(list(PARAM_SPACE.keys()))
    new_params[key] = random.choice(PARAM_SPACE[key])
    return new_params

def main():
    checkpoint = load_checkpoint()
    history = checkpoint["history"] if checkpoint else []
    best_res = checkpoint["best"] if checkpoint else None
    start_iter = len(history) + 1
    
    print(f"=== Zen 7.1 Robust Evolution (Starting at {start_iter}) ===")
    
    for i in range(start_iter, MAX_ITER + 1):
        print(f"\n[Iteration {i}/{MAX_ITER}]")
        
        # Search strategy
        if i % 5 == 0 or i == 1:
            candidate = get_random_params()
        elif best_res:
            candidate = mutate_params(best_res["params"])
        else:
            candidate = get_random_params()
            
        res = run_backtest(candidate)
        if not res: continue
        
        history.append(res)
        
        if best_res is None or res["score"] > best_res["score"]:
            best_res = res
            print(f"  [NEW BEST] Score: {res['score']} | Ret: {res['ret']*100}% | DD: {res['mdd']*100}% | Sharpe: {res['sharpe']}")
        else:
            print(f"  [Skip] Score: {res['score']} (Best: {best_res['score']})")
        
        save_checkpoint(history, best_res)
        
    print("\n" + "="*50)
    print("EVOLUTION COMPLETED")
    if best_res:
        print(f"Best Params: {best_res['params']}")
        print(f"Result: {best_res['ret']*100:.2f}% Return | {best_res['sharpe']} Sharpe")
    print("="*50)

if __name__ == "__main__":
    main()
