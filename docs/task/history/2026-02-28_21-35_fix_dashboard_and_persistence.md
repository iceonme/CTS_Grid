# 任务验收文档 (Walkthrough)
**日期**: 2026-02-28
**任务**: 修复 Dashboard 响应与多策略持久化隔离

## 诊断与修复结论
本次修复解决了从“单策略版本”迁移到“多策略 Dashboard”后遗留的一系列数据兼容性问题：

1. **策略下拉框空白**：
   * **修复**：在 `run_okx_demo.py` 初始化时，主动调用 `dashboard.register_strategy(STRATEGY_ID, "Grid RSI V4 (BTC-USDT)")`。现在打开 Dashboard，右上角的下拉框会正确显示正在跑的策略名称，不再显示“等待策略列表”。

2. **RSI 缺失 / 为默认值 50**：
   * **修复**：原来的代码视图通过 `getattr(strategy.state, 'current_rsi')` 获取，但这在最新版本中不存在。现已修正为从安全的上下文字典中读取：`strategy_status.get('current_rsi')`，图表和仪表盘数据已恢复联动。

3. **持久化文件命名冲突**：
   * **修复**：之前的记录文件被写死为 `trading_state.json`，如果运行多个配置或副本，状态会被互相覆盖。引入了 `STRATEGY_ID = "grid_rsi_demo_01"` 常量，现在的状态文件会被隔离保存为如 `trading_state_grid_rsi_demo_01.json`。以后新建任何策略脚本，只需调整这个 ID 即可做到互不干涉。

## 运行建议
修改已经全部生效。您可以重新运行：
```powershell
python run_okx_demo.py
```
现在打开 Dashboard，您不但能看到策略名字，而且 RSI 的状态和曲线都能瞬间同步上了。不同实例也不会再破坏彼此的历史记录。
