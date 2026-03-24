# 浠诲姟楠屾敹鎶ュ憡锛歝an GridRSI 閫夋墜 & CTS1 澶氱瓥鐣ヤ华琛ㄧ洏

**鏃ユ湡鏃堕棿**: 2026-02-28 17:40

## 涓€銆佷换鍔＄洰鏍?

1. **can 椤圭洰**锛氭柊澧?`grid-rsi-contestant.ts`锛堝湪缃戞牸绛栫暐鍩虹涓婂姞鍏?RSI 鍔ㄦ€佽皟浠撶郴鏁帮級
2. **CTS1 椤圭洰**锛氭柊澧?`grid_rsi_5_1.py`锛圴5.1 闅旂鍘熷瀷锛夊苟灏嗕华琛ㄧ洏鏀归€犱负鏀寔澶氱瓥鐣ュ苟琛屽睍绀?

---

## 浜屻€佸彉鏇存枃浠舵眹鎬?

### can 椤圭洰

| 鏂囦欢 | 鎿嶄綔 | 璇存槑 |
|------|------|------|
| `lib/agents/contestants/grid-rsi-contestant.ts` | **鏂板** | GridRSIContestant 绫伙紝缁ф壙缃戞牸閫昏緫锛孯SI 璋冧粨绯绘暟绾挎€ф彃鍊?|
| `app/api/backtest/run/route.ts` | 淇敼 | Import GridRSIContestant锛屾敞鍐?`grid-rsi-bot` / `type:grid-rsi` 鍒嗘敮 |

**GridRSI 绛栫暐鏍稿績閫昏緫**锛?
- `rsiOversold`锛堥粯璁?35锛夆啌 鈫?`buyMultiplier = rsiMaxMultiplier`锛堥粯璁?1.5x锛夋斁澶т拱鍏?
- `rsiOverbought`锛堥粯璁?65锛夆啈 鈫?`buyMultiplier = rsiMinMultiplier`锛堥粯璁?0.5x锛夌缉灏忎拱鍏?
- 涓棿鍖洪棿绾挎€ф彃鍊硷紝RSI 姣忚疆閲嶇畻缃戞牸鏃跺悓姝ユ洿鏂?
- 閰嶇疆鏂板瀛楁锛歚rsiPeriod`, `rsiOversold`, `rsiOverbought`, `rsiMaxMultiplier`, `rsiMinMultiplier`

### CTS1 椤圭洰

| 鏂囦欢 | 鎿嶄綔 | 璇存槑 |
|------|------|------|
| `strategies/grid_rsi_5_1.py` | **鏂板** | V5.1 闅旂鍘熷瀷锛岀被鍚?`GridRSIStrategyV5_1`锛岄€昏緫鍚?V4.0 |
| `strategies/__init__.py` | 淇敼 | 瀵煎嚭 `GridRSIStrategyV5_1` |
| `dashboard/server.py` | **閲嶅啓** | 澶氱瓥鐣?Room 鍖栵細`_data` 鍙樹负瀛楀吀鐨勫瓧鍏革紝`update(data, strategy_id)` |
| `dashboard/__init__.py` | 淇敼 | 琛ュ厖瀵煎嚭 `get_dashboard`, `set_dashboard` |
| `dashboard/templates/dashboard.html` | 淇敼 | Header 鍔犵瓥鐣ュ垏鎹?Select锛汮S 鍔?`switchStrategy()` + `join/leave` Room 閫昏緫 |
| `run_multiple.py` | **鏂板** | 澶氱瓥鐣ュ苟琛屽洖娴嬪叆鍙ｏ紝涓や釜寮曟搸绾跨▼锛屾敮鎸?`--dashboard` 鍙傛暟 |

---

## 涓夈€佸叧閿灦鏋勫彉鍖?

### CTS1 Dashboard 澶氱瓥鐣ユ灦鏋?

```
                     鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
鍚庣绾跨▼ A (V4.0) 鈹€鈹€鈫?鈹?server.update(data,          鈹?
                     鈹?  strategy_id='grid_rsi_v40')鈹傗攢鈹€鈫?Room:grid_rsi_v40 鈹€鈹€鈫?娴忚鍣ˋ
鍚庣绾跨▼ B (V5.1) 鈹€鈹€鈫?鈹?server.update(data,          鈹?
                     鈹?  strategy_id='grid_rsi_v51')鈹傗攢鈹€鈫?Room:grid_rsi_v51 鈹€鈹€鈫?娴忚鍣˙
                     鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
```

鍓嶇閫氳繃涓嬫媺妗嗗垏鎹㈢瓥鐣ユ椂锛?
1. `socket.emit('leave', {strategy_id: old})` 绂诲紑鏃ф埧闂?
2. 娓呯┖鍥捐〃銆佷氦鏄撹褰?
3. `socket.emit('join', {strategy_id: new})` 鍔犲叆鏂版埧闂达紝绔嬪嵆鏀跺埌鍘嗗彶鏁版嵁

### can GridRSI 娉ㄥ唽

```
contestants: [
  { type: 'grid-rsi', id: 'my-bot', settings: { rsiOversold: 30, rsiOverbought: 70 } }
]
```

---

## 鍥涖€佷娇鐢ㄦ柟娉?

### CTS1 澶氱瓥鐣ュ苟琛岃繍琛?

```bash
# 绾洖娴嬪姣?
python run_multiple.py --data btc_1m.csv --capital 10000

# 甯?Dashboard 鍙鍖?
python run_multiple.py --data btc_1m.csv --capital 10000 --dashboard --port 5000
```

### can 鍥炴祴 API 璋冪敤

```json
{
  "contestants": [
    { "type": "grid",     "id": "grid-bot",     "name": "绾綉鏍? },
    { "type": "grid-rsi", "id": "gridrsi-bot",  "name": "缃戞牸RSI",
      "settings": { "rsiOversold": 35, "rsiOverbought": 65 } }
  ]
}
```

---

## 浜斻€侀獙璇佹儏鍐?

- 鉁?Python 璇硶锛歚grid_rsi_5_1.py` 閫昏緫瀹屾暣 Copy 鑷?V4.0锛屾棤鏂板紩鍏ョ殑璇硶閿欒
- 鉁?TypeScript 鎺ュ彛锛歚grid-rsi-contestant.ts` 绫诲疄鐜颁簡瀹屾暣鐨?`Contestant` 鎺ュ彛锛坄initialize`, `onTick`, `getPortfolio`, `getLogs`, `getTrades`, `getMetrics`锛?
- 鉁?Dashboard 鍚戝悗鍏煎锛氭棫鐗?`run_okx_demo_with_dashboard.py` 鐨勫崟绛栫暐 `server.update(data)` 璋冪敤浠嶅彲浣跨敤锛坄strategy_id` 鏈夐粯璁ゅ€?`'default'`锛?
- 鉁?BOARD.md 宸叉洿鏂帮紙瑙佷笅锛?
