import pandas as pd
import os

def extract_mar_week():
    input_file = "data/btc_1m_2025.csv"
    output_file = "data/btc_1m_2025_03_week_16_22.csv"
    
    if not os.path.exists("data"):
        os.makedirs("data")

    print(f"Reading {input_file}...")
    # 鍋囪 CSV 鍖呭惈 timestamp 鍒楋紝鏍煎紡涓?YYYY-MM-DD HH:MM:SS 鎴栧彲鐢?pd.to_datetime 瑙ｆ瀽
    df = pd.read_csv(input_file)
    
    # 灏?timestamp (鍋囪鏄绉? 杞负 datetime 鏍煎紡浠ヤ究绛涢€?
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # 绛涢€?2025-03-16 00:00:00 鍒?2025-03-22 23:59:00 鐨勬暟鎹?
    start_date = "2025-03-16 00:00:00"
    end_date = "2025-03-22 23:59:00"
    
    print(f"Filtering data from {start_date} to {end_date}...")
    mask = (df['timestamp'] >= start_date) & (df['timestamp'] <= end_date)
    filtered_df = df.loc[mask]
    
    if filtered_df.empty:
        print("Warning: No data found in the specified range!")
    else:
        print(f"Found {len(filtered_df)} bars. Saving to {output_file}...")
        filtered_df.to_csv(output_file, index=False)
        print("Done.")

if __name__ == "__main__":
    extract_mar_week()
