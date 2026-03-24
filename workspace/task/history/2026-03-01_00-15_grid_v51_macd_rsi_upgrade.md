# GridRSI V5.1 策略升级 鈥?验收文档
**日期**: 2026-03-01 00:15

---

## 变更摘要

灏?`strategies/grid_rsi_5_1.py` 浠?V4.0 复制原型升级为真正的 V5.1 策略，实鐜?`grid_5.1_JeffHuang.md` 策略说明中的ȫ部核心改进銆?

**只修改了 1 个文浠?*，类鍚?`GridRSIStrategyV5_1` 和公共接口不变，可无缝接鍏?`run_cts1.py` 鍜?Dashboard銆?

---

## 核心改动

| 模块 | 变更 | 说明 |
|---|---|---|
| MACD 计算 | **新增** `_calculate_macd()` | EMA(12,26,9)，返鍥?macd_line/signal_line/histogram |
| ATR 计算 | **新增** `_calculate_atr()` | 14 周期 ATR，驱动网格间距自适应 |
| 趋势判别 | **替换** `_detect_market_regime()` | 浠?ADX+MA 鈫?MACD 5 级分绫?(STRONG_BULLISH/BULLISH/NEUTRAL/BEARISH/STRONG_BEARISH) |
| 双指标确璁?| **新增** `_get_dual_signal()` | 5×4 矩阵：趋势方鍚?× RSI 区间 鈫?仓位等级 + 动作 |
| 仓λ公式 | **重写** `_calculate_position_size()` | 趋势强度系数(+0.3~-0.4) × RSI 偏离折扣 × MACD 零轴保护 |
| 网格计算 | **改进** `_calculate_dynamic_grid()` | ATR 鑷€傚簲间距(0.3%~2.0%) + MACD 趋势偏移(±10%~20%) |
| 风控规则 | **新增** 多层风控 | RSI>75 禁买 / MACD<0 减仓50% / 15 分钟冷却 / 保守模式 |
| 移动止盈 | **改进** `_check_stop_loss()` | 盈利>5% 涓?MACD 柱状图收缂?鈫?婵€活；RSI>75 减仓50% |
| 异常妫€娴?| **新增** `_check_anomaly()` | 连续 3 娆?MACD/RSI 冲突 鈫?保守模式(网格间距扩大) |
| 鐘舵€佹姤鍛?| **增强** `get_status()` | 新增 macd_line/signal_line/histogram/trend_strength/atr/dual_action 等字娈?|

---

## 验证结果

| 妫€查项 | 结果 |
|---|---|
| 导入妫€鏌?`from strategies.grid_rsi_5_1 import GridRSIStrategyV5_1` | 鉁?OK |
| `get_status()` 返回 V5.1 新字娈?| 鉁?macd_line=0.0, trend=NEUTRAL, atr=0.0, action=hold |
| 现有单元测试 (5 tests) | 鉁?All passed (0.229s) |
| 类名 & 接口签名兼容鎬?| 鉁?涓?`run_cts1.py` / `run_multiple.py` 无缝衔接 |

---

## 修改文件

| 文件 | 操作 |
|---|---|
| [grid_rsi_5_1.py](file:///c:/Projects/TradingGarage/CTS1/strategies/grid_rsi_5_1.py) | 重写 (588鈫?80 琛? |
