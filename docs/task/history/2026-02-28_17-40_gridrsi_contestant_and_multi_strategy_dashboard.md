# 任务验收报告：can GridRSI 选手 & CTS1 多策略仪表盘

**日期时间**: 2026-02-28 17:40

## 一、任务目标

1. **can 项目**：新增 `grid-rsi-contestant.ts`（在网格策略基础上加入 RSI 动态调仓系数）
2. **CTS1 项目**：新增 `grid_rsi_5_1.py`（V5.1 隔离原型）并将仪表盘改造为支持多策略并行展示

---

## 二、变更文件汇总

### can 项目

| 文件 | 操作 | 说明 |
|------|------|------|
| `lib/agents/contestants/grid-rsi-contestant.ts` | **新增** | GridRSIContestant 类，继承网格逻辑，RSI 调仓系数线性插值 |
| `app/api/backtest/run/route.ts` | 修改 | Import GridRSIContestant，注册 `grid-rsi-bot` / `type:grid-rsi` 分支 |

**GridRSI 策略核心逻辑**：
- `rsiOversold`（默认 35）↓ → `buyMultiplier = rsiMaxMultiplier`（默认 1.5x）放大买入
- `rsiOverbought`（默认 65）↑ → `buyMultiplier = rsiMinMultiplier`（默认 0.5x）缩小买入
- 中间区间线性插值，RSI 每轮重算网格时同步更新
- 配置新增字段：`rsiPeriod`, `rsiOversold`, `rsiOverbought`, `rsiMaxMultiplier`, `rsiMinMultiplier`

### CTS1 项目

| 文件 | 操作 | 说明 |
|------|------|------|
| `strategies/grid_rsi_5_1.py` | **新增** | V5.1 隔离原型，类名 `GridRSIStrategyV5_1`，逻辑同 V4.0 |
| `strategies/__init__.py` | 修改 | 导出 `GridRSIStrategyV5_1` |
| `dashboard/server.py` | **重写** | 多策略 Room 化：`_data` 变为字典的字典，`update(data, strategy_id)` |
| `dashboard/__init__.py` | 修改 | 补充导出 `get_dashboard`, `set_dashboard` |
| `dashboard/templates/dashboard.html` | 修改 | Header 加策略切换 Select；JS 加 `switchStrategy()` + `join/leave` Room 逻辑 |
| `run_multiple.py` | **新增** | 多策略并行回测入口，两个引擎线程，支持 `--dashboard` 参数 |

---

## 三、关键架构变化

### CTS1 Dashboard 多策略架构

```
                     ┌─────────────────────────────┐
后端线程 A (V4.0) ──→ │ server.update(data,          │
                     │   strategy_id='grid_rsi_v40')│──→ Room:grid_rsi_v40 ──→ 浏览器A
后端线程 B (V5.1) ──→ │ server.update(data,          │
                     │   strategy_id='grid_rsi_v51')│──→ Room:grid_rsi_v51 ──→ 浏览器B
                     └─────────────────────────────┘
```

前端通过下拉框切换策略时：
1. `socket.emit('leave', {strategy_id: old})` 离开旧房间
2. 清空图表、交易记录
3. `socket.emit('join', {strategy_id: new})` 加入新房间，立即收到历史数据

### can GridRSI 注册

```
contestants: [
  { type: 'grid-rsi', id: 'my-bot', settings: { rsiOversold: 30, rsiOverbought: 70 } }
]
```

---

## 四、使用方法

### CTS1 多策略并行运行

```bash
# 纯回测对比
python run_multiple.py --data btc_1m.csv --capital 10000

# 带 Dashboard 可视化
python run_multiple.py --data btc_1m.csv --capital 10000 --dashboard --port 5000
```

### can 回测 API 调用

```json
{
  "contestants": [
    { "type": "grid",     "id": "grid-bot",     "name": "纯网格" },
    { "type": "grid-rsi", "id": "gridrsi-bot",  "name": "网格RSI",
      "settings": { "rsiOversold": 35, "rsiOverbought": 65 } }
  ]
}
```

---

## 五、验证情况

- ✅ Python 语法：`grid_rsi_5_1.py` 逻辑完整 Copy 自 V4.0，无新引入的语法错误
- ✅ TypeScript 接口：`grid-rsi-contestant.ts` 类实现了完整的 `Contestant` 接口（`initialize`, `onTick`, `getPortfolio`, `getLogs`, `getTrades`, `getMetrics`）
- ✅ Dashboard 向后兼容：旧版 `run_okx_demo_with_dashboard.py` 的单策略 `server.update(data)` 调用仍可使用（`strategy_id` 有默认值 `'default'`）
- ✅ BOARD.md 已更新（见下）
