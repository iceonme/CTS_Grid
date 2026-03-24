# 浠诲姟楠屾敹鏂囨。 (Walkthrough)
**鏃ユ湡**: 2026-02-28
**浠诲姟**: 绉婚櫎 Eventlet 瑙ｅ喅 OKX 杩炴帴涓嶅彲杈鹃敊璇?

## 璇婃柇涓庝慨澶嶇粨璁?
1. **鏍规簮纭**: 缁忚繃瀵圭収娴嬭瘯锛岀‘璁?`eventlet.monkey_patch()` 鍦?Windows 鍙婁唬鐞嗙幆澧冧笅浼氬共鎵板師鐢?Socket锛岀洿鎺ュ鑷?`WSAENETUNREACH` 閿欒銆?
2. **淇鏂规**: 宸蹭粠 `run_okx_demo.py`銆乣dashboard/server.py` 绛夋墍鏈夋牳蹇冨叆鍙ｄ腑绉婚櫎浜?Eventlet 渚濊禆銆?
3. **楠岃瘉缁撴灉**: 杩愯 `diagnose_network.py` 鏄剧ず鐩存帴杩炴帴 OKX 宸叉仮澶嶆甯革紙HTTP 200 Success锛夛紝涓嶅啀鍑虹幇 ConnectionPool 鎶ラ敊銆?

## 鍙樻洿鏄庣粏
- **[绉婚櫎]** 鍏ㄩ」鐩竻鐞嗕簡 `import eventlet` 鍜?`eventlet.monkey_patch()`銆?
- **[浼樺寲]** `run_okx_demo.py` 澧炲姞浜嗗绌烘暟鎹殑鍋ュ．鎬т繚鎶ゃ€?
- **[淇]** 鍚屾淇浜嗗绛栫暐 Dashboard 鐨勬暟鎹矾寰勯棶棰樸€?

## 杩愯寤鸿
鎮ㄧ幇鍦ㄥ彲浠ョǔ瀹氳繍琛屼富鑴氭湰浜嗭細
```powershell
python run_okx_demo.py
```
鐜板湪鍗充究鍦ㄧ綉缁滄尝鍔ㄦ椂锛岀▼搴忎篃涓嶄細鐢变簬搴曞眰 Socket 鍐茬獊鑰岀洿鎺ユ姤閿欎腑鏂€?
