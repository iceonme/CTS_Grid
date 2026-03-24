# 多策略并发架构重鏋?Walkthrough
**日期**: 2026-02-28 21:57
**任务**: 多策略并发运琛?+ 前端启动/暂停/重置控制

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
| `dashboard/server.py` | 新增 `start_strategy`/`pause_strategy` SocketIO 事件鍙?`on_control_callback` 接口 |
| `dashboard/templates/dashboard.html` | 新增启动(鈻?/暂停(鈴?按钮、`updateControlButtons()` 鐘舵€佽仈动函鏁般€乣strategy_status_changed` 事件处理 |

## 架构设计
```
run_cts1.py
  └─ MultiStrategyRunner
       ├─ OKXDataFeed (单一连接, 广播)
       ├─ StrategySlot grid_v40 (Grid RSI V4.0, PaperExecutor)
       └─ StrategySlot grid_v51 (Grid RSI V5.1, PaperExecutor)
                鈫?dashboard.update(data, strategy_id=xxx)
          DashboardServer (前端按房间接收各策略数据)
                鈫?emit: start_strategy / pause_strategy / reset_strategy
```

## 运行方法
```powershell
python run_cts1.py
```
浏览器打寮€ `http://localhost:5000`锛岄€夋嫨策略后点鍑汇€屸柖 启动銆嶃€?

## 关键设计决策
- **共享数据婧?*: 单个 `OKXDataFeed` 广播，避免重澶?API 调用
- **异常隔离**: 每个 slot 鐨?`on_bar` 用独绔?try/except 包裹
- **暂停机制**: `threading.Event` 标志，不强制停止线程，tick 级检鏌?
- **持久化隔绂?*: 鐘舵€佹枃件命名为 `trading_state_{slot_id}.json`
