# V4 / V5 鍓嶇瑙ｈ€﹀強 MACD 淇楠屾敹鏂囨。

**鏃ユ湡**: 2026-03-01
**涓昏浠诲姟**: 褰诲簳鍒嗙 V4 鍜?V5 鐨勫墠绔瓥鐣ュ垏鎹㈤€昏緫锛屾秷闄ゅ啑浣?UI锛屽苟淇 V5 浠〃鐩樹腑 MACD 鎸囨爣鐨勬覆鏌撻敊璇€?

## 鍙樻洿璇存槑

### 1. 鍚庣璺敱纭垎绂?
- 淇敼浜?`dashboard/server.py`锛岄厤缃簡鐙珛鐨?`/v4` 鍜?`/v5` 闈欐€佽矾鐢辨帴鍙ｃ€?
- 灏嗗師鏈姩鎬佸尮閰嶇殑绛栫暐璺敱鍙樻洿涓哄浐瀹氳鍥撅紱璁块棶鏍圭洰褰?`/` 浼氳嚜鍔ㄩ噸瀹氬悜鑷?`/v5`銆?

### 2. V4 浠〃鐩樿В鑰?(`dashboard.html`)
- 绉婚櫎浜嗛《閮ㄧ殑鈥滅瓥鐣ュ垏鎹笅鎷夋鈥?(`select#strategySelect`)锛屼唬涔嬩互鏄惧紡鐨勨€滅綉鏍?V4.0鈥濈姸鎬佹爣绛俱€?
- 鍓嶇 JS 閫昏緫涓Щ闄や簡 `switchStrategy` 鍑芥暟浠ュ強 Socket.IO 瀵?`strategies_list` 鐨勮嚜鍔ㄨ烦杞€昏緫銆?
- 灏嗚繛鎺ョ殑 `currentStrategyId` 纭紪鐮佷负 `grid_v40`銆?

### 3. V5 浠〃鐩樿В鑰︿笌 MACD 淇 (`dashboard_5_1.html`)
- 绉婚櫎浜嗛《閮ㄧ殑绛栫暐閫夋嫨鍣紝纭紪鐮?`currentStrategyId` 涓?`grid_v51`銆?
- 閲嶆瀯浜?TradingView Lightweight Charts 涓?MACD 鍥捐〃鐨勫垵濮嬪寲閫昏緫 (`initCharts`)銆?
- **MACD 淇鐐?*锛?
  - 涓?MACD 鍥捐〃涓撻棬鍒嗛厤骞剁粦瀹氫簡鍙充晶鍒诲害 (`rightPriceScale` 璁剧疆涓?`autoScale: true`锛屼笂涓嬭竟璺濅负 `0.1`)銆?
  - 涓?MACD 鏌辩姸鍥?(`macdHistSeries`)銆佸揩绾?(`macdMacdSeries`) 鍜屾參绾?(`macdSignalSeries`) 鏄惧紡閰嶇疆浜?`priceScaleId: 'right'`锛屼粠鑰岀‘淇濅笉鍚岄噺绾х殑鏁版嵁鑳藉湪鍓浘闈㈡澘涓甯哥缉鏀惧拰娓叉煋銆?

## 楠岃瘉璁″垝 (闇€鎵ц鎵嬪伐妫€鏌?
鍥犺嚜鍔ㄥ寲娴嬭瘯鍙楅檺浜?Windows OS 鐨勬棤澶存祻瑙堝櫒妯″紡锛?*璇锋墜鍔ㄩ獙璇?*锛?
1. 杩愯 `python run_cts1.py`銆?
2. 鍦ㄦ祻瑙堝櫒涓墦寮€ `http://localhost:5000/v4`锛岀‘璁ゆ棤绛栫暐閫夋嫨妗嗭紝鏁版嵁姝ｅ父娴佽浆銆?
3. 鎵撳紑 `http://localhost:5000/v5`锛岀‘璁ゆ棤绛栫暐閫夋嫨妗嗭紝鍚戜笅婊氬姩瀵熺湅 RSI 涓嬫柟鐨?MACD 鍓浘锛屾牳瀵?MACD 鏌变笌绾挎槸鍚﹁兘闅忎环鏍煎彉鍔ㄦ纭覆鏌撱€?
