---
name: okx-swap-executor
metadata:
  type: executor
  version: "1.0"
  description: 支持 OKX 永续合约 (Swap) 的执行器组件
---

# OKX 合约执行器 (OKX-Swap-Executor)

支持 OKX 永续合约 (Swap) 的执行器组件。

## 核心功能
- **双向持仓**：强制开启 `long_short_mode` 以支持 V93 等网格对冲策略。
- **动态杠杆**：支持由策略信号驱动的实时杠杆调整。
- **单位转换**：自动处理标的资产（如 ETH）与合约张数（Contracts）之间的换算。
- **实盘/模拟**：兼容 OKX 真实的模拟盘 (Demo Trading) 接口。

## 配置项 (config.json)
- `symbol`: 交易标的，如 `ETH-USDT-SWAP`。
- `leverage`: 初始杠杆倍数（默认 1.0）。
- `ct_val`: 合约面值（如 ETH 通常是 0.1 ETH/张）。
- `api_key`/`api_secret`/`passphrase`: OKX API 密钥。
- `is_demo`: 是否运行在模拟盘环境。

## 开发者
- **Skill Type**: Bridge / Executor
- **Base Class**: `BaseExecutor`
