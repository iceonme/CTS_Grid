# 澶氱瓥鐣ュ苟鍙戞灦鏋勯噸鏋?Walkthrough
**鏃ユ湡**: 2026-02-28 21:57
**浠诲姟**: 澶氱瓥鐣ュ苟鍙戣繍琛?+ 鍓嶇鍚姩/鏆傚仠/閲嶇疆鎺у埗

## 鍙樻洿鎽樿

### 鏂板鏂囦欢
| 鏂囦欢 | 璇存槑 |
|------|------|
| `runner/__init__.py` | runner 鍖呭垵濮嬪寲 |
| `runner/multi_strategy_runner.py` | 澶氱瓥鐣ョ鐞嗘牳蹇冿細`StrategySlot` + `MultiStrategyRunner` |
| `run_cts1.py` | 鏂扮殑 CTS1 涓诲叆鍙ｏ紝鍏变韩鏁版嵁娴佸箍鎾紝鍓嶇鍙帶 |

### 淇敼鏂囦欢
| 鏂囦欢 | 璇存槑 |
|------|------|
| `dashboard/server.py` | 鏂板 `start_strategy`/`pause_strategy` SocketIO 浜嬩欢鍙?`on_control_callback` 鎺ュ彛 |
| `dashboard/templates/dashboard.html` | 鏂板鍚姩(鈻?/鏆傚仠(鈴?鎸夐挳銆乣updateControlButtons()` 鐘舵€佽仈鍔ㄥ嚱鏁般€乣strategy_status_changed` 浜嬩欢澶勭悊 |

## 鏋舵瀯璁捐
```
run_cts1.py
  鈹斺攢 MultiStrategyRunner
       鈹溾攢 OKXDataFeed (鍗曚竴杩炴帴, 骞挎挱)
       鈹溾攢 StrategySlot grid_v40 (Grid RSI V4.0, PaperExecutor)
       鈹斺攢 StrategySlot grid_v51 (Grid RSI V5.1, PaperExecutor)
                鈫?dashboard.update(data, strategy_id=xxx)
          DashboardServer (鍓嶇鎸夋埧闂存帴鏀跺悇绛栫暐鏁版嵁)
                鈫?emit: start_strategy / pause_strategy / reset_strategy
```

## 杩愯鏂规硶
```powershell
python run_cts1.py
```
娴忚鍣ㄦ墦寮€ `http://localhost:5000`锛岄€夋嫨绛栫暐鍚庣偣鍑汇€屸柖 鍚姩銆嶃€?

## 鍏抽敭璁捐鍐崇瓥
- **鍏变韩鏁版嵁婧?*: 鍗曚釜 `OKXDataFeed` 骞挎挱锛岄伩鍏嶉噸澶?API 璋冪敤
- **寮傚父闅旂**: 姣忎釜 slot 鐨?`on_bar` 鐢ㄧ嫭绔?try/except 鍖呰９
- **鏆傚仠鏈哄埗**: `threading.Event` 鏍囧織锛屼笉寮哄埗鍋滄绾跨▼锛宼ick 绾ф鏌?
- **鎸佷箙鍖栭殧绂?*: 鐘舵€佹枃浠跺懡鍚嶄负 `trading_state_{slot_id}.json`
