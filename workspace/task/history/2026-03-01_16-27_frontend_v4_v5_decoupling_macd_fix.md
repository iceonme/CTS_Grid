# V4 / V5 前端瑙ｈ€﹀強 MACD 修复验收文档

**日期**: 2026-03-01
**主要任务**: 彻底分离 V4 鍜?V5 的ǰ端策略切鎹㈤€昏緫，消除冗浣?UI，并修复 V5 仪表盘中 MACD 指标的渲染错璇€?

## 变更说明

### 1. 后端路由硬分绂?
- 修改浜?`dashboard/server.py`，配置了独立鐨?`/v4` 鍜?`/v5` 闈欐€佽矾由接鍙ｃ€?
- 将ԭ本动̬ƥ配的策略路由变更为固定视ͼ；访问根目褰?`/` 会自动重定向鑷?`/v5`銆?

### 2. V4 仪表盘解鑰?(`dashboard.html`)
- 移除了顶部的“策略切换下拉框鈥?(`select#strategySelect`)，代之以显式鐨勨€滅綉鏍?V4.0”状态标绛俱€?
- 前端 JS 逻辑中移除了 `switchStrategy` 函数以及 Socket.IO 瀵?`strategies_list` 的自动跳杞€昏緫銆?
- 将连接的 `currentStrategyId` 硬编码为 `grid_v40`銆?

### 3. V5 仪表盘解耦与 MACD 修复 (`dashboard_5_1.html`)
- 移除了顶部的策略选择器，硬编鐮?`currentStrategyId` 涓?`grid_v51`銆?
- 重构浜?TradingView Lightweight Charts 涓?MACD 图表的初始化逻辑 (`initCharts`)銆?
- **MACD 修订鐐?*锛?
  - 涓?MACD 图表专门分配并绑定了右侧刻度 (`rightPriceScale` 设置涓?`autoScale: true`，上下边距为 `0.1`)銆?
  - 涓?MACD 柱状鍥?(`macdHistSeries`)、快绾?(`macdMacdSeries`) 和慢绾?(`macdSignalSeries`) 显式配置浜?`priceScaleId: 'right'`，从而确保不同量级的数据能在副图面板中正常缩放和渲染銆?

## 验证计划 (闇€执行手工妫€鏌?
因自动化测试受限浜?Windows OS 的无头浏览器模式锛?*请手动验璇?*锛?
1. 运行 `python run_cts1.py`銆?
2. 在浏览器中打寮€ `http://localhost:5000/v4`，确认无策略选择框，数据正常流转銆?
3. 打开 `http://localhost:5000/v5`，确认无策略选择框，向下滚动察看 RSI 下方鐨?MACD 副图，核瀵?MACD 柱与线是否能随价格变动正确渲鏌撱€?
