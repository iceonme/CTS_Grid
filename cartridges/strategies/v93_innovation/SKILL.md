---
name: v93_innovation
metadata:
  type: strategy
  version: "9.3"
  description: 基于 3+2 动态网格与 RSI 动量过滤的 ETH 永续合约策略
---

# V9.3 Innovation 策略


基于 3 实体网格 + 2 虚拟网格架构的高级动量网格策略。

## 核心特性
- **3+2 网格系统**：动态调整交易区间。
- **RSI 动量过滤**：自适应 RSI 阈值。
- **无状态设计**：支持通过 `ats.py` 进行标准加载。

## 配置项 (config.json)
- `symbol`: 交易标的。
- `base_position_eth`: 基础仓位大小。
- `leverage_base`: 基础杠杆。

## 开发者
- **Skill Type**: Strategy
- **Base Class**: `BaseStrategy`
