# ADR002: Dashboard Skill 化与插件式 UI 架构

*   **状态**: 已接受 (Accepted)
*   **日期**: 2026-03-25
*   **决策者**: Human & Antigravity (AI)

## 1. 背景 (Context)

在重构后的 v3.1 异步事件驱动架构中，系统需要一个可视化监控界面（Dashboard）。
最初的考量是将其作为 `ATSEngine` 的内置功能，还是由一个独立的 Skill 来承担。同时，系统需要兼顾“主机通用监控”和“策略自定义监控”两个场景。

## 2. 决策 (Decision)

我们决定将 Dashboard **完全 Skill 化**，定义为 `UISkill` 类型，并采用 **“核心服务器 + 插件式内容”** 的设计模式。

### 详细规范：
1.  **观察员模式**：Dashboard 作为一个独立的 Skill 存在，通过 `EventBus` 订阅全量事件（行情、仓位、信号、成交）。它不持有核心交易状态，仅作为“数据消费者”。
2.  **全异步隔离**：Dashboard 的 Backend（Flask/SocketIO）运行在独立线程/进程中，严禁阻塞 `ATSEngine` 的总线分发循环。
3.  **插件式模板注入**：
    *   `DashboardServer` 自动扫描已加载策略 Skill 目录下的 `dashboard/` 文件夹。
    *   通过自定义路由映射（如 `/strategy/<sid>/`），将各策略专属的 UI 内容挂载至主服务器。
4.  **宿主视图 (Host View)**：提供全局日志流展示、系统资源监控及基于 JSONL 文件的离线/实时数据分析。

## 3. 后果 (Consequences)

### 正面影响：
*   **低耦合**：Dashboard 的崩溃或重启完全不影响核心交易链路。
*   **极高性能**：支持 Headless 模式运行，在高性能实盘环境下可随时剥离 UI。
*   **扩展性**：支持多种显示终端并存（如 Web, Mobile, Telegram Bot），只需增加不同的 `UISkill` 订阅总线。

### 负面影响：
*   **通信消耗**：数据流经总线分发会有微量开销（对 1s 级及以上的网格策略可忽略不计）。
*   **复杂度**：需要维护一套 Skill 挂载与静态文件映射的逻辑。

## 4. 状态 (Status)
本 ADR 现作为 `ATSEngine` v3.1 开发标准的最高准则执行。
