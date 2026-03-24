
import hmac
import hashlib
import base64
import json
import requests
from datetime import datetime, timezone

# Using credentials from ethswap/config/api_config.py
API_KEY = "5d76baf2-21f2-4bfb-951e-2ba54e8a2d52"
API_SECRET = "FE2BA8C81B72814CBDA7C425E4FF101F"
PASSPHRASE = "Tonghua9527_"
IS_DEMO = True

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

def okx_request(method, path, body=None):
    url = "https://www.okx.com" + path
    timestamp = get_timestamp()
    body_json = json.dumps(body) if body else ""
    
    # Handle query params in sign path correctly if any
    request_path = path
    
    headers = {
        'OK-ACCESS-KEY': API_KEY,
        'OK-ACCESS-SIGN': sign(timestamp, method, request_path, API_SECRET, body_json),
        'OK-ACCESS-TIMESTAMP': timestamp,
        'OK-ACCESS-PASSPHRASE': PASSPHRASE,
        'Content-Type': 'application/json',
        'x-simulated-trading': '1' if IS_DEMO else '0'
    }
    
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, timeout=10)
        else:
            response = requests.post(url, headers=headers, data=body_json, timeout=10)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def diag():
    print("--- OKX Account Diagnostic ---")
    
    # 1. Check Position Mode
    pos_mode = okx_request('GET', '/api/v5/account/position-mode')
    print(f"Position Mode: {json.dumps(pos_mode, indent=2)}")
    
    # 2. Check Positions
    positions = okx_request('GET', '/api/v5/account/positions?instType=SWAP')
    print(f"Positions: {json.dumps(positions, indent=2)}")
    
    # 3. Check Account Balance (USDT)
    balance = okx_request('GET', '/api/v5/account/balance?ccy=USDT')
    print(f"Balance: {json.dumps(balance, indent=2)}")

if __name__ == "__main__":
    diag()
