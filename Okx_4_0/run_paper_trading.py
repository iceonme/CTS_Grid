"""
run_paper_trading.py - 完整运行脚本
"""

import pandas as pd
import numpy as np
from datetime import datetime

# 导入自定义模块
from paper_trading import MultiExchangePaperTrading, DataFeed
from grid_strategy import DynamicGridStrategyV4


def run_single_symbol_backtest(symbol='BTC/USDT', data_path='btc_1m.csv'):
    """单币种回测"""
    print(f"\n{'='*60}")
    print(f"开始回测: {symbol}")
    print(f"{'='*60}")
    
    # 1. 加载数据
    try:
        df = pd.read_csv(data_path, index_col='timestamp', parse_dates=True)
        print(f"数据加载完成: {len(df)} 条记录")
    except Exception as e:
        print(f"加载数据失败: {e}")
        return None, None
    
    # 2. 初始化模拟盘
    paper = MultiExchangePaperTrading(
        initial_capital=10000,
        fee_rate=0.001,
        slippage_model='adaptive'
    )
    paper.set_latency(200)
    
    # 3. 创建策略
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
    
    # 4. 运行回测
    print(f"\n运行模拟...")
    results = strategy.run_backtest(df, verbose=True)
    
    # 5. 打印报告
    strategy.print_report(results)
    
    return results, strategy


def run_okx_demo():
    """OKX模拟盘运行示例"""
    try:
        from okx_config import OKXAPI, OKXDataFeed
        
        # 配置API（使用模拟盘）
        # 注意：OKX API 必须提供 Passphrase (API密码)
        okx = OKXAPI(
            api_key='72aac042-9859-48ec-8e27-9722524429a6',
            api_secret='CCFE2963EBD154027557D24CFA2CAA57',
            passphrase='Tonghua9527_', # OKX API 密码
            is_demo=True,
            simulate_slippage=True
        )
        
        # 获取历史数据
        df = okx.get_candles('BTC-USDT', '1m', 1000)
        print(f"获取数据: {len(df)} 条")
        print(df.tail())
        
        # 获取余额
        balance = okx.get_balance()
        print(f"\n账户余额: {balance}")
        
        # 模拟下单
        result = okx.place_order('BTC-USDT', 'buy', 'market', '0.01')
        print(f"\n下单结果: {result}")
        
    except Exception as e:
        print(f"OKX运行错误: {e}")
        print("请确保已配置正确的API Key")


if __name__ == '__main__':
    # 选择运行模式
    print("\n模式选择:")
    print("1=回测 (默认加载 btc_1m.csv)")
    print("2=OKX模拟盘 (需要 API Key)")
    mode = input("选择模式: ").strip()
    
    if mode == '1':
        # 回测模式
        results, strategy = run_single_symbol_backtest('BTC/USDT', 'btc_1m.csv')
        
        if results:
            # 保存结果
            results['equity_curve'].to_csv('backtest_result.csv')
            print("\n结果已保存到 backtest_result.csv")
            
            # 绘制图表
            try:
                strategy.plot_results(save_path='strategy_results.png')
            except Exception as e:
                print(f"绘图失败: {e}")
        
    elif mode == '2':
        # OKX模拟盘
        run_okx_demo()
    else:
        print("无效选择")
