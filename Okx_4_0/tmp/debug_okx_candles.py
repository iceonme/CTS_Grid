
import hmac
import hashlib
import base64
import json
import requests
import pandas as pd
from datetime import datetime, timezone

def get_timestamp():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

def sign(timestamp, method, request_path, secret, body=''):
    message = timestamp + method.upper() + request_path + body
    mac = hmac.new(
        secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    )
    d = mac.digest()
    return base64.b64encode(d).decode('utf-8')

# Using the credentials from ethswap/config/api_config.py
API_KEY = "5d76baf2-21f2-4bfb-951e-2ba54e8a2d52"
API_SECRET = "FE2BA8C81B72814CBDA7C425E4FF101F"
PASSPHRASE = "Tonghua9527_"
SYMBOL = "ETH-USDT-SWAP"
IS_DEMO = True

def run_diagnostic():
    url = "https://www.okx.com/api/v5/market/candles"
    params = {'instId': SYMBOL, 'bar': '1m', 'limit': '5'}
    
    # Simple request without sign for public data if possible, but let's use signed to be sure about demo headers
    timestamp = get_timestamp()
    request_path = f"/api/v5/market/candles?instId={SYMBOL}&bar=1m&limit=5"
    
    headers = {
        'OK-ACCESS-KEY': API_KEY,
        'OK-ACCESS-SIGN': sign(timestamp, 'GET', request_path, API_SECRET),
        'OK-ACCESS-TIMESTAMP': timestamp,
        'OK-ACCESS-PASSPHRASE': PASSPHRASE,
        'Content-Type': 'application/json'
    }
    if IS_DEMO:
        headers['x-simulated-trading'] = '1'
        
    print(f"Requesting {SYMBOL} candles from {'Demo' if IS_DEMO else 'Real'}...")
    try:
        response = requests.get("https://www.okx.com" + request_path, headers=headers, timeout=10)
        print(f"Status Code: {response.status_code}")
        data = response.json()
        if data.get('code') == '0':
            candles = data['data']
            print("\nLatest 5 candles (Raw from OKX):")
            print("Timestamp | Open | High | Low | Close | Volume")
            for c in candles:
                # ts, o, h, l, c, vol, ...
                ts_ms = int(c[0])
                dt = datetime.fromtimestamp(ts_ms/1000, tz=timezone.utc)
                print(f"{dt.isoformat()} | {c[1]} | {c[2]} | {c[3]} | {c[4]} | {c[5]}")
                
            # Check if columns are correct
            # Standard OKX V5: ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm
            # If the High is not the max of the four, then columns might be swapped
            for c in candles:
                prices = [float(x) for x in c[1:5]]
                h = float(c[2])
                l = float(c[3])
                if h < max(prices) or l > min(prices):
                    print(f"!!! COLUMN MISMATCH DETECTED: H={h}, L={l}, Prices={prices}")
                else:
                    print(f"Column check passed: H={h} is max, L={l} is min.")
        else:
            print(f"API Error: {data}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_diagnostic()
