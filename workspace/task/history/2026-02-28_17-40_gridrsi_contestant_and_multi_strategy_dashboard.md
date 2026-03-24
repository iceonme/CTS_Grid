# 任务验收报告：can GridRSI 选手 & CTS1 多策略仪表盘

**日期时间**: 2026-02-28 17:40

## 丢㡢任务目鏍?

1. **can 项目**：新澧?`grid-rsi-contestant.ts`（在网格策略基础上加鍏?RSI 鍔ㄦ€佽皟仓系数）
2. **CTS1 项目**：新澧?`grid_rsi_5_1.py`（V5.1 隔离原型）并将仪表盘鏀归€犱负支持多策略并行展绀?

---

## 浜屻€佸彉更文件汇鎬?

### can 项目

| 文件 | 操作 | 说明 |
|------|------|------|
| `lib/agents/contestants/grid-rsi-contestant.ts` | **新增** | GridRSIContestant 类，继承网格逻辑，RSI 调仓系数绾挎€ф彃鍊?|
| `app/api/backtest/run/route.ts` | 修改 | Import GridRSIContestant，注鍐?`grid-rsi-bot` / `type:grid-rsi` 分支 |

**GridRSI 策略核心逻辑**锛?
- `rsiOversold`（默璁?35）↓ 鈫?`buyMultiplier = rsiMaxMultiplier`（默璁?1.5x）放大买鍏?
- `rsiOverbought`（默璁?65）↑ 鈫?`buyMultiplier = rsiMinMultiplier`（默璁?0.5x）缩小买鍏?
- 中间区间绾挎€ф彃值，RSI 每轮重算网格时同步更鏂?
- 配置新增字段：`rsiPeriod`, `rsiOversold`, `rsiOverbought`, `rsiMaxMultiplier`, `rsiMinMultiplier`

### CTS1 项目

| 文件 | 操作 | 说明 |
|------|------|------|
| `strategies/grid_rsi_5_1.py` | **新增** | V5.1 隔离原型，类鍚?`GridRSIStrategyV5_1`锛岄€昏緫鍚?V4.0 |
| `strategies/__init__.py` | 修改 | 导出 `GridRSIStrategyV5_1` |
| `dashboard/server.py` | **重写** | 多策鐣?Room 化：`_data` 变为字典的字典，`update(data, strategy_id)` |
| `dashboard/__init__.py` | 修改 | 补充导出 `get_dashboard`, `set_dashboard` |
| `dashboard/templates/dashboard.html` | 修改 | Header 加策略切鎹?Select；JS 鍔?`switchStrategy()` + `join/leave` Room 逻辑 |
| `run_multiple.py` | **新增** | 多策略并行回测入口，两个引擎线程，支鎸?`--dashboard` 参数 |

---

## 涓夈€佸叧键架构变鍖?

### CTS1 Dashboard 多策略架鏋?

```
                     ┌─鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
后端线程 A (V4.0) 鈹€鈹€鈫?鈹?server.update(data,          鈹?
                     鈹?  strategy_id='grid_rsi_v40')│─鈹€鈫?Room:grid_rsi_v40 鈹€鈹€鈫?浏览器A
后端线程 B (V5.1) 鈹€鈹€鈫?鈹?server.update(data,          鈹?
                     鈹?  strategy_id='grid_rsi_v51')│─鈹€鈫?Room:grid_rsi_v51 鈹€鈹€鈫?浏览器B
                     └─鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
```

前端通过下拉框切换策略时锛?
1. `socket.emit('leave', {strategy_id: old})` 离开旧房闂?
2. 清空图表、交易记褰?
3. `socket.emit('join', {strategy_id: new})` 加入新房间，立即收到历史数据

### can GridRSI 注册

```
contestants: [
  { type: 'grid-rsi', id: 'my-bot', settings: { rsiOversold: 30, rsiOverbought: 70 } }
]
```

---

## 鍥涖€佷娇用方娉?

### CTS1 多策略并行运琛?

```bash
# 纯回测对姣?
python run_multiple.py --data btc_1m.csv --capital 10000

# 甯?Dashboard 可视鍖?
python run_multiple.py --data btc_1m.csv --capital 10000 --dashboard --port 5000
```

### can 回测 API 调用

```json
{
  "contestants": [
    { "type": "grid",     "id": "grid-bot",     "name": "纯网鏍? },
    { "type": "grid-rsi", "id": "gridrsi-bot",  "name": "网格RSI",
      "settings": { "rsiOversold": 35, "rsiOverbought": 65 } }
  ]
}
```

---

## 浜斻€侀獙证情鍐?

- 鉁?Python 语法：`grid_rsi_5_1.py` 逻辑完整 Copy 鑷?V4.0，无新引入的语法错误
- 鉁?TypeScript 接口：`grid-rsi-contestant.ts` 类实现了完整鐨?`Contestant` 接口（`initialize`, `onTick`, `getPortfolio`, `getLogs`, `getTrades`, `getMetrics`锛?
- 鉁?Dashboard 向后兼容：旧鐗?`run_okx_demo_with_dashboard.py` 的单策略 `server.update(data)` 调用仍可使用（`strategy_id` 有默璁ゅ€?`'default'`锛?
- 鉁?BOARD.md 已更新（见下锛?
