# INS005: Agent-Friendly 控制平面设计 (2026-03-15)

## 1. 核心洞察 (Insight)

在 Agentic Trading System (ATS) 中，系统不仅仅是给人用的，更是给其他 AI Agent 调用的。因此，系统的入口不应仅仅是一个“启动脚本”，而应是一个高度标准化、可预测、且具备自检能力的 **“控制平面 (Control Plane)”**。

## 2. 设计原则 (Design Philosophy)

### 2.1 统一总线 (Unified CLI)
- 将所有的生产指令（Run, Check, Config）收敛至单一入口 `ats.py`。
- 减少 Agent 搜索脚本的心智负担。

### 2.2 机器友好 (Agent Friendly)
- **结构化输出**: 提供 `--json` 开关，让 Agent 直接处理返回的性能指标或错误日志。
- **无交互执行**: 避免任何 `input()` 阻塞，所有指令均通过 Flag 彻底闭环。
- **语义化指令**: 采用 `ats run <skill>` 这种动词+名词的结构，方便 LLM 进行逻辑转换。

### 2.3 确定性与安全性
- 通过 `SkillLoader` 在控制平面层进行强类型校验。
- 利用 `.env` 实现密钥的物理隔离，防止 Agent 在处理配置文件时意外泄露敏感信息。

## 3. 演进路线

- **Phase 1 (Done)**: 重命名为 `ats.py`，支持 `run` 子命令。
- **Phase 2 (Pending)**: 整合 `factory` 逻辑，支持 `ats backtest`。
- **Phase 3 (Vision)**: 引入 `ats doctor` 或 `ats check`，实现 Skill 规范的自动审计。

---
> “最好的架构是即使没有人类干预，系统也能通过标准接口自我运行与进化。”
