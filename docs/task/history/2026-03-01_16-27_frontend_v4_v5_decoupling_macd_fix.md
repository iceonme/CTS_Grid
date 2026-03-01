# V4 / V5 前端解耦及 MACD 修复验收文档

**日期**: 2026-03-01
**主要任务**: 彻底分离 V4 和 V5 的前端策略切换逻辑，消除冗余 UI，并修复 V5 仪表盘中 MACD 指标的渲染错误。

## 变更说明

### 1. 后端路由硬分离
- 修改了 `dashboard/server.py`，配置了独立的 `/v4` 和 `/v5` 静态路由接口。
- 将原本动态匹配的策略路由变更为固定视图；访问根目录 `/` 会自动重定向至 `/v5`。

### 2. V4 仪表盘解耦 (`dashboard.html`)
- 移除了顶部的“策略切换下拉框” (`select#strategySelect`)，代之以显式的“网格 V4.0”状态标签。
- 前端 JS 逻辑中移除了 `switchStrategy` 函数以及 Socket.IO 对 `strategies_list` 的自动跳转逻辑。
- 将连接的 `currentStrategyId` 硬编码为 `grid_v40`。

### 3. V5 仪表盘解耦与 MACD 修复 (`dashboard_5_1.html`)
- 移除了顶部的策略选择器，硬编码 `currentStrategyId` 为 `grid_v51`。
- 重构了 TradingView Lightweight Charts 中 MACD 图表的初始化逻辑 (`initCharts`)。
- **MACD 修订点**：
  - 为 MACD 图表专门分配并绑定了右侧刻度 (`rightPriceScale` 设置为 `autoScale: true`，上下边距为 `0.1`)。
  - 为 MACD 柱状图 (`macdHistSeries`)、快线 (`macdMacdSeries`) 和慢线 (`macdSignalSeries`) 显式配置了 `priceScaleId: 'right'`，从而确保不同量级的数据能在副图面板中正常缩放和渲染。

## 验证计划 (需执行手工检查)
因自动化测试受限于 Windows OS 的无头浏览器模式，**请手动验证**：
1. 运行 `python run_cts1.py`。
2. 在浏览器中打开 `http://localhost:5000/v4`，确认无策略选择框，数据正常流转。
3. 打开 `http://localhost:5000/v5`，确认无策略选择框，向下滚动察看 RSI 下方的 MACD 副图，核对 MACD 柱与线是否能随价格变动正确渲染。
