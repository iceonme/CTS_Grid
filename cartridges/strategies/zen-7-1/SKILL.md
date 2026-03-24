---
name: zen-7-1
description: |
  杩欐槸涓€涓€愪氦鏄撳垽鏂妧鑳藉寘銆戯紙Trading Skill锛夈€?
  鏀寔涓ょ妯″紡锛?1) Agent 鐩存帴鍔犺浇璋冪敤锛岃緟鍔╁喅绛栵紱(2) 鎸傝浇鍒?Runner 鎴愪负寰湇鍔℃寔缁繍琛屻€?
  鍩轰簬 BOLL 甯﹀鎵╁紶 + MACD + RSI 涓夐噸鍏辨尟淇″彿锛岄噰鐢ㄧ綉鏍煎垎灞傛憡钖勬満鍒跺缓浠擄紝鍚姩鎬佹鐩?鍏ㄥ眬纭鎹熴€?
  閫傜敤浜?BTC/USDT 1m K绾?+ 60m 閲嶉噰鏍枫€?
license: Proprietary
metadata:
  author: TradingGarage
  version: "7.1"
  symbol: BTC-USDT-SWAP
  timeframe: 1m
  resample: 60m
  min_capital: "5000"
---

# Zen 7.1 鈥?Agent 浜ゆ槗鎶€鑳藉寘

鏈?Skill 鍖呬笓渚?AI Agent锛堝 Claude銆丆ursor锛夋垨鍩轰簬 API 鐨勫井鏈嶅姟绯荤粺浣跨敤銆?
**杩欐槸涓€涓弻妯″紡鎶€鑳藉寘锛圖ual-Mode Skill锛夈€?*

---

## 妯″紡 A锛欰gent 鐩存帴璋冪敤楠岃瘉

濡傛灉浣犳槸 AI Agent锛屼綘鍙互鐩存帴璋冪敤姝ょ洰褰曚腑鐨勮剼鏈潵杩涜绛栫暐楠岃瘉鎴栨ā鎷熻绠椼€?

1. **鏌ラ槄鍥炴祴鏁版嵁**
   Agent 鍙互鍦?`assets/backtest_summary.json` 涓煡闃?2025 骞村洖娴嬬粨鏋滀笌棰勮鏈€浣冲弬鏁般€?
2. **蹇€熻繍琛屼笌楠岃瘉**
   鍦ㄩ」鐩牴鐩綍涓嬶紝鎵ц鍐呯疆鐨勫揩閫熼獙璇佽剼鏈細
   ```bash
   python strategies/skills/zen-7-1/scripts/verify.py
   ```
   璇ヨ剼鏈笉渚濊禆搴炲ぇ鐨勫簳灞?Runner 妗嗘灦锛屽畠鍙槸瀹炰緥鍖栦簡 `strategy.py` 骞剁亴鍏ヤ簡鍑犲崄鏍规ā鎷熺殑 K 绾挎暟鎹紝鐢ㄤ簬楠岃瘉閫昏緫閫氶亾宸茶蛋閫氥€?
3. **璋冩暣鍙傛暟**
   鐩存帴淇敼鏈洰褰曠殑 `config.json`锛屾垨鍒涘缓 `config.local.json` 瑕嗙洊鍙傛暟浠ユ敼鍙樿祫閲戣妯″拰椋庨櫓鍋忓ソ銆?

---

## 妯″紡 B锛氭寕杞戒负 Runner 寰湇鍔?

鏈妧鑳藉寘鍙嵆鎻掑嵆鐢紝浣滀负闀块┗鍚庡彴寰湇鍔″伐浣溿€備綘鐨勫涓?Runner 灏嗛€氳繃 `SkillLoader` 鍔犺浇鏈寘锛?

```python
from runner.skill_loader import SkillLoader
# Loader 灏嗚嚜鍔ㄤ粠 scripts/strategy.py 鎻愬彇鍑虹瓥鐣ョ被锛屽苟鐢?config.json 閲岀殑 params 杩涜鍒濆鍖?
strategy, meta, config = SkillLoader().load("strategies/skills/zen-7-1")
```

闅忓悗 Runner 灏嗘妸绛栫暐瑁呭叆 slot锛屽苟涓哄叾鎸佺画鎺ㄩ€?WebSocket 鏁版嵁涓庢墽琛岃鍗曘€?

---

## 绛栫暐杩涘嚭鍦烘牳蹇冮€昏緫锛堜緵 Agent 瀛︿範锛?

鎵€鏈変笟鍔￠€昏緫鍧囧湪 `scripts/strategy.py` 涓€?

### 杩涘満锛?H 绾у埆鍏辨尟锛?

**鏉′欢 A锛堟爣鍑嗗ぇ鍓嶇疆锛?*锛屼互涓嬪叏閮ㄦ弧瓒筹細
- 娉㈠姩鐜囷細`BBW > BBW_MA20`
- 寮哄娍澶氬ご锛歚close > boll_mid` 涓?`macd_hist > 0`
- 鏃犺秴涔颁笖鍔ㄨ兘鍚戜笂锛歚35 鈮?RSI 鈮?65` 涓?`RSI > prev_RSI`

### 鍑哄満锛堟鐩?姝㈡崯锛?

**鍔ㄦ€佹鐩堬紙鐩堝埄杈炬爣鍚庯紝娑ㄥ娍鍋滄粸鏃惰窇璺級**锛?
- `pnl 鈮?tp_min_profit_pct` AND `touched_upper_band` AND `RSI > 65` (涓斿紑濮嬪姩鑳芥敹缂?

**纭鎹燂紙1M 绾у疄鏃堕槻鐖嗭級**锛?
- 鍙栧喅浜?`config.json` 涓殑 `hard_sl_pct` 鍙傛暟锛屽鏋滆Е鍙婂垯鍏ㄩ儴娓呭钩浠擄紙杩斿洖 SELL 淇″彿闃绘柇鍚庣画鎿嶄綔锛?

---

## 淇敼杈圭晫

- **濡傞渶璋冩暣椋庨櫓鍋忓ソ**锛氳淇敼 `config.json` 涓殑 `hard_sl_pct` 鍜?`grid_drop_pct` 鍙傛暟
- **濡傞渶淇敼涔板崠鐐归€昏緫**锛氳缂栬緫 `scripts/strategy.py`
- **濡傞渶淇敼鏂囨。涓庢帹鑽愬€?*锛氳缂栬緫 `SKILL.md` 鍜?`references/REFERENCE.md`
