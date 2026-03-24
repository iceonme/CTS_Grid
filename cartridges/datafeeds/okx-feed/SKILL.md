---
name: okx-feed
description: |
  OKX 实时行情数据源 Skill。
  支持获取 K 线数据流，并可将数据记录到本地 CSV。
  遵循 Trading Skill v2.0 规范。
metadata:
  type: datafeed
  author: TradingGarage
  version: "1.0"
---

# OKX DataFeed Skill

本组件负责从 OKX 获取实时 K 线数据。

## 功能特性
- **实时流**：通过轮询方式模拟数据流。
- **本地记录**：可配置将行情数据录入 `assets/` 目录。
- **配置隔离**：API Key 等敏感信息应放在 `config.local.json`。

## 配置参数
- `symbol`: 交易对（如 BTC-USDT）。
- `timeframe`: 时间周期（如 1m, 5m）。
- `poll_interval`: 轮询间隔（秒）。

---
*注：已默认优化为对接 OKX 现货市场以保证行情稳定性。*
