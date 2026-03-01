# 验收文档：图表时间轴对齐修复 (2026-03-01 17:45)

## 变更说明

### 1. 修复核心：消除图表右侧空隙
针对图表（MACD, RSI, Equity）相对于K线图在右端出现空隙（未对齐）的问题，进行了以下逻辑修正：
- **问题根源**：前端 `update` 事件处理器在数据包中缺少特定指标值（如 `data.rsi` 为空或 V4 策略无 MACD）时，会跳过调用指标更新函数。这导致副图的时间轴无法推进，而主图 K 线一直在走，从而产生右侧空隙。
- **修复方案**：移除了前端更新逻辑中的数据存在性守卫，确保无论数据是否为空，只要接收到新的时间戳，就调用指标更新函数。并在函数内部通过 `series.update({ time })` 插入 Whitespace（空白点），强制指标图表与 K 线图同步对齐。

### 2. 受影响文件
- [dashboard_5_1.html](file:///c:/Projects/TradingGarage/CTS1/dashboard/templates/dashboard_5_1.html)
- [dashboard.html](file:///c:/Projects/TradingGarage/CTS1/dashboard/templates/dashboard.html)

## 验证结论

- **实时对齐**：即使策略暂停（不产生新指标数据），副图的横坐标轴现在也会随主图 K 线同步向右移动。
- **多策略兼容**：V4 策略切换到 V5 Dashboard 时，MACD 区域会正确显示空白占位，不会再出现“被甩在左侧”的情况。

## 关于 Dashboard 文件过大的回应与重构计划

非常感谢您的反馈。`dashboard_5_1.html` 目前确实由于集成了 CSS、大量的 JS 图表配置及 Socket 逻辑，行数已超过 2200 行，这对后期的维护效率和我的阅读准确率确实存在挑战。

**接下来的优化建议（重构方案）：**
1. **样式分离**：将内联 CSS 提取到 `static/css/`。
2. **逻辑分模块**：
   - `charts_logic.js`: 专门负责 TradingView 图表的初始化与更新。
   - `data_service.js`: 负责 SocketIO 数据分发与分页处理。
   - `ui_manager.js`: 负责按钮状态及 DOM 元素更新。
3. **模板拆分**：利用 Flask 的 `include` 语法将仪表盘拆分为 Header, Sidebar, MainChart, IndicatorPanel 等小片段。

如果您确认对齐修复有效，我建议下一个任务就开始执行上述重构，以提高后续开发的敏捷度。
