# 鍒嗘敮鍚屾浠诲姟楠屾敹鏂囨。 (Walkthrough)

**鏃ユ湡**: 2026-03-02 16:45
**鎻忚堪**: 浠?GitHub 涓嬭浇骞舵洿鏂?`cts_grid` 鐨?`multi_runner` 鍒嗘敮銆?

## 瀹屾垚鐨勫伐浣?
1. **鑾峰彇鏇存柊**: 鎵ц `git fetch origin` 鑾峰彇浜嗚繙绋嬫墍鏈夊垎鏀殑鏈€鏂扮姸鎬併€?
2. **鍒嗘敮鍒囨崲**: 鍒囨崲鏈湴鍒嗘敮鍒?`multi_runner`銆?
3. **浠ｇ爜鍚屾**: 鎵ц `git pull origin multi_runner` 灏嗘湰鍦颁唬鐮佹洿鏂拌嚦杩滅▼鏈€鏂扮増鏈紙Commit: `8f7f80e`锛夈€?

## 鍚屾缁撴灉楠岃瘉
- **褰撳墠鍒嗘敮**: `multi_runner`
- **鏈€鏂版彁浜?*: `8f7f80e feat: upgrade to V5.2 with MACD filter fix and grid density optimization`
- **涓昏鍙樻洿**:
    - 鏂板 `run_cts52.py` (V5.2 杩愯鑴氭湰)
    - 鏂板 `strategies/grid_rsi_5_1_r.py` (绛栫暐閲嶆瀯鐗?
    - 鍚勭閰嶇疆鏂囦欢鍗囩骇 (`grid_v52_default.json` 绛?
    - 閮ㄥ垎 JSON 鏁版嵁鏂囦欢閲嶅懡鍚?

## 楠岃瘉鎴浘/璁板綍
```bash
> git branch
  main
* multi_runner

> git log -1 --oneline
8f7f80e feat: upgrade to V5.2 with MACD filter fix and grid density optimization
```
