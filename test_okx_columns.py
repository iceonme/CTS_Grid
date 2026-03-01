import requests
import json

def test_okx_candles():
    url = "https://www.okx.com/api/v5/market/candles"
    params = {
        "instId": "BTC-USDT",
        "bar": "1m",
        "limit": "1"
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if data.get('code') == '0':
            candles = data['data']
            if candles:
                print(f"OKX K-line data (first row): {candles[0]}")
                print(f"Number of columns: {len(candles[0])}")
            else:
                print("No data returned")
        else:
            print(f"Error from OKX: {data}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_okx_candles()
