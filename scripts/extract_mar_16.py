import pandas as pd
import os

def extract_mar_16():
    input_file = "data/btc_1m_2025.csv"
    output_file = "data/btc_1m_2025_03_16.csv"
    
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return

    print(f"Reading {input_file}...")
    # 假设文件有 timestamp 列，格式为 ms
    df = pd.read_csv(input_file)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # 过滤 3月16日 全天
    start_date = "2025-03-16 00:00:00"
    end_date = "2025-03-16 23:59:59"
    
    mask = (df['timestamp'] >= start_date) & (df['timestamp'] <= end_date)
    march_16_df = df.loc[mask]
    
    if march_16_df.empty:
        print("No data found for March 16th.")
        return
        
    march_16_df.to_csv(output_file, index=False)
    print(f"Successfully extracted {len(march_16_df)} bars to {output_file}")

if __name__ == "__main__":
    extract_mar_16()
