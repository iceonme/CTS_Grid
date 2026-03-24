import hmac
import hashlib
import base64
import json
import requests
from datetime import datetime

def test_okx():
    config = {
        "api_key": "5d76baf2-21f2-4bfb-951e-2ba54e8a2d52",
        "api_secret": "FE2BA8C81B72814CBDA7C425E4FF101F",
        "passphrase": "Zen9527Zen9527!",
        "testnet": True
    }
    
    symbol = "ETH-USDT-SWAP"
    path = f"/api/v5/market/candles?instId={symbol}&bar=1m&limit=1"
    method = "GET"
    timestamp = datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'
    
    # Sign
    message = timestamp + method.upper() + path + ""
    mac = hmac.new(
        config['api_secret'].encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    )
    signature = base64.b64encode(mac.digest()).decode('utf-8')
    
    headers = {
        'OK-ACCESS-KEY': config['api_key'],
        'OK-ACCESS-SIGN': signature,
        'OK-ACCESS-TIMESTAMP': timestamp,
        'OK-ACCESS-PASSPHRASE': config['passphrase'],
        'Content-Type': 'application/json',
        'x-simulated-trading': '1' if config['testnet'] else '0'
    }
    
    url = "https://www.okx.com" + path
    print(f"Testing URL: {url}")
    print(f"Headers: {json.dumps(headers, indent=2)}")
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_okx()
