# 楠屾敹鏂囨。 - 2026-02-23 23:30

## 鍏ㄩ潰瀹℃煡骞朵慨澶嶆暟鎹畬鏁存€ч棶棰?

### 闂鎻忚堪
Dashboard K 绾垮浘鏁版嵁涓嶈繛缁€佸嚭鐜伴棿鏂€傜粡鍏ㄩ摼璺唬鐮佸鏌ワ紝鍙戠幇澶氬鏁版嵁绫诲瀷涓嶄竴鑷村拰閬楁紡闂銆?

### 鍏ㄩ摼璺慨澶嶆竻鍗?

| # | 鏂囦欢 | 闂 | 淇 |
|---|------|------|------|
| 1 | [okx_config.py](file:///c:/Projects/CTS1/okx_config.py) | 杞闂撮殧 60s锛屾瘡鍒嗛挓鎵嶆洿鏂颁竴娆?| 缂╃煭鑷?2s锛屽疄鐜拌繎瀹炴椂鏁堟灉 |
| 2 | [okx_config.py](file:///c:/Projects/CTS1/okx_config.py) | `stream_ohlcv` 浼犻€?`symbol` 瀛楃涓叉贩鍏?DataFrame 瀵艰嚧鏁板€煎垪寮傚父 | 绉婚櫎 `symbol` 瀛楁 |
| 3 | [okx_config.py](file:///c:/Projects/CTS1/okx_config.py) | `get_candles` 杩斿洖棰濆鍒?(`volCcy`, `confirm` 绛?锛屼笌 tick 鏁版嵁鍒椾笉涓€鑷?| 鍙繚鐣?OHLCV 浜斿垪 |
| 4 | [okx_config.py](file:///c:/Projects/CTS1/okx_config.py) | timestamp 浼?`pd.Timestamp` 瀵硅薄锛屽悗缁鐞嗕笉涓€鑷?| 缁熶竴浼犳绉掓暣鏁?|
| 5 | [run_live_grid.py](file:///c:/Projects/CTS1/run_live_grid.py) | `on_tick` 鐢ㄦ绉掓暣鏁板仛绱㈠紩锛屼笌 warmup 鐨?`pd.Timestamp` 绱㈠紩鍐茬獊 | 缁熶竴杞崲涓?`pd.Timestamp` + 鍘婚噸鎺掑簭 |
| 6 | [run_live_grid.py](file:///c:/Projects/CTS1/run_live_grid.py) | warmup 鍘嗗彶鐢?ISO 瀛楃涓诧紝on_tick 鐢ㄦ绉掞紝鏃跺尯鍋忕Щ瀵艰嚧涓嶈繛缁?| 鍏ㄩ儴缁熶竴涓烘绉掓暣鏁?|
| 7 | [run_live_grid.py](file:///c:/Projects/CTS1/run_live_grid.py) | warmup 缂哄皯 `position_value` 瀛楁 | 琛ュ厖璇ュ瓧娈?|
| 8 | [dashboard.py](file:///c:/Projects/CTS1/dashboard.py) | `history_candles` 閲嶅鏃堕棿鎴崇疮绉?| 鍚屾椂闂存埑鏇挎崲鑰岄潪杩藉姞 |
| 9 | [dashboard.py](file:///c:/Projects/CTS1/dashboard.py) | 杩炴帴鏃跺弻鍙?`history_update` + `update` | 鍙彂涓€娆?`update` |
| 10 | [dashboard.html](file:///c:/Projects/CTS1/templates/dashboard.html) | `setData` 鍓嶆湭鍘婚噸锛宍Value is null` 宕╂簝 | `Map` 鍘婚噸 + `update()` 澧為噺鏇存柊 |

### 楠岃瘉鏂瑰紡
閲嶅惎 `run_live_grid.py` 骞跺埛鏂版祻瑙堝櫒锛堢‘璁?`Build-005`锛夛紝瑙傚療锛?
- K 绾挎暟鎹粠鍘嗗彶鍒板疄鏃跺簲鏃犻棿鏂?
- 姣?2 绉掑埛鏂颁竴娆℃渶鏂颁环鏍?
- 鏃犳姤閿欎俊鎭?
