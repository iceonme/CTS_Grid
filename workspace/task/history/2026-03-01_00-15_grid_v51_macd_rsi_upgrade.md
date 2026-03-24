# GridRSI V5.1 绛栫暐鍗囩骇 鈥?楠屾敹鏂囨。
**鏃ユ湡**: 2026-03-01 00:15

---

## 鍙樻洿鎽樿

灏?`strategies/grid_rsi_5_1.py` 浠?V4.0 澶嶅埗鍘熷瀷鍗囩骇涓虹湡姝ｇ殑 V5.1 绛栫暐锛屽疄鐜?`grid_5.1_JeffHuang.md` 绛栫暐璇存槑涓殑鍏ㄩ儴鏍稿績鏀硅繘銆?

**鍙慨鏀逛簡 1 涓枃浠?*锛岀被鍚?`GridRSIStrategyV5_1` 鍜屽叕鍏辨帴鍙ｄ笉鍙橈紝鍙棤缂濇帴鍏?`run_cts1.py` 鍜?Dashboard銆?

---

## 鏍稿績鏀瑰姩

| 妯″潡 | 鍙樻洿 | 璇存槑 |
|---|---|---|
| MACD 璁＄畻 | **鏂板** `_calculate_macd()` | EMA(12,26,9)锛岃繑鍥?macd_line/signal_line/histogram |
| ATR 璁＄畻 | **鏂板** `_calculate_atr()` | 14 鍛ㄦ湡 ATR锛岄┍鍔ㄧ綉鏍奸棿璺濊嚜閫傚簲 |
| 瓒嬪娍鍒ゅ埆 | **鏇挎崲** `_detect_market_regime()` | 浠?ADX+MA 鈫?MACD 5 绾у垎绫?(STRONG_BULLISH/BULLISH/NEUTRAL/BEARISH/STRONG_BEARISH) |
| 鍙屾寚鏍囩‘璁?| **鏂板** `_get_dual_signal()` | 5脳4 鐭╅樀锛氳秼鍔挎柟鍚?脳 RSI 鍖洪棿 鈫?浠撲綅绛夌骇 + 鍔ㄤ綔 |
| 浠撲綅鍏紡 | **閲嶅啓** `_calculate_position_size()` | 瓒嬪娍寮哄害绯绘暟(+0.3~-0.4) 脳 RSI 鍋忕鎶樻墸 脳 MACD 闆惰酱淇濇姢 |
| 缃戞牸璁＄畻 | **鏀硅繘** `_calculate_dynamic_grid()` | ATR 鑷€傚簲闂磋窛(0.3%~2.0%) + MACD 瓒嬪娍鍋忕Щ(卤10%~20%) |
| 椋庢帶瑙勫垯 | **鏂板** 澶氬眰椋庢帶 | RSI>75 绂佷拱 / MACD<0 鍑忎粨50% / 15 鍒嗛挓鍐峰嵈 / 淇濆畧妯″紡 |
| 绉诲姩姝㈢泩 | **鏀硅繘** `_check_stop_loss()` | 鐩堝埄>5% 涓?MACD 鏌辩姸鍥炬敹缂?鈫?婵€娲伙紱RSI>75 鍑忎粨50% |
| 寮傚父妫€娴?| **鏂板** `_check_anomaly()` | 杩炵画 3 娆?MACD/RSI 鍐茬獊 鈫?淇濆畧妯″紡(缃戞牸闂磋窛鎵╁ぇ) |
| 鐘舵€佹姤鍛?| **澧炲己** `get_status()` | 鏂板 macd_line/signal_line/histogram/trend_strength/atr/dual_action 绛夊瓧娈?|

---

## 楠岃瘉缁撴灉

| 妫€鏌ラ」 | 缁撴灉 |
|---|---|
| 瀵煎叆妫€鏌?`from strategies.grid_rsi_5_1 import GridRSIStrategyV5_1` | 鉁?OK |
| `get_status()` 杩斿洖 V5.1 鏂板瓧娈?| 鉁?macd_line=0.0, trend=NEUTRAL, atr=0.0, action=hold |
| 鐜版湁鍗曞厓娴嬭瘯 (5 tests) | 鉁?All passed (0.229s) |
| 绫诲悕 & 鎺ュ彛绛惧悕鍏煎鎬?| 鉁?涓?`run_cts1.py` / `run_multiple.py` 鏃犵紳琛旀帴 |

---

## 淇敼鏂囦欢

| 鏂囦欢 | 鎿嶄綔 |
|---|---|
| [grid_rsi_5_1.py](file:///c:/Projects/TradingGarage/CTS1/strategies/grid_rsi_5_1.py) | 閲嶅啓 (588鈫?80 琛? |
