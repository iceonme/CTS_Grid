import hmac
import base64
import json
import time
import pandas as pd
import requests
from datetime import datetime, timezone
import hashlib

class OKXAPI:
    """
    OKX API 统一封装工具类 (V5)
    支持现货、永续合约，及实盘/模拟盘环境。
    """
    
    def __init__(self, api_key=None, api_secret=None, passphrase=None, is_demo=True, **kwargs):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.is_demo = is_demo
        self.base_url = "https://www.okx.com"
        # 兼容多余参数
        self.options = kwargs

        
    def _generate_signature(self, timestamp, method, request_path, body=""):
        if body == "" or body is None:
            message = str(timestamp) + str.upper(method) + request_path
        else:
            message = str(timestamp) + str.upper(method) + request_path + str(body)
        
        mac = hmac.new(bytes(self.api_secret, encoding='utf8'), bytes(message, encoding='utf8'), digestmod='sha256')
        d = mac.digest()
        return base64.b64encode(d)

    def _get_header(self, method, request_path, body=""):
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        header = {
            'Content-Type': 'application/json',
            'OK-ACCESS-KEY': self.api_key,
            'OK-ACCESS-SIGN': self._generate_signature(timestamp, method, request_path, body),
            'OK-ACCESS-TIMESTAMP': timestamp,
            'OK-ACCESS-PASSPHRASE': self.passphrase,
        }
        if self.is_demo:
            header['x-simulated-trading'] = '1'
        return header

    def _request(self, method, request_path, params=None, body=None):
        if params:
            import urllib.parse
            # 核心修复：签名中的 requestPath 必须包含 Query String
            request_path += '?' + urllib.parse.urlencode(params)
            
        url = self.base_url + request_path
        try:
            # 只有在提供 Key/Secret 时才生成签名 Header
            header = {'Content-Type': 'application/json'}
            if self.api_key and self.api_secret:
                header = self._get_header(method, request_path, json.dumps(body) if body else "")
            elif self.is_demo:
                header['x-simulated-trading'] = '1'

            if method == 'GET':
                response = requests.get(url, headers=header, timeout=10)
            else:
                response = requests.post(url, headers=header, json=body, timeout=10)
            
            data = response.json()
            if data.get('code') != '0':
                print(f"[OKXAPI] Error {data.get('code')}: {data.get('msg')}")
            return data
        except Exception as e:
            print(f"[OKXAPI] Request failed: {e}")
            return None

    # --- 行情接口 ---
    def get_candles(self, instId, bar='1m', limit=100, after=None):
        """获取 K 线数据 (支持分页)"""
        path = "/api/v5/market/candles"
        params = {"instId": instId, "bar": bar, "limit": limit}
        if after:
            params["after"] = after
            
        res = self._request('GET', path, params=params)
        if res and res.get('data'):
            df = pd.DataFrame(res['data'], columns=['ts', 'open', 'high', 'low', 'close', 'vol', 'volCcy', 'volCcyQuote', 'confirm'])
            df['ts'] = pd.to_datetime(df['ts'].astype(float), unit='ms')
            df.set_index('ts', inplace=True)
            df = df.astype(float)
            return df.sort_index()
        return None

    # --- 账户接口 ---
    def get_balance(self, ccy="USDT"):
        path = "/api/v5/account/balance"
        params = {"ccy": ccy}
        res = self._request('GET', path, params=params)
        if res and res.get('data'):
            details = res['data'][0]['details']
            for d in details:
                if d['ccy'] == ccy:
                    return float(d['availBal'])
        return 0.0

    def get_account_max_leverage(self, instId, mgnMode="cross"):
        """获取最大可用杠杆"""
        path = "/api/v5/account/max-leverage"
        params = {"instId": instId, "mgnMode": mgnMode}
        res = self._request('GET', path, params=params)
        if res and res.get('data'):
            return float(res['data'][0]['maxLvg'])
        return 1.0

    def set_leverage(self, instId, lever, mgnMode="cross"):
        """设置杠杆"""
        path = "/api/v5/account/set-leverage"
        body = {"instId": instId, "lever": str(lever), "mgnMode": mgnMode}
        return self._request('POST', path, body=body)

    def set_position_mode(self, posMode="long_short_mode"):
        """设置持仓模式：long_short_mode(双向) / net_mode(单向)"""
        path = "/api/v5/account/set-position-mode"
        body = {"posMode": posMode}
        return self._request('POST', path, body=body)

    # --- 交易接口 ---
    def place_order(self, instId, tdMode, side, ordType, sz, posSide=None, px=None, clOrdId=None):
        path = "/api/v5/trade/order"
        body = {
            "instId": instId,
            "tdMode": tdMode,
            "side": side,
            "ordType": ordType,
            "sz": str(sz)
        }
        if posSide: body["posSide"] = posSide
        if px: body["px"] = str(px)
        if clOrdId: body["clOrdId"] = clOrdId
        return self._request('POST', path, body=body)

    def cancel_order(self, instId, ordId=None, clOrdId=None):
        path = "/api/v5/trade/cancel-order"
        body = {"instId": instId}
        if ordId: body["ordId"] = ordId
        if clOrdId: body["clOrdId"] = clOrdId
        return self._request('POST', path, body=body)

    def get_order(self, instId, ordId=None, clOrdId=None):
        path = "/api/v5/trade/order"
        params = {"instId": instId}
        if ordId: params["ordId"] = ordId
        if clOrdId: params["clOrdId"] = clOrdId
        res = self._request('GET', path, params=params)
        return res['data'][0] if res and res.get('data') else None

    # --- 合约特有接口 ---
    def get_positions(self, instId=None, instType="SWAP"):
        path = "/api/v5/account/positions"
        params = {"instType": instType}
        if instId: params["instId"] = instId
        res = self._request('GET', path, params=params)
        return res['data'] if res and res.get('data') else []

    def get_fills(self, instId=None, limit=100):
        """获取最近成交明细"""
        path = "/api/v5/trade/fills"
        params = {"limit": limit}
        if instId: params["instId"] = instId
        res = self._request('GET', path, params=params)
        return res['data'] if res and res.get('data') else []
