# 数据目录重排方案 (Data Reorganization)

将根目录下的 `data/` 目录迁移至 `factory/` 目录下，以符合“生产/Runner环境”与“研究/工厂环境”分离的架构原则。

## 用户审核要求

> [!IMPORTANT]
> 此操作将改变历史行情数据（CSV文件）的存储路径。如果你有其他外部脚本直接引用 `data/market/`，需要同步更新。

## 拟议变更

### [Component] File System Structure

#### [DELETE] [data/](file:///c:/CS/CTA2/data)
#### [DELETE] [archive/](file:///c:/CS/CTA2/archive)
删除根目录下的 `data/` 和 `archive/` 文件夹。

#### [NEW] [factory/data/market/](file:///c:/CS/CTA2/factory/data/market)
#### [NEW] [factory/archive/](file:///c:/CS/CTA2/factory/archive)
将原 `data/market/` 和 `archive/` 下的所有内容迁移至 `factory/` 对应路径。

### [Component] Factory Research & Tests

#### [MODIFY] [run_v60.py](file:///c:/CS/CTA2/factory/tests/run_v60.py)
#### [MODIFY] [evolve_z7.py](file:///c:/CS/CTA2/factory/optimizer/evolve_z7.py)
#### [MODIFY] [run_v85_static_viewer.py](file:///c:/CS/CTA2/factory/backtest/run_v85_static_viewer.py)
#### [MODIFY] [run_interactive_replay.py](file:///c:/CS/CTA2/factory/backtest/run_interactive_replay.py)
#### [MODIFY] [run_backtest_arena_viewer.py](file:///c:/CS/CTA2/factory/backtest/run_backtest_arena_viewer.py)
#### [MODIFY] [run_backtest_arena_fast.py](file:///c:/CS/CTA2/factory/backtest/run_backtest_arena_fast.py)
更新数据加载路径，将 `data/market/` 或 `../../data/market/` 等相对路径映射到新的 `factory/data/market/`。

## 验证计划

### 自动化测试
- 运行 `python factory/tests/run_v60.py`，确认其能正确找到并加载 `BTC_USDT_1m.csv`。

### 手动验证
- 确认 `launcher.py` 和 `console/` 目录下的脚本运行正常（确认它们本就不依赖此目录）。
