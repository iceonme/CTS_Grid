# 多策略并发架构重构 Walkthrough
**日期**: 2026-02-28 21:57
**任务**: 多策略并发运行 + 前端启动/暂停/重置控制

## 变更摘要

### 新增文件
| 文件 | 说明 |
|------|------|
| `runner/__init__.py` | runner 包初始化 |
| `runner/multi_strategy_runner.py` | 多策略管理核心：`StrategySlot` + `MultiStrategyRunner` |
| `run_cts1.py` | 新的 CTS1 主入口，共享数据流广播，前端可控 |

### 修改文件
| 文件 | 说明 |
|------|------|
| `dashboard/server.py` | 新增 `start_strategy`/`pause_strategy` SocketIO 事件及 `on_control_callback` 接口 |
| `dashboard/templates/dashboard.html` | 新增启动(▶)/暂停(⏸)按钮、`updateControlButtons()` 状态联动函数、`strategy_status_changed` 事件处理 |

## 架构设计
```
run_cts1.py
  └─ MultiStrategyRunner
       ├─ OKXDataFeed (单一连接, 广播)
       ├─ StrategySlot grid_v40 (Grid RSI V4.0, PaperExecutor)
       └─ StrategySlot grid_v51 (Grid RSI V5.1, PaperExecutor)
                ↓ dashboard.update(data, strategy_id=xxx)
          DashboardServer (前端按房间接收各策略数据)
                ↑ emit: start_strategy / pause_strategy / reset_strategy
```

## 运行方法
```powershell
python run_cts1.py
```
浏览器打开 `http://localhost:5000`，选择策略后点击「▶ 启动」。

## 关键设计决策
- **共享数据源**: 单个 `OKXDataFeed` 广播，避免重复 API 调用
- **异常隔离**: 每个 slot 的 `on_bar` 用独立 try/except 包裹
- **暂停机制**: `threading.Event` 标志，不强制停止线程，tick 级检查
- **持久化隔离**: 状态文件命名为 `trading_state_{slot_id}.json`
