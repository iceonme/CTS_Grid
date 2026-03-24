---
name: paper-executor
description: |
  模拟交易执行器 Skill。
  支持本地撮合、滑点模拟、手续费计算及持仓管理。
  遵循 Trading Skill v2.0 规范。
metadata:
  type: executor
  author: TradingGarage
  version: "1.0"
---

# Paper Executor Skill

本组件提供高性能的本地模拟撮合服务。

## 功能特性
- **本地撮合**：基于市场价格实时成交。
- **参数化建模**：支持配置手续费率和多种滑点模型（固定、自适应）。
- **状态维护**：自动维护虚拟现金和持仓。

## 配置参数
- `initial_capital`: 初始资金。
- `fee_rate`: 手续费率。
- `slippage_model`: 滑点模型 (`none`, `fixed`, `adaptive`)。
- `slippage_base`: 基础滑点比例。
