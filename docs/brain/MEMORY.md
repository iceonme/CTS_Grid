# 🧠 TradeStation AI-Brain 记忆库 (Memories)

本文件作为系统的核心知识沉淀，区分“长期架构思想（LTM）”与“短期操作实录（STM）”。

---

## 🏗️ 长期记忆 (Long-term Memory)

### 1. 核心架构哲学 (Architectural Philosophy)
- **三权分立 (Tri-Pillar Parallelism)**: 系统由 `datafeeds`（行情源）、`executors`（执行器）、`strategies`（策略脑）三大支柱平行支撑。它们物理隔离，职责单一。
- **底座托管机制 (Host-Plugin Pattern)**: `console/` 目录作为底座提供基础设施；`cartridges/` 目录作为插件提供业务能力。策略看板通过路由动态挂载。
- **无状态化逻辑**: 策略函数应保持纯粹逻辑，状态管理（State Management）由引擎中枢统一负责。
- **命名规范**: Skill 文件夹强制使用下划线 `snake_case` 定名，以确保 Python 导入路径的合法性。

### 🚩 关键里程碑 (Milestones)
- **[2026-03-24]**: 成功将 ETH-V93 策略从原生单体架构平移至 CTS1 模块化环境，确立了“三权分立”的最终物理目录标准。

---

## ⚡ 短期记忆 (Short-term Memory)

### 最近操作记录 (Recent Actions)
- **[2026-03-24] V93 迁移与底座优化**:
    - 物理路径重构：将 `bridge` 下的所有组件平移至顶级 `cartridges` 目录。
    - 工具类重定位：将 `okx_api.py` 迁移至 `console/utils/` 作为全局公共底座。
    - Dashboard 瘦身：移除冗余的 `server_60.py` 及旧版静态模板，实现看板的动态插拔。
    - 兼容性修复：解决了 SkillLoader 环境下策略包的相对导入冲突。
    - 环境验证：通过 `SkillLoader` 批量实例化测试，闭环验证了行情、执行与策略的加载通路。
