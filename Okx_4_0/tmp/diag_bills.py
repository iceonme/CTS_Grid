import sys
import os
from datetime import datetime

# Add ethswap to path
sys.path.insert(0, os.path.join(os.getcwd(), "ethswap"))

from config.api_config import OKX_CONFIG
from config.okx_config import OKXAPI

def diag_bills():
    api = OKXAPI(
        api_key=OKX_CONFIG['api_key'],
        api_secret=OKX_CONFIG['api_secret'],
        passphrase=OKX_CONFIG['passphrase'],
        is_demo=OKX_CONFIG['is_demo']
    )
    
    print(f"Fetching bills for SWAP...")
    res = api.get_bills(inst_type='SWAP', limit=10)
    if res and res.get('code') == '0':
        data = res.get('data', [])
        print(f"Got {len(data)} bills.")
        for i, b in enumerate(data):
            print(f"Bill {i}: ts={b.get('ts')} instId={b.get('instId')} type={b.get('type')} bal={b.get('bal')} balChg={b.get('balChg')}")
    else:
        print(f"Error fetching bills: {res}")

if __name__ == "__main__":
    diag_bills()
