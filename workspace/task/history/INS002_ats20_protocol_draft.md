# INS002: ATS-20 浠ｇ悊浜ゆ槗閫氫俊鍗忚鑽夋 (Agentic Trading Skill Protocol)

## 1. 鏍稿績鎬濇兂 (The "ERC-20" of Quant Trading)
涓轰簡瀹炵幇鐪熸鐨勨€滄彃浠跺寘鍗虫湇鍔♀€濓紙Skill as a Service锛夛紝骞剁‘淇?Agent 鎷垮埌浠绘剰涓€涓?Trading Skill 鍗冲彲鐞嗚В瀹冪殑杈圭晫鍜岃緭鍏ヨ緭鍑烘柟寮忥紝蹇呴』灏嗙幇琛屼緷璧栧叿浣撻」鐩唬鐮佸簱锛堝 `from cts1.core import...`锛夌殑绱ц€﹀悎鏂瑰紡锛屽崌鏍间负涓€绉?*鎶借薄鐨勬帴鍙ｅ崗璁?*銆侫TS-20 鎷熶綔涓鸿繖涓€鎺ュ彛鐨勫弬鑰冨疄鐜版寚寮曘€?

## 2. 鍗忚瑕佹眰涓庤鑼?

### A. 鎺ュ彛 (Interfaces)
浠讳綍澹扮О涓?ATS-20 鍏煎鐨?Strategy Skill 蹇呴』瀹炵幇浠ヤ笅鎺ュ彛绛惧悕銆?
*(娉ㄦ剰锛氳繖浜涙帴鍙ｅ繀椤诲彧鑳戒娇鐢?Python 鍘熺敓绫诲瀷鎴栧叕寮€鐨勪笁鏂硅交閲忕被鍨嬶紝鏃犻渶渚濊禆绉佹湁搴曞眰)*

- `initialize(params: dict) -> bool`
  - **鑱岃矗**: 浣跨敤缁欏畾鐨勫弬鏁板垵濮嬪寲绛栫暐鍐呴儴鐘舵€侊紙濡傚姩鑳界紦鍐插尯銆佺綉鏍艰鏁板櫒锛夈€?
- `on_data(data: dict) -> list[dict]`
  - **鑱岃矗**: 绛栫暐鐨勬牳蹇冦€傛帴鍙椾竴涓爣鍑嗙殑琛屾儏蹇収锛圱ick 鎴?K绾匡級锛岃緭鍑?涓垨澶氫釜鏍囧噯涔板崠鎸囦护瀛楀吀銆?
- `on_event(event_type: str, payload: dict) -> None`
  - **鑱岃矗**: 鎺ユ敹鏉ヨ嚜瀹夸富/浜ゆ槗鎵€鐨勫閮ㄤ簨浠讹紙濡傦細璁㈠崟鎴愪氦銆佽鍗曟嫆缁濄€佺垎浠撹鍛婏級銆?
- `get_status() -> dict`
  - **鑱岃矗**: 鏆撮湶绛栫暐褰撳墠鍐呴儴鐨勫叧閿姸鎬侊紙濡傦細褰撳墠浠撲綅鎴愭湰銆佽窛涓嬩竴娆¤喘涔扮殑浠锋牸宸€佸唴閮?RSI 鍊硷級锛屼互渚夸华琛ㄧ洏娓叉煋鎴?Agent 鏌ヨ銆?

### B. 鏁版嵁濂戠害 (Data Schemas)
寮曟搸鍜岀瓥鐣ヤ箣闂撮€氳繃**绾暟鎹粨鏋勶紙Data Contracts锛?*閫氫俊锛岃€岄潪澶嶆潅鐨勭被瀹炰緥銆?

**鏍囧噯杈撳叆: MarketData**
```json
{
  "symbol": "BTC-USDT",
  "timestamp": 1709420000000,
  "close": 65000.50,
  "high": 65100.00,
  "low": 64900.00,
  "open": 64950.00,
  "volume": 12.5
}
```

**鏍囧噯杈撳嚭: Signal**
```json
{
  "skill_name": "zen-7-1",
  "symbol": "BTC-USDT",
  "side": "BUY",
  "type": "MARKET",
  "size": 0.05,
  "price": null, 
  "rationale": "RSI(25) deeply oversold & BBW expanded"
}
```

### C. 浜嬩欢浣撶郴 (Events)
寮曟搸闇€淇濊瘉浜х敓鐨勪簨浠跺寘鍚爣鍑嗗寲 `topic`銆備緥濡傦細
- `topic: "ORDER_FILLED"` (鍖呭惈鎴愪氦浠蜂笌鏁伴噺锛岀敤浜庣瓥鐣ュ唴鎵ｅ噺/鎺ㄨ繘缃戞牸)
- `topic: "RISK_MARGIN_CALL"` (寮曟搸渚у彂鍑鸿鍛婏紝绛栫暐搴旂珛鍒昏緭鍑哄钩浠?Signal)

## 3. 瀹炵幇璺嚎鍥?(Roadmap for Architecture 3.x)
1. **绗竴闃舵 (褰撳墠)**: 浠庢枃浠跺眰闈笂瀹炵幇浜?Skill 鐨勬墦鍖?(`zen-7-1`)銆?
2. **绗簩闃舵 (ATS-20 Wrapper)**: 鍐欎竴涓瀬鍏惰交閲忕殑 `ats_core.py` (涓嶅寘鍚换浣曢€昏緫锛屼粎鍖呭惈 Protocol 瀹氫箟鍜?TypeDict / Pydantic BaseModel)銆?
3. **绗笁闃舵 (瀹屽叏鐙珛鍖?**: `zen-7-1` 淇敼鍏?`scripts/strategy.py` 浠ｇ爜锛屽畬鍏ㄥ彧渚濊禆 `ats_core` 杩涜绫诲瀷鏍囨敞銆俁unner 绔礋璐ｅ皢 OKX 浼犳潵鐨勮剰鏁版嵁鎶瑰钩涓?`ATS-20` 鏁版嵁鏍煎紡锛屽啀鍠傜粰绛栫暐锛涘悓鏃舵嫤鎴瓥鐣ュ悙鍑虹殑淇″彿锛岀炕璇戜负 OKX API 鎵ц銆?

## 4. 鍟嗕笟/鐢熸€佷环鍊?
濡傛灉鏈潵鎴戜滑灏?`ats_core` 鍙戝竷鍒?PyPI (`pip install ats-core`)锛?
涓栫晫涓婁换浣?Agent (濡?GPT-5, Claude 3.5) 鐢熸垚鐨勪唬鐮侊紝鍙瀹?`implement ATS-20`锛屽畠灏辫兘鏃犳崯鍦版彃鍦ㄦ垜浠殑 CTS1 浠ュ強鏈潵浠讳綍寮€婧愬紩鎿庝笂璺戝疄鐩樸€傝繖灏卞交搴曡В寮€浜嗗唴瀹圭敓浜э紙Strategy锛夊拰鍩虹璁炬柦锛圧unner锛夌殑缁戝畾鐢熸€併€?
