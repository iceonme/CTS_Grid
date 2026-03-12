import csv

file_path = r'c:\CS\zen\data\btc_1m_2025.csv'
# March 15, 2025 00:00:00 UTC = 1741996800000
# March 31, 2025 23:59:00 UTC = 1743465540000
start_ts = 1741996800000
end_ts = 1743465540000

max_high = 0
min_low = float('inf')
open_price = None
close_price = None

with open(file_path, 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        ts = int(row['timestamp'])
        if start_ts <= ts <= end_ts:
            high = float(row['high'])
            low = float(row['low'])
            close = float(row['close'])
            open_val = float(row['open'])
            
            if ts == start_ts:
                open_price = open_val
            
            if ts == end_ts:
                close_price = close
                
            if high > max_high:
                max_high = high
            if low < min_low:
                min_low = low

if open_price and close_price:
    change = (close_price - open_price) / open_price * 100
    print(f"Open: {open_price}")
    print(f"Close: {close_price}")
    print(f"Change: {change:.4f}%")
    print(f"Max: {max_high}")
    print(f"Min: {min_low}")
else:
    print("Could not find start or end price.")
