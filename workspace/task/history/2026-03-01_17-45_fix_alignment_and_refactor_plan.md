# 验收文档：图表时间轴对齐修复 (2026-03-01 17:45)

## 变更说明

### 1. 修复核心：消除图表右侧空闅?
针对ͼ表（MACD, RSI, Equity）相对于K线图在右端出现空隙（未对齐）的问题，进行了以涓嬮€昏緫修正锛?
- **问题根源**：前绔?`update` 事件处理器在数据包中缺少特定指标值（濡?`data.rsi` 为空鎴?V4 策略鏃?MACD）时，会跳过调用指标更新函数。这导致副图的时间轴无法推进锛岃€屼富鍥?K 线一直在走，浠庤€屼骇生右侧空闅欍€?
- **修复方案**：移除了前端更新逻辑中的数据存在性守卫，确保无论数据是否Ϊ空，只要接收到新的时间戳，就调用指标更新函鏁般€傚苟在函数内閮ㄩ€氳繃 `series.update({ time })` 插入 Whitespace（空白点），强制指标图表涓?K 线ͼ同步对齐銆?

### 2. 受影响文浠?
- [dashboard_5_1.html](file:///c:/Projects/TradingGarage/CTS1/dashboard/templates/dashboard_5_1.html)
- [dashboard.html](file:///c:/Projects/TradingGarage/CTS1/dashboard/templates/dashboard.html)

## 验֤结论

- **实时对齐**：即使策略暂停（不产生新指标数据），副图的横坐标轴现在也会随主图 K 线同步向右移鍔ㄣ€?
- **多策略兼瀹?*：V4 策略切换鍒?V5 Dashboard 时，MACD 区域会正确显示空白占位，不会再出鐜扳€滆甩在左侧”的情况銆?

## 关于 Dashboard 文件过大的回应与重构计划

非常感谢您的反馈。`dashboard_5_1.html` 目前确实由于集成浜?CSS、大量的 JS 图表配置鍙?Socket 逻辑，行数已超过 2200 行，这对后期的维护效率和我的阅读׼确率确实存在挑鎴樸€?

**接下来的优化建议（重构方案）锛?*
1. **样ʽ分离**：将内联 CSS 提取鍒?`static/css/`銆?
2. **逻辑分模鍧?*锛?
   - `charts_logic.js`: 专门负责 TradingView 图表的初始化与更鏂般€?
   - `data_service.js`: 负责 SocketIO 数据分发与分页处鐞嗐€?
   - `ui_manager.js`: 负责按钮鐘舵€佸強 DOM 元素更新銆?
3. **模板拆分**：利鐢?Flask 鐨?`include` 语法将仪表盘拆分涓?Header, Sidebar, MainChart, IndicatorPanel 等С片段銆?

如果您ȷ认对齐修复有效，我建议下涓€个任务就寮€始执行上述重构，以提高后续开发的敏捷搴︺€?
