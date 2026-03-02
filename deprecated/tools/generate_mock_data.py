import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def generate_mock_data(filename='btc_1m.csv', days=7):
    print(f"正在生成 {days} 天的模拟 BTC 数据...")
    
    start_time = datetime.now() - timedelta(days=days)
    timestamps = [start_time + timedelta(minutes=i) for i in range(days * 24 * 60)]
    
    # 模拟价格走势：随机漫步 + 一些震荡
    np.random.seed(42)
    returns = np.random.normal(0, 0.0002, len(timestamps))
    price_path = 50000 * np.exp(np.cumsum(returns))
    
    data = {
        'timestamp': timestamps,
        'open': price_path * (1 + np.random.normal(0, 0.0001, len(timestamps))),
        'high': price_path * (1 + abs(np.random.normal(0.0005, 0.0002, len(timestamps)))),
        'low': price_path * (1 - abs(np.random.normal(0.0005, 0.0002, len(timestamps)))),
        'close': price_path,
        'volume': np.random.uniform(10, 100, len(timestamps))
    }
    
    df = pd.DataFrame(data)
    df.set_index('timestamp', inplace=True)
    df.to_csv(filename)
    print(f"数据已保存至 {filename}，共 {len(df)} 条记录。")

if __name__ == '__main__':
    generate_mock_data()
