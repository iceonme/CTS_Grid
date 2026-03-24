"""
run_paper_trading.py - 瀹屾暣杩愯鑴氭湰
"""

import pandas as pd
import numpy as np
from datetime import datetime

# 瀵煎叆鑷畾涔夋ā鍧?
from paper_trading import MultiExchangePaperTrading, DataFeed
from grid_strategy import DynamicGridStrategyV4


def run_single_symbol_backtest(symbol='BTC/USDT', data_path='btc_1m.csv'):
    """鍗曞竵绉嶅洖娴?""
    print(f"\n{'='*60}")
    print(f"寮€濮嬪洖娴? {symbol}")
    print(f"{'='*60}")
    
    # 1. 鍔犺浇鏁版嵁
    try:
        df = pd.read_csv(data_path, index_col='timestamp', parse_dates=True)
        print(f"鏁版嵁鍔犺浇瀹屾垚: {len(df)} 鏉¤褰?)
    except Exception as e:
        print(f"鍔犺浇鏁版嵁澶辫触: {e}")
        return None, None
    
    # 2. 鍒濆鍖栨ā鎷熺洏
    paper = MultiExchangePaperTrading(
        initial_capital=10000,
        fee_rate=0.001,
        slippage_model='adaptive'
    )
    paper.set_latency(200)
    
    # 3. 鍒涘缓绛栫暐
    strategy = DynamicGridStrategyV4(
        initial_capital=10000,
        symbol=symbol,
        grid_levels=10,
        rsi_weight=0.4,
        rsi_oversold=35,
        rsi_overbought=65,
        adaptive_rsi=True,
        use_trend_filter=True,
        use_kelly_sizing=True,
        trailing_stop=True
    )
    
    # 4. 杩愯鍥炴祴
    print(f"\n杩愯妯℃嫙...")
    results = strategy.run_backtest(df, verbose=True)
    
    # 5. 鎵撳嵃鎶ュ憡
    strategy.print_report(results)
    
    return results, strategy


def run_okx_demo():
    """OKX妯℃嫙鐩樿繍琛岀ず渚?""
    try:
        from okx_config import OKXAPI, OKXDataFeed
        
        # 閰嶇疆API锛堜娇鐢ㄦā鎷熺洏锛?
        # 娉ㄦ剰锛歄KX API 蹇呴』鎻愪緵 Passphrase (API瀵嗙爜)
        okx = OKXAPI(
            api_key='72aac042-9859-48ec-8e27-9722524429a6',
            api_secret='CCFE2963EBD154027557D24CFA2CAA57',
            passphrase='Tonghua9527_', # OKX API 瀵嗙爜
            is_demo=True,
            simulate_slippage=True
        )
        
        # 鑾峰彇鍘嗗彶鏁版嵁
        df = okx.get_candles('BTC-USDT', '1m', 1000)
        print(f"鑾峰彇鏁版嵁: {len(df)} 鏉?)
        print(df.tail())
        
        # 鑾峰彇浣欓
        balance = okx.get_balance()
        print(f"\n璐︽埛浣欓: {balance}")
        
        # 妯℃嫙涓嬪崟
        result = okx.place_order('BTC-USDT', 'buy', 'market', '0.01')
        print(f"\n涓嬪崟缁撴灉: {result}")
        
    except Exception as e:
        print(f"OKX杩愯閿欒: {e}")
        print("璇风‘淇濆凡閰嶇疆姝ｇ‘鐨凙PI Key")


if __name__ == '__main__':
    # 閫夋嫨杩愯妯″紡
    print("\n妯″紡閫夋嫨:")
    print("1=鍥炴祴 (榛樿鍔犺浇 btc_1m.csv)")
    print("2=OKX妯℃嫙鐩?(闇€瑕?API Key)")
    mode = input("閫夋嫨妯″紡: ").strip()
    
    if mode == '1':
        # 鍥炴祴妯″紡
        results, strategy = run_single_symbol_backtest('BTC/USDT', 'btc_1m.csv')
        
        if results:
            # 淇濆瓨缁撴灉
            results['equity_curve'].to_csv('backtest_result.csv')
            print("\n缁撴灉宸蹭繚瀛樺埌 backtest_result.csv")
            
            # 缁樺埗鍥捐〃
            try:
                strategy.plot_results(save_path='strategy_results.png')
            except Exception as e:
                print(f"缁樺浘澶辫触: {e}")
        
    elif mode == '2':
        # OKX妯℃嫙鐩?
        run_okx_demo()
    else:
        print("鏃犳晥閫夋嫨")
