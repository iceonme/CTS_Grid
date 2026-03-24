
import sys
import os
sys.path.append(os.getcwd())
from okx_config import OKXAPI
import json

def test_auth():
    api_config = {
        'api_key': '72aac042-9859-48ec-8e27-9722524429a6',
        'api_secret': 'CCFE2963EBD154027557D24CFA2CAA57',
        'passphrase': 'Tonghua9527_',
        'is_demo': True
    }
    
    api = OKXAPI(**api_config)
    
    print("--- 楠岃瘉 GET 璇锋眰 (浣欓) ---")
    balance = api.get_balance()
    if balance:
        print(f"鎴愬姛鑾峰彇浣欓: {balance['availBal']} USDT")
    else:
        print("鑾峰彇浣欓澶辫触")
        
    print("\n--- 楠岃瘉 GET 璇锋眰 (鎸佷粨) ---")
    positions = api.get_positions('BTC-USDT')
    if positions is not None:
        print(f"鎴愬姛鑾峰彇鎸佷粨锛屽綋鍓嶆寔浠撴暟閲? {len(positions)}")
    else:
        print("鑾峰彇鎸佷粨澶辫触")

    print("\n--- 楠岃瘉 POST 璇锋眰 (妯℃嫙涓嬪崟娴嬭瘯) ---")
    # 杩欓噷鎴戜滑浣跨敤涓€涓皬棰濈殑涔板崟鏉ユ祴璇曪紝OKX 妯℃嫙鐩樺簲璇ュ厑璁?
    # 娉ㄦ剰锛氳繖閲岃皟鐢ㄧ殑鏄?place_order锛屽唴閮ㄥ鏋?force_server=True 浼氱湡瀹炲彂缁欐湇鍔″櫒
    order_result = api.place_order(inst_id='BTC-USDT', side='buy', sz='0.01', force_server=True)
    if order_result and order_result.get('code') == '0':
        print(f"涓嬪崟娴嬭瘯鎴愬姛! OrdId: {order_result['data'][0].get('ordId')}")
    else:
        print(f"涓嬪崟娴嬭瘯澶辫触: {order_result}")

if __name__ == "__main__":
    test_auth()
