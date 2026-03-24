# Walkthrough: Strategy Skill 鍖栨灦鏋勫疄鐜?(Zen-7-1 杩佺Щ)

## 浠诲姟鐩爣
灏嗗師鏈夌殑鍥哄寲浠ｇ爜绛栫暐锛坄zen_7_1.py`锛夎В鑰﹂噸鏋勪负绗﹀悎 Anthropic [agentskills.io](https://agentskills.io/specification) 鏍囧噯鐨勫弻妯″紡 Skill 鍖咃紝骞堕厤濂楀崌绾х郴缁熺殑鍔ㄦ€佸姞杞藉簳搴ф満鍒躲€?

## 涓昏鍙樻洿

### 1. 鏂板缓 `runner/skill_loader.py`
鍒涘缓浜嗗姩鎬佹彃浠跺姞杞戒腑蹇冿細
- 鑷姩瑙ｆ瀽 `SKILL.md` 鐨?YAML 鍏冩暟鎹€?
- 鍔ㄦ€?import 绛栫暐鑴氭湰锛坄scripts/strategy.py`锛夛紝鑷姩瀵诲潃 `BaseStrategy` 鐨勫瓙绫汇€?
- 瀹炵幇 `config.local.json` 鍚堝苟鏈哄埗锛堝厑璁歌法鏈哄櫒浼犻€掔瓥鐣ヤ絾涓嶆薄鏌撴湰鍦板寲閰嶇疆锛夈€?
- 缁?Runner 搴曞骇鐨?`StrategySlot` 琛ュ厖娉ㄥ叆浜?`skill_meta`锛屼负鏃ュ悗鎺ュ叆 AI Dashboard / MCP 棰勭暀涓婁笅鏂囥€?

### 2. 鍙屾ā寮?Skill 鍖呯‘绔?(`strategies/skills/zen-7-1/`)
瀹炵幇浜?Agent-First 鐨勫寘缁撴瀯锛?
- **`SKILL.md` (Agent 鎸囧紩)**锛氶潪闈㈠悜浜虹被锛岃€屾槸閲囩敤鍔ㄨ瘝椹卞姩鍜屾竻鏅拌Е鍙戠偣鎻忚堪锛屾寚瀵?Agent 濡備綍鏌ラ獙鏁版嵁銆佹洿鏀瑰弬鏁颁互鍙婇儴缃茶绛栫暐鏈嶅姟銆?
- **`config.json` (鐘舵€侀殧绂?**锛氬皢鍘熷啓姝诲湪绛栫暐 `__init__` 鐨勮皟浼樺弬鏁帮紙濡?`resample_min`, `grid_drop_pct` 绛夛級瀹屽叏瑙ｈ€﹁繘 JSON銆?
- **`scripts/strategy.py` (涓氬姟寮曟搸)**锛氱Щ鍏ヨ璺緞涓嬨€傚師 `on_data` 鍜?`on_fill` 浠ｇ爜鍘熷皝涓嶅姩瀹岀編鍏煎锛屼粎闇€淇敼瀵煎寘璺緞銆?
- **`scripts/verify.py` (Agent 鑷祴鎺㈤拡)**锛氭柊澧炴缁勪欢锛屽厑璁?Agent 鎴栨湇鍔″湪鍏ㄩ噺鍔犺浇鏁翠釜绯荤粺涔嬪墠锛屼粎鐢ㄥ嚑鏍?Mock K绾垮揩閫熼獙璇佸紩鎿庨€昏緫涓庡弬鏁拌В鏋愭爲姝ｅ父宸ヤ綔銆?
- **`assets/backtest_summary.json` (鐭ヨ瘑澶栧寲)**锛氬浐鍖栦簡姝ゅ弬鏁伴泦鍦ㄨ繃鍘绘牳蹇冩祴璇曚腑鐨勮〃鐜扮壒寰侊紝渚?Agent 鍒ゆ柇璋冪敤鏃舵満銆?

### 3. 鏍囧噯钀藉湴
- 缂栧啓骞跺浐鍖栦簡 `docs/trading_skill_spec.md`锛氬洟闃熶笌澶氫唬鐞嗗叡鍚岄伒瀹堢殑绛栫暐鎻掍欢缁撴瀯寮€鍙戣鑼冦€?

## 楠岃瘉缁撹
- **API 鎺ュ彛瀹屾暣鎬?*锛氭墽琛?`scripts/verify.py` 鍚庯紝绛栫暐姝ｅ父鍒濆鍖栧苟娑堝寲 65 鏍规ā鎷?K 绾匡紝鍐呴儴鎸囨爣锛堝 RSI 绛夛級鍜屼俊鍙风敓鎴愬潎鏃犲紓甯告姤閿欍€?
- **SkillLoader 鍗曞厓娴嬭瘯**锛氭柊娣荤殑 `tests/test_skill_loader.py` 鍏ㄩ儴 pass锛屾垚鍔熻鍙栧苟缁勫悎浜嗚В鑰﹀嚭鐨?config 涓?strategy 绫汇€?

## 涓嬩竴姝ュ缓璁?
1. 姝ら樁娈垫殏鏈皢 Runner 鐩存帴鍗囨牸涓?MCP Server銆傚緟璇ユ爣鍑嗗湪鍏朵粬缁忓吀绛栫暐锛堝 `grid_jeff_6_5`锛変笂澶嶅埢绋冲畾鍚庯紝鍐嶇敱 Agent 缁熶竴鎺ョ鏈嶅姟璋冨害鎺ュ彛銆?
2. 瀹屽杽绛栫暐灞傜姸鎬佹満鐨勫揩鐓у鍑烘牸寮忥紝浣?Agent 鍙互鏇寸簿缁嗗湴璇诲彇姝ｅ湪杩愯鏃剁殑瀹炴椂鍔ㄦ€佸唴閮ㄦ寚鏍囷紙濡傛鍦ㄦ寔鏈夌殑姣忎竴寮犵綉鏍煎崟鐨勭姸鎬侊級銆?
