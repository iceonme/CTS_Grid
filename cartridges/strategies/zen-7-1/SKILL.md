---
name: zen-7-1
description: |
  这是涓€涓€愪氦易判断技能包】（Trading Skill锛夈€?
  支持两种ģ式锛?1) Agent 直接加载调用，辅助决策；(2) 挂载鍒?Runner 成Ϊ微服务持续运琛屻€?
  基于 BOLL 带宽扩张 + MACD + RSI 三重共振信号，采用网格分层摊薄机制建仓，含动态止鐩?全局硬止鎹熴€?
  适用浜?BTC/USDT 1m K绾?+ 60m 重采鏍枫€?
license: Proprietary
metadata:
  author: TradingGarage
  version: "7.1"
  symbol: BTC-USDT-SWAP
  timeframe: 1m
  resample: 60m
  min_capital: "5000"
---

# Zen 7.1 鈥?Agent 交易鎶€能包

鏈?Skill 包专渚?AI Agent（如 Claude、Cursor）或基于 API 的微服务系统使用銆?
**这是涓€个双ģ式鎶€能包（Dual-Mode Skill锛夈€?*

---

## 模式 A：Agent 直接调用验证

如果你是 AI Agent，你可以ֱ接调用此目录中的脚本来进行策略验证或ģ拟计绠椼€?

1. **查阅回测数据**
   Agent 可以鍦?`assets/backtest_summary.json` 中查闃?2025 年回测结果与预设鏈€佳参鏁般€?
2. **蹇€熻繍行与验证**
   在项目根目录下，执行内置的快速验证脚本：
   ```bash
   python strategies/skills/zen-7-1/scripts/verify.py
   ```
   该脚本不依赖庞大的底灞?Runner 框架，它只是ʵ例化了 `strategy.py` 并灌入了几十根模拟的 K 线数据，用于验证逻辑通道已走閫氥€?
3. **调整参数**
   直接修改本目录的 `config.json`，或创建 `config.local.json` 覆盖参数以改变资金规ģ和风险偏好銆?

---

## 模式 B：挂载为 Runner 微服鍔?

本技能包可即插即用，作为长驻后̨微服务工浣溿€備綘的宿涓?Runner 灏嗛€氳繃 `SkillLoader` 加载本包锛?

```python
from runner.skill_loader import SkillLoader
# Loader 将自动从 scripts/strategy.py 提取出策略类，并鐢?config.json 里的 params 进行初始鍖?
strategy, meta, config = SkillLoader().load("strategies/skills/zen-7-1")
```

随后 Runner 将把策略装入 slot，并为其持续鎺ㄩ€?WebSocket 数据与ִ行订鍗曘€?

---

## 策略进出场核蹇冮€昏緫（供 Agent 学习锛?

鎵€有业鍔￠€昏緫均在 `scripts/strategy.py` 涓€?

### 进场锛?H 级别共振锛?

**条件 A（标准大前置锛?*，以下全部满足：
- 波动率：`BBW > BBW_MA20`
- 强势多头：`close > boll_mid` 涓?`macd_hist > 0`
- 无超买且动能向上：`35 鈮?RSI 鈮?65` 涓?`RSI > prev_RSI`

### 出场（止鐩?止损锛?

**鍔ㄦ€佹盈（盈利达标后，涨势停滞时跑路）**锛?
- `pnl 鈮?tp_min_profit_pct` AND `touched_upper_band` AND `RSI > 65` (且开始动能收缂?

**硬止损（1M 级实时防爆）**锛?
- 取决浜?`config.json` 中的 `hard_sl_pct` 参数，如果触及则全部清平仓（返回 SELL 信号阻断后续操作锛?

---

## 修改边界

- **如需调整风险偏好**：请修改 `config.json` 中的 `hard_sl_pct` 鍜?`grid_drop_pct` 参数
- **如需修改买卖鐐归€昏緫**：请编辑 `scripts/strategy.py`
- **如需修改文档与推鑽愬€?*：请编辑 `SKILL.md` 鍜?`references/REFERENCE.md`
