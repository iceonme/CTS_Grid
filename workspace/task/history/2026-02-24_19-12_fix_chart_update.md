# 验收文档 (Walkthrough) - 2026-02-24_19-12_修复图表更新问题

## 任务背景
用户反馈仪表盘ǰ端显示正常且有心跳，但图表无法实时更鏂般€?

## 修复内容

### 引擎核心逻辑修复
修改浜?[engines/live.py](file:///c:/Projects/CTS1/engines/live.py)，在 `_build_status` 方法中补ȫ了前端 `dashboard.html` 渲染图表鎵€闇€的关键字段：

- **[NEW] `candle` 字段**：包含实鏃?K 线的 `t`, `o`, `h`, `l`, `c` 鏁板€笺€?
- **[NEW] `rsi` 字段**：直接从策略中获ȡ当前的 RSI 鏁板€笺€?
- **[NEW] `strategy` 字段**：包含网格边鐣屻€佷俊号文本等策略运行ָ标銆?
- **[MODIFY] `trade_history`**：统涓€了交易历史的字段名称，确保与前端 JS 脚本匹配銆?

## 验证结果

### 自动化验璇?
通过运行 `verify_fix.py` 进行验证，结果如下：
- 鉁?`candle` 字段妫€测成功且结构完整銆?
- 鉁?`rsi` 鍙?`strategy` 鐘舵€佹垚功注鍏ャ€?
- 鉁?计算逻辑（如 `pnl_pct` 鍜?`initial_balance`）验璇侀€氳繃銆?

### 手动验֤建议
请重启仪表盘脚本（例濡?`python run_okx_demo_with_dashboard.py`），刷新浏览器页面后即可看到锛?
1. K 线主图开始随行情波动銆?
2. RSI 曲线和参考线随数据产出动态绘鍒躲€?
3. 账户权益曲线寮€始记录增量变鍖栥€?
