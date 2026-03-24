# 浠诲姟楠屾敹锛氫慨澶?Dashboard 瀹炴椂鏁版嵁娴佸崱浣忛棶棰?

## 闂鍙戠幇
鍦ㄥ绛栫暐骞跺彂杩愯鏃讹紝Dashboard 鍦ㄩ鐑畬鎴愬悗锛屼笉鍐嶆帴鏀舵柊鐨勫疄鏃禟绾挎暟鎹紝鎺у埗鍙板崱鍦?`鍚姩 OKX 鏁版嵁娴? BTC-USDT 1m` 涔嬪悗銆?

## 鍘熷洜鍒嗘瀽
杩欐槸鍥犱负 `flask-socketio` 榛樿浼氬湪妫€娴嬪埌绯荤粺涓畨瑁呬簡 `eventlet` 鏃跺垏鎹㈠埌 `eventlet` 杩愯妯″紡銆傜劧鑰岋紝鐢变簬浠ｇ爜灏氭湭鍦ㄩ《閮ㄨ繘琛?`eventlet.monkey_patch()`锛屼富绾跨▼涓殑 `requests.get()`锛坄okx_feed.py` 閲岃皟鐢?OKX API锛変細浣跨敤鍘熺敓 socket 闃诲鏁翠釜 Eventlet 浜嬩欢寰幆锛屽鑷存閿侊紝浣?K 绾胯疆璇㈡案杩滄棤娉曠户缁€?

## 瑙ｅ喅鍔炴硶
鍦?`CTS1/dashboard/server.py` 涓垵濮嬪寲 `SocketIO` 鏃讹紝寮哄埗鎸囧畾 `async_mode='threading'`锛岃瀹冧娇鐢?Werkzeug 鐨勫绾跨▼鍘熺敓鎬佹ā寮忥紝鏀惧純 Eventlet銆傝繖褰诲簳瑙ｅ喅浜嗗洜涓?Socket 闃诲寮曞彂鐨勬閿侀棶棰樸€?

```diff
-        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
+        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode='threading')
```

## 楠岃瘉缁撴灉
1. 宸插姞鍏?debug 鏃ュ織鎺掓煡锛岀‘璁ゆ墽琛屽埌 `get_candles` 鏃跺彂鐢熶簡鏃犻檺闃诲銆?
2. 寮哄埗鎸囧畾 `threading` 妯″紡鍚庯紝鍐嶆鍚姩 `run_cts1.py` 鏈嶅姟锛屾帶鍒跺彴椤哄埄杈撳嚭浜嗘瘡鍒嗛挓鐨勫疄鏃惰疆璇㈡洿鏂般€?
3. 娓呯悊浜?debug 鎵撳嵃浠ｇ爜銆?
4. 鐜板湪 Dashboard 鑳藉婧愭簮涓嶆柇鍦版敹鍒版柊鐨勫疄鏃惰鎯呮暟鎹€?
