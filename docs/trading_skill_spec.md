# Trading Strategy Skill 规范 (v1.0)

> 适用系统：CTS1 (TradingGarage)  
> 兼容标准：[agentskills.io specification](https://agentskills.io/specification)  
> 版本日期：2026-03-05

---

## 1. 概述

**Trading Skill** 是一个可移植的策略文件包。将一个策略 Skill 目录复制到任意装有 CTS1 Runner 的机器上，Runner 即可通过 `SkillLoader` 自动加载并运行，**无需修改任何代码**。

Skill 包与 Runner 底座的职责边界：

| 归属 Runner（底座） | 归属 Skill（插件） |
|---|---|
| 数据总线、WebSocket 连接 | 信号逻辑（on_data） |
| 订单执行（Paper / OKX） | 指标计算（RSI / MACD 等） |
| Dashboard 推送 | 参数配置（config.json） |
| 持久化（state / trades） | UI 组件声明（get_ui_manifest） |
| 日志、错误隔离 | 参数文档（SKILL.md / REFERENCE.md） |

---

## 2. 目录结构

```
<skill-name>/                 ← 目录名即为 Skill 名（小写+连字符）
├── SKILL.md                  ← [必须] 策略说明（支持双模式描述）
├── config.json               ← [必须] 默认参数
├── scripts/                  ← [必须] 执行脚本目录
│   ├── strategy.py           ← [必须] 策略逻辑（包含 BaseStrategy 子类）
│   └── verify.py             ← [可选] 供 Agent 快速验证逻辑的独立脚本
├── assets/                   ← [可选] 数据或静态资源
│   └── backtest_summary.json ← 回测结论摘要
└── references/               ← [可选]
    └── REFERENCE.md          ← 参数详解
```

---

## 3. SKILL.md 格式

### 3.1 Frontmatter（必填字段）

```yaml
---
name: zen-7-1                   # 必须与目录名一致；小写 + 连字符；1-64字符
description: |                  # 策略的用途和适用场景描述；1-1024字符
  动态波动率+网格共振策略 v7.1。
  适用于 BTC/USDT 1m K线 + 60m 重采样。
  含 ATR 动态止盈/止损和网格摊薄机制。
metadata:
  author: TradingGarage         # 作者
  version: "7.1"                # 策略版本
  symbol: BTC-USDT-SWAP         # 主要适用标的
  timeframe: 1m                 # 数据频率
  min_capital: "5000"           # 建议最低资金（USDT）
---
```

#### name 字段规则
- 仅允许小写英文字母、数字、连字符 (`a-z`, `0-9`, `-`)
- 不能以连字符开头或结尾，不能含连续连字符
- 必须与父目录名完全一致

### 3.2 Body（正文）

正文使用 Markdown 格式，应包含：

1. **策略逻辑概述** — 用自然语言描述进出场核心逻辑
2. **适用市场条件** — 明确此策略适合什么行情（趋势/震荡/高波动等）
3. **参数说明** — 每个参数的含义与推荐范围（可引用 `references/REFERENCE.md`）
4. **风险提示** — 已知的策略局限性

---

## 4. config.json 格式

```json
{
  "symbol": "BTC-USDT-SWAP",      // 交易标的（Runner 层使用）
  "timeframe": "1m",              // 数据频率（Runner 层使用）
  "initial_balance": 10000,       // 默认初始资金
  "params": {                     // 传入策略 __init__ 的参数
    "resample_min": 60,
    "capital": 10000,
    "grid_layers": 5,
    "grid_drop_pct": 0.02,
    "hard_sl_pct": -0.10,
    "tp_min_profit_pct": 0.03
  }
}
```

**跨机器参数覆盖**：在目标机器上可创建 `config.local.json`，Runner 会以 local 优先：

```json
{
  "initial_balance": 5000,
  "params": {
    "capital": 5000
  }
}
```

---

## 5. scripts/strategy.py 接口规范

`scripts/strategy.py` 必须包含且仅包含一个继承 `BaseStrategy` 的策略类。

### 5.1 必须实现的接口

```python
from strategies.base import BaseStrategy
from core import MarketData, Signal, StrategyContext
from typing import List

class MyStrategy(BaseStrategy):

    def __init__(self, name="my-strategy", **params):
        """
        所有可调参数通过 **params 注入。
        不应在此处 hardcode 任何数值，全部从 params.get() 读取。
        """
        super().__init__(name, **params)
        ...

    def on_data(self, data: MarketData, context: StrategyContext) -> List[Signal]:
        """
        接收每根 K 线数据，返回交易信号列表。
        - 无信号时返回 []，不得返回 None
        - 不得直接调用交易 API，只能返回 Signal
        """
        ...
```

### 5.2 推荐实现的接口

```python
    def on_fill(self, fill: FillEvent):
        """成交回调，用于更新内部网格/成本等状态"""
        ...

    def get_status(self, context=None) -> dict:
        """
        返回策略当前内部状态，供 Dashboard 展示。
        必须包含 'name' 字段。推荐字段：rsi, layers, avg_cost, stats
        """
        return {"name": self.name, ...}

    def get_ui_manifest(self) -> dict:
        """声明 Dashboard 所需渲染组件（可选）"""
        ...
```

### 5.3 禁止事项

- ❌ 不得在 `scripts/strategy.py` 中直接调用 OKX API
- ❌ 不得在 `scripts/strategy.py` 中读写文件（持久化由 Runner 统一管理）
- ❌ 不得在 `__init__` 中 hardcode 参数数值（应全部通过 `params.get()` 读取）
- ❌ 不得 import 项目外的未声明第三方库（需在 SKILL.md 中通过 `compatibility` 字段声明）

---

## 6. SkillLoader 加载流程

```
SkillLoader.load("strategies/skills/zen-7-1")
    │
    ├─ 1. 读取 SKILL.md frontmatter → skill_meta
    ├─ 2. 读取 config.json (+ config.local.json 合并覆盖)
    ├─ 3. importlib 动态导入 strategy.py
    ├─ 4. 自动发现 BaseStrategy 子类（有且仅有一个）
    └─ 5. 实例化：MyStrategy(name=skill_meta['name'], **config['params'])
           └─ 返回 (strategy_instance, skill_meta)
```

Runner 使用示例：

```python
from runner.skill_loader import SkillLoader

loader = SkillLoader()
strategy, meta = loader.load("strategies/skills/zen-7-1")

slot = StrategySlot(
    slot_id=meta["name"],
    display_name=f"{meta['name']} v{meta.get('version', '?')}",
    strategy=strategy,
    executor=PaperExecutor(config["initial_balance"]),
    initial_balance=config["initial_balance"],
    skill_meta=meta,
)
runner.add_slot(slot)
```

---

## 7. 目录命名规范

| 示例 | 合法？ | 原因 |
|---|---|---|
| `zen-7-1` | ✅ | |
| `grid-jeff-6-5` | ✅ | |
| `Zen71` | ❌ | 含大写 |
| `zen_7_1` | ❌ | 含下划线 |
| `-zen` | ❌ | 连字符开头 |
| `zen--7` | ❌ | 连续连字符 |

---

## 8. 版本控制建议

- Skill 包应独立进行 Git 管理（或单独 zip 归档）
- `config.local.json` 应加入 `.gitignore`（机器私有配置）
- `references/` 中的回测结论建议包含测试数据集的时间范围

---

## 附录：Skill 包快速校验清单

```
□ 目录名与 SKILL.md 中 name 字段一致
□ config.json 包含 symbol、params 字段
□ strategy.py 中有且仅有一个 BaseStrategy 子类
□ strategy.py 中所有参数通过 params.get() 读取，无 hardcode
□ on_data() 无信号时返回 []，不返回 None
□ 不直接调用 OKX API 或写文件
```
