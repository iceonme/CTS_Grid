# 故障修复报告 (2026-03-01 18:30)

## 修复概述
针对用户反馈的后端 OKX API 超时及前端 Dashboard `socket is not defined` 报错，已完成针对性修复。

## 修改内容

### 后端：OKX API 稳定性优化
- **延长超时**：将 `okx_config.py` 中的全局请求超时从 10s 增加至 **30s**，以应对预热阶段获取大量历史数据时的网络波动。
- **备用域名**：将 `LIVE_API_URL` 默认指向 `https://aws.okx.com`（通常比 `www.okx.com` 更稳定），并支持通过环境变量 `OKX_API_URL` 动态覆盖。

### 前端：Socket 初始化及预热修复
- **变量定义**：在 `dashboard_5_1.html` 中补全了 `socket` 变量定义。
- **预热渲染**：完善了 `dashboard_v51.js` 对历史数据的 `setData` 逻辑，支持 MACD 历史显示。

## 验证结论
- **网络验证**：连通性测试通过。
- **功能验证**：JS 报错消除，预热图表恢复。
