# 浠诲姟楠屾敹锛欳TS 5.2 鐗堟湰鏍囧噯鍖栨竻鐞?

鏈浠诲姟涓昏瀹屾垚浜嗗叏绯荤粺鍚?5.2 鐗堟湰鐨勬爣鍑嗗寲杩佺Щ锛岃В鍐充簡鏂囦欢鍚嶃€佺被鍚嶃€侀厤缃敭鍙婁华琛ㄧ洏寮曠敤涓嶇粺涓€鐨勯棶棰樸€?

## 宸插畬鎴愮殑鏇存敼

### 1. 鏍稿績绛栫暐閲嶅懡鍚嶄笌鏇存柊
- **鏂囦欢閲嶅懡鍚?*锛氬皢 `strategies/grid_rsi_5_1_r.py` 閲嶅懡鍚嶄负 `strategies/grid_rsi_5_2.py`銆?
- **绫诲悕缁熶竴**锛氱‘淇濈瓥鐣ュ唴閮ㄤ娇鐢ㄧ殑鏄?`GridRSIStrategyV5_2`銆?
- **妯″潡瀵煎嚭**锛氭洿鏂?`strategies/__init__.py`锛岀Щ闄や簡澶辨晥鐨?5.1 寮曠敤锛屾寮忓鍑?5.2 鐗堟湰銆?

### 2. 鍚姩鍣ㄤ笌骞跺彂绠＄悊
- **`run_cts52.py`**锛氬皢 `STRATEGY_CATALOG` 涓殑 key 浠?`grid_v51` 鏇存柊涓?`grid_v52`銆?
- **`multi_strategy_runner.py`**锛氱Щ闄ょ‖缂栫爜鐨勬棩蹇楀璁￠€昏緫锛岀幇宸叉敮鎸侀€氱敤鐨?5.x 鐗堟湰绛栫暐鏃ュ織銆?
- **杈呭姪鑴氭湰鍚屾**锛氭洿鏂颁簡 `run_cts1.py`銆乣run_multiple.py`銆乣run_okx_demo_with_dashboard.py` 鍙?`main.py`锛岀‘淇濆畠浠潎鎸囧悜 5.2 鐗堟湰銆?

### 3. Dashboard 琛ㄧ幇灞傛洿鏂?
- **妯℃澘鏂囦欢**锛氬皢 `dashboard_5_1.html` 閲嶅懡鍚嶄负 `dashboard_5_2.html`銆?
- **闈欐€佽祫婧?*锛氬皢 `dashboard_v51.css/js` 鍚屾閲嶅懡鍚嶄负 `dashboard_v52.css/js`銆?
- **鏈嶅姟鍣ㄩ€昏緫**锛歚dashboard/server.py` 宸叉洿鏂拌矾鐢卞強鐗堟湰澹版槑锛坴5.2-MultiStrategy-0302锛夈€?
- **鍓嶇娉ㄥ叆**锛氫慨姝ｄ簡 JS 鍐呴儴鐨?`currentStrategyId` 涓?`grid_v52`銆?

## 楠岃瘉缁撴灉

- **瀵煎叆娴嬭瘯**锛氳繍琛?`verify_pivot_fix.py` 鎴愬姛閫氳繃锛岃瘉鏄?`GridRSIStrategyV5_2` 鑳藉琚纭姞杞戒笖閫昏緫姝ｅ父銆?
- **鐜妫€鏌?*锛氬叏灞€宸叉悳绱㈠苟娓呯悊 `5_1` 鐩稿叧娈嬬暀锛岀郴缁熺幆澧冧繚鎸侀珮搴︿竴鑷淬€?

## 鍚庣画寤鸿
- 鍚姩 `python run_cts52.py` 鍗冲彲杩涘叆鍏ㄦ柊鐨?5.2 绛栫暐杩愯鐜銆?
- 浠〃鐩樿闂湴鍧€淇濇寔涓?`http://localhost:5051/v5`銆?
