---
name: zen-7-1
description: |
  这是一个【交易判断技能包】（Trading Skill）。
  支持两种模式：(1) Agent 直接加载调用，辅助决策；(2) 挂载到 Runner 成为微服务持续运行。
  基于 BOLL 带宽扩张 + MACD + RSI 三重共振信号，采用网格分层摊薄机制建仓，含动态止盈/全局硬止损。
  适用于 BTC/USDT 1m K线 + 60m 重采样。
license: Proprietary
metadata:
  author: TradingGarage
  version: "7.1"
  symbol: BTC-USDT-SWAP
  timeframe: 1m
  resample: 60m
  min_capital: "5000"
---

# Zen 7.1 — Agent 交易技能包

本 Skill 包专供 AI Agent（如 Claude、Cursor）或基于 API 的微服务系统使用。
**这是一个双模式技能包（Dual-Mode Skill）。**

---

## 模式 A：Agent 直接调用验证

如果你是 AI Agent，你可以直接调用此目录中的脚本来进行策略验证或模拟计算。

1. **查阅回测数据**
   Agent 可以在 `assets/backtest_summary.json` 中查阅 2025 年回测结果与预设最佳参数。
2. **快速运行与验证**
   在项目根目录下，执行内置的快速验证脚本：
   ```bash
   python strategies/skills/zen-7-1/scripts/verify.py
   ```
   该脚本不依赖庞大的底层 Runner 框架，它只是实例化了 `strategy.py` 并灌入了几十根模拟的 K 线数据，用于验证逻辑通道已走通。
3. **调整参数**
   直接修改本目录的 `config.json`，或创建 `config.local.json` 覆盖参数以改变资金规模和风险偏好。

---

## 模式 B：挂载为 Runner 微服务

本技能包可即插即用，作为长驻后台微服务工作。你的宿主 Runner 将通过 `SkillLoader` 加载本包：

```python
from runner.skill_loader import SkillLoader
# Loader 将自动从 scripts/strategy.py 提取出策略类，并用 config.json 里的 params 进行初始化
strategy, meta, config = SkillLoader().load("strategies/skills/zen-7-1")
```

随后 Runner 将把策略装入 slot，并为其持续推送 WebSocket 数据与执行订单。

---

## 策略进出场核心逻辑（供 Agent 学习）

所有业务逻辑均在 `scripts/strategy.py` 中。

### 进场（1H 级别共振）

**条件 A（标准大前置）**，以下全部满足：
- 波动率：`BBW > BBW_MA20`
- 强势多头：`close > boll_mid` 且 `macd_hist > 0`
- 无超买且动能向上：`35 ≤ RSI ≤ 65` 且 `RSI > prev_RSI`

### 出场（止盈/止损）

**动态止盈（盈利达标后，涨势停滞时跑路）**：
- `pnl ≥ tp_min_profit_pct` AND `touched_upper_band` AND `RSI > 65` (且开始动能收缩)

**硬止损（1M 级实时防爆）**：
- 取决于 `config.json` 中的 `hard_sl_pct` 参数，如果触及则全部清平仓（返回 SELL 信号阻断后续操作）

---

## 修改边界

- **如需调整风险偏好**：请修改 `config.json` 中的 `hard_sl_pct` 和 `grid_drop_pct` 参数
- **如需修改买卖点逻辑**：请编辑 `scripts/strategy.py`
- **如需修改文档与推荐值**：请编辑 `SKILL.md` 和 `references/REFERENCE.md`
