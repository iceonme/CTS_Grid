# 验收文档 (Walkthrough) - 2026-02-24_19-12_修复图表更新问题

## 任务背景
用户反馈仪表盘前端显示正常且有心跳，但图表无法实时更新。

## 修复内容

### 引擎核心逻辑修复
修改了 [engines/live.py](file:///c:/Projects/CTS1/engines/live.py)，在 `_build_status` 方法中补全了前端 `dashboard.html` 渲染图表所需的关键字段：

- **[NEW] `candle` 字段**：包含实时 K 线的 `t`, `o`, `h`, `l`, `c` 数值。
- **[NEW] `rsi` 字段**：直接从策略中获取当前的 RSI 数值。
- **[NEW] `strategy` 字段**：包含网格边界、信号文本等策略运行指标。
- **[MODIFY] `trade_history`**：统一了交易历史的字段名称，确保与前端 JS 脚本匹配。

## 验证结果

### 自动化验证
通过运行 `verify_fix.py` 进行验证，结果如下：
- ✅ `candle` 字段检测成功且结构完整。
- ✅ `rsi` 及 `strategy` 状态成功注入。
- ✅ 计算逻辑（如 `pnl_pct` 和 `initial_balance`）验证通过。

### 手动验证建议
请重启仪表盘脚本（例如 `python run_okx_demo_with_dashboard.py`），刷新浏览器页面后即可看到：
1. K 线主图开始随行情波动。
2. RSI 曲线和参考线随数据产出动态绘制。
3. 账户权益曲线开始记录增量变化。
