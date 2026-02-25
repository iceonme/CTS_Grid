"""
OKX交易所接入配置
支持：模拟盘、实盘、WebSocket实时数据
"""

import pandas as pd
import numpy as np
import time
import hmac
import hashlib
import base64
import json
import requests
from datetime import datetime, timezone


class OKXAPI:
    """OKX API接入类"""
    
    # API端点
    DEMO_API_URL = "https://www.okx.com"
    LIVE_API_URL = "https://www.okx.com"
    
    def __init__(self, api_key=None, api_secret=None, passphrase=None, 
                 is_demo=True, simulate_slippage=True):
        """
        初始化OKX API
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.is_demo = is_demo
        self.simulate_slippage = simulate_slippage
        
        self.base_url = self.DEMO_API_URL if is_demo else self.LIVE_API_URL
        self.session = requests.Session()
        
        print(f"OKX API初始化完成 | 模式: {'模拟盘' if is_demo else '实盘'}")
        
    def _get_timestamp(self):
        """生成ISO格式时间戳"""
        return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    
    def _sign(self, timestamp, method, request_path, body=''):
        """生成签名"""
        message = timestamp + method.upper() + request_path + body
        mac = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        )
        d = mac.digest()
        return base64.b64encode(d).decode('utf-8')
    
    def _request(self, method, path, params=None, body=None):
        """发送请求"""
        url = self.base_url + path
        
        # 处理 GET 参数拼接到路径（OKX 签名要求）
        request_path = path
        if method == 'GET' and params:
            from urllib.parse import urlencode
            query = urlencode(params)
            request_path += f"?{query}"
        
        # 处理 Body 序列化
        body_str = ""
        if body:
            body_str = json.dumps(body)
            
        timestamp = self._get_timestamp()
        
        headers = {
            'OK-ACCESS-KEY': self.api_key,
            'OK-ACCESS-SIGN': self._sign(timestamp, method, request_path, body_str),
            'OK-ACCESS-TIMESTAMP': timestamp,
            'OK-ACCESS-PASSPHRASE': self.passphrase,
            'Content-Type': 'application/json'
        }
        
        if self.is_demo:
            headers['x-simulated-trading'] = '1'
        
        try:
            if method == 'GET':
                response = self.session.get(url, headers=headers, params=params, timeout=10)
            else:
                response = self.session.post(url, headers=headers, data=body_str, timeout=10)
            
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            print(f"请求错误: {e}")
            return None
    
    def get_balance(self):
        """获取账户余额 (USDT)"""
        result = self._request('GET', '/api/v5/account/balance', {'ccy': 'USDT'})
        if result and result.get('code') == '0':
            # 提取 USDT 可用余额和总权益
            data = result['data'][0]
            details = data.get('details', [])
            for asset in details:
                if asset['ccy'] == 'USDT':
                    return {
                        'availBal': float(asset['availBal']),
                        'eq': float(asset['eq']),
                        'raw': data
                    }
        return None

    def get_balances(self):
        """获取账户全币种余额"""
        result = self._request('GET', '/api/v5/account/balance')
        if result and result.get('code') == '0':
            data = result['data'][0]
            return {
                'details': data.get('details', []),
                'totalEq': float(data.get('totalEq', 0) or 0),
                'raw': data
            }
        return None
    
    def get_ticker(self, inst_id='BTC-USDT'):
        """获取最新价格"""
        result = self._request('GET', '/api/v5/market/ticker', {'instId': inst_id})
        if result and result.get('code') == '0':
            return result['data'][0]
        return None
    
    def get_candles(self, inst_id='BTC-USDT', bar='1m', limit=100):
        """获取K线数据"""
        params = {
            'instId': inst_id,
            'bar': bar,
            'limit': str(limit)
        }
        result = self._request('GET', '/api/v5/market/candles', params)
        
        if result and result.get('code') == '0':
            # 转换为DataFrame
            df = pd.DataFrame(result['data'], columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume', 'volCcy', 'volCcyQuote', 'confirm'
            ])
            df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
            df.set_index('timestamp', inplace=True)
            df = df.sort_index()
            df = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
            return df
        return None
    
    def place_order(self, inst_id='BTC-USDT', side='buy', ord_type='market',
                    sz='0.01', px=None, td_mode='cash', ccy=None, force_server=False,
                    tgt_ccy: str = None):
        """
        下单
        force_server: 如果为 True，即使是模拟盘也会发送到 OKX 服务器，而不是本地模拟成交
        ccy: 指定 sz 的币种，例如 'USDT' 表示 sz 是 USDT 金额（用于市价买入单）
        tgt_ccy: 目标币种（用于币币交易指定目标币种）
        """
        body = {
            'instId': inst_id,
            'tdMode': td_mode,
            'side': side,
            'ordType': ord_type,
            'sz': sz
        }
        if ccy:
            body['ccy'] = ccy
        if tgt_ccy:
            body['tgtCcy'] = tgt_ccy
        
        if ord_type == 'limit' and px:
            body['px'] = px
        
        # 默认情况下，模拟盘使用本地滑点模拟以获得更快的反馈
        # 如果 force_server 为 True，则真实请求 OKX 模拟盘接口
        if self.is_demo and self.simulate_slippage and not force_server:
            ticker = self.get_ticker(inst_id)
            if ticker:
                last_price = float(ticker['last'])
                slippage = np.random.normal(0.0005, 0.0002)
                executed_price = last_price * (1 + slippage if side == 'buy' else 1 - slippage)
                
                print(f"[本地模拟成交] {side.upper()} {sz} {inst_id} @ ${executed_price:.2f}")
                return {
                    'code': '0',
                    'data': [{
                        'ordId': f"simulated_{int(time.time()*1000)}",
                        'executed_price': executed_price,
                        'slippage': slippage,
                        'status': 'filled'
                    }]
                }
        
        return self._request('POST', '/api/v5/trade/order', body=body)
    
    def get_order_history(self, inst_id='BTC-USDT', limit=100, inst_type='SPOT'):
        """获取订单历史"""
        params = {
            'instType': inst_type,
            'instId': inst_id,
            'limit': str(limit)
        }
        return self._request('GET', '/api/v5/trade/orders-history', params)

    def get_positions(self, inst_id=None):
        """获取当前持仓"""
        params = {}
        if inst_id:
            params['instId'] = inst_id
        
        result = self._request('GET', '/api/v5/account/positions', params)
        if result and result.get('code') == '0':
            return result['data']
        return []


class OKXDataFeed:
    """OKX数据流（支持WebSocket）"""
    
    def __init__(self, api=None, use_websocket=False):
        self.api = api or OKXAPI()
        self.use_websocket = use_websocket
        self.running = False
        
    def fetch_ohlcv(self, symbol='BTC-USDT', timeframe='1m', limit=100):
        """获取OHLCV数据"""
        inst_id = symbol.replace('/', '-')
        bar_map = {'1m': '1m', '5m': '5m', '15m': '15m', '1h': '1H', '4h': '4H', '1d': '1D'}
        bar = bar_map.get(timeframe, '1m')
        return self.api.get_candles(inst_id, bar, limit)
    
    def stream_ohlcv(self, symbol='BTC-USDT', timeframe='1m'):
        """实时数据流（轮询模式 - 已优化实时性）"""
        print(f"启动OKX数据流: {symbol} {timeframe}")
        self.running = True
        
        while self.running:
            try:
                # 获取最近 2 根，确保包含当前正在变动的 K 线
                df = self.fetch_ohlcv(symbol, timeframe, limit=2)
                if df is not None and len(df) > 0:
                    current_candle = df.iloc[-1]
                    
                    # 总是 yield 最新数据 (允许在同一分钟内不断更新 close/high/low)
                    # 将 pandas Timestamp 转换为毫秒时间戳
                    ts_ms = int(current_candle.name.timestamp() * 1000)
                    
                    yield {
                        'timestamp': ts_ms,
                        'open': float(current_candle['open']),
                        'high': float(current_candle['high']),
                        'low': float(current_candle['low']),
                        'close': float(current_candle['close']),
                        'volume': float(current_candle['volume'])
                    }
                
                # 缩短轮询间隔，实现近似实时的效果
                time.sleep(2) 
            except Exception as e:
                print(f"数据流错误: {e}")
                time.sleep(5)
    
    def stop(self):
        """停止数据流"""
        self.running = False
