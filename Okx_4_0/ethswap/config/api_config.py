"""
ETH Swap 专用 API 配置文件
"""

# OKX API 配置 (复用 4.0 的模拟盘凭据)
OKX_CONFIG = {
    'api_key': '5d76baf2-21f2-4bfb-951e-2ba54e8a2d52',
    'api_secret': 'FE2BA8C81B72814CBDA7C425E4FF101F',
    'passphrase': 'Tonghua9527_',
    'is_demo': True  # 强制模拟盘
}

# 默认交易配置
DEFAULT_SYMBOL = 'ETH-USDT-SWAP'
DEFAULT_TIMEFRAME = '1m'
