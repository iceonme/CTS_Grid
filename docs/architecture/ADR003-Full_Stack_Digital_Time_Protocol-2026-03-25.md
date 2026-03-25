# ADR003: 全链路数字化时间协议与策略生命周期规范

## 状态
已通过 (Accepted) - 2026-03-25

## 上下文 (Context)
在开发 V93 Dashboard 时，系统面临三个核心痛点：
1. **时区偏差**：ISO 字符串导致浏览器渲染出现 8 小时偏移。
2. **初始化竞态**：异步启动时，首根行情信号可能丢失，导致策略预热失败。
3. **数据类型崩溃**：数字化改造后，Pandas/Numpy 的 int64 类型与 datetime 原生方法不兼容导致 AttributeError。

## 决策 (Decisions)

### 1. 全链路 Unix 数字化 (Full-Stack Unix Epoch)
- **协议层**：所有总线事件（`MarketUpdateEvent` 等）中的 `timestamp` 统一采用 **Unix 秒级整数 (float/int)**。
- **计算层**：Pandas DataFrame 索引必须保持数字化，严禁在计算中间态转回 `datetime` 对象。
- **渲染层**：前端 `script.js` 统一使用 `new Date(ts * 1000)` 进行本地化呈现。

### 2. 策略“HDMI输出”模式 (Proactive HDMI Pattern)
- **职责**：策略不再仅是消费者，必须主动为 Dashboard 提供“高质量画面驱动”。
- **补全要求**：
    - 历史数据（Preheat）完成后，必须立即广播 `ui_history_update`。
    - 必须响应 `ui_snapshot_request` 握手信号。

### 3. 异步初始化“冷启动保险” (Cold-Start Safety)
- **实现**：在 `BaseStrategy.on_init` 中注入 3 秒延时任务。
- **逻辑**：若 3 秒内未接到行情触发 `initialize()`，则强制冷启动执行预热。

### 4. 数据防御编码规范 (Robust Coding)
- **禁止**：对数字化索引调用 `.isoformat()` 或 `.timestamp()`。
- **推荐**：使用 `datetime.fromtimestamp(ts)` 进行非破坏性格式化。
- **时间差**：直接使用数学减法 `(t2 - t1)`，禁止使用 `.total_seconds()`。

## 后果 (Consequences)
- **优点**：彻底根治时差问题，提高系统并发启动的成功率，减少计算层的类型转换开销。
- **风险**：对旧代码的迁移需要仔细核查所有涉及 `datetime` 属性的调用点。

---
**核准人**：Antigravity / USER
