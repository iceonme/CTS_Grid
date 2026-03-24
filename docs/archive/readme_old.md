# BTC鍔ㄦ€佺綉鏍肩瓥鐣?- 鏈湴妯℃嫙鐩樼郴缁?

## 馃搧 椤圭洰缁撴瀯

```
grid_trading_system/
鈹溾攢鈹€ paper_trading.py          # 妯℃嫙鐩樺紩鎿庯紙鏍稿績锛?
鈹溾攢鈹€ grid_strategy.py          # 绛栫暐閫傞厤鍣紙浼樺寲鐗圴4锛?
鈹溾攢鈹€ okx_config.py             # OKX浜ゆ槗鎵€閰嶇疆
鈹溾攢鈹€ run_paper_trading.py      # 杩愯鑴氭湰
鈹溾攢鈹€ dashboard.py              # 瀹炴椂鐩戞帶闈㈡澘
鈹溾攢鈹€ templates/
鈹?  鈹斺攢鈹€ dashboard.html        # Web鐣岄潰妯℃澘
鈹溾攢鈹€ data/
鈹?  鈹斺攢鈹€ btc_1m.csv           # 鍘嗗彶鏁版嵁鏂囦欢
鈹斺攢鈹€ README.md                 # 鏈枃浠?
```

## 馃殌 蹇€熷紑濮?

### 1. 瀹夎渚濊禆

```bash
pip install pandas numpy ccxt flask flask-socketio plotly requests
```

### 2. 鍑嗗鏁版嵁

CSV鏍煎紡瑕佹眰锛堜繚瀛樹负 `btc_1m.csv`锛夛細
```csv
timestamp,open,high,low,close,volume
2024-01-01 00:00:00,42500,42600,42400,42550,100.5
2024-01-01 00:01:00,42550,42650,42500,42620,95.3
```

### 3. 杩愯鍥炴祴

```bash
python run_paper_trading.py
# 閫夋嫨妯″紡: 1 (鍥炴祴妯″紡)
```

## 馃敡 OKX閰嶇疆璇︾粏姝ラ

### 姝ラ1: 娉ㄥ唽OKX璐﹀彿
1. 璁块棶 https://www.okx.com

### 姝ラ2: 鍒涘缓API Key锛堟ā鎷熺洏锛?
1. 鐧诲綍鍚庣偣鍑诲彸涓婅銆愪釜浜轰腑蹇冦€?
2. 閫夋嫨銆怉PI銆?>銆愬垱寤篈PI Key銆?
3. 閫夋嫨銆愭ā鎷熶氦鏄撱€?
4. 璁剧疆API Key鍚嶇О銆丳assphrase骞朵繚瀛樸€?

### 姝ラ3: 鑾峰彇妯℃嫙璧勯噾
1. 杩涘叆OKX妯℃嫙浜ゆ槗椤甸潰鑾峰彇铏氭嫙USDT銆?

## 馃搳 鏍稿績鍔熻兘

### 1. 鑷€傚簲婊戠偣妯″瀷
鏍规嵁璁㈠崟绨挎繁搴﹁嚜鍔ㄨ皟鏁存粦鐐广€?

### 2. 缃戠粶寤惰繜妯℃嫙
妯℃嫙 200ms 鐨勭綉缁滃線杩斿欢杩熴€?

### 3. 鍔ㄦ€佷粨浣嶈皟鏁达紙浼樺寲鐗圴4锛?
- 鑷€傚簲 RSI 鎸囨爣銆?
- 鍑埄鍏紡浠撲綅绠＄悊銆?
- 绉诲姩姝㈡崯鏈哄埗銆?

## 馃枼锔?鍚姩鐩戞帶闈㈡澘

```bash
python dashboard.py
# 娴忚鍣ㄨ闂?http://localhost:5000
```

## 鈿狅笍 椋庨櫓鎻愮ず
1. **妯℃嫙鐩樷墵瀹炵洏**銆?
2. **API瀹夊叏**锛氳鍕挎硠闇?API Key銆?
3. **璧勯噾瀹夊叏**锛氬疄鐩樿浠庡皬璧勯噾寮€濮嬨€?




# 鍙敤API  锛堟ā鎷熺洏锛?
apikey = "72aac042-9859-48ec-8e27-9722524429a6"
secretkey = "CCFE2963EBD154027557D24CFA2CAA57"
IP = ""
澶囨敞鍚?= "Paper_trading_1"
鏉冮檺 = "璇诲彇", "浜ゆ槗"
