# MACD/RSI 图表时间轴未对齐的修复 (时间尺度错位问题)

## 问题描述
用户反馈在 `V5.1` (以及 `V4` 兼容策略) 面板中，K线实时数据更新正常并显示当前时间（例如 17:06），但下方的 MACD 指标、RSI 指标以及资产曲线的连线**都在 K线右侧留白（未能连接到当前 K线时间的垂直网格线上）**。虽然鼠标悬停 (Crosshair) 时 tooltip 能够正确显示对应的最新指标数据，但在视觉表现上形成了“指标图比K线图短一截”的剥离感，未能做到严格的“向右对齐”。

## 根本原因 (Root Cause)
由于采用 `Lightweight Charts` 库作为前端组件，各个副图（RSI、MACD、Equity）分别在不同的 `Chart` 实例中渲染，并通过 `timeScale().subscribeVisibleTimeRangeChange` 进行互相绑定。此时存在一个底层渲染机制陷阱：

1. **`logicalRange` (逻辑索引偏移)**
前端的 `syncCharts` 同步逻辑复用了 `timeScale().getVisibleLogicalRange()` 去跨图表同步。由于依赖了**逻辑索引 (Index)** 而非独立时间戳，这要求主图与所有副图的**数据点总流长必须严格 1:1 对等**。
2. **后加载指标 (Warm-up 阶段剔除空值导致的点数不匹配)**
在系统初始化阶段 (`build_history_data`)，计算 RSI 和 MACD 时由于需要预留计算窗口 (例如 14, 26 周期等)，初始的若干根历史 K线不会产生有意义的指标值，Python 后端虽然输出了空值列表，但前端原有的 `prepareBatchData` 函数在解析时，**直接利用 `continue` 跳过了所有 `v === null` 的坏点**。
3. **连锁反应**
因为早期数据点被直接抛弃，MACD/RSI 组件最终填充到 DataFrame 里的有效点数量**少于 K线的总点数**。例如缺失了最开始的 14 个点。这就导致当 K线运行至绝对索引 N（即右边界最末端）时，RSI 组件的右边界绝对索引仅为 N-14。因此在两图通过 `logicalIndex` 保持同步平移时，副图表现为**在右侧向后回退了 14 根 K线的距离，留下明显留白！**

## 解决方案

**1. 后端补充空数据节点占位 (`run_cts1.py`)**
在主循环 `build_history_data` 里，不仅 RSI 初始化时要 `history_rsi.append({'t': ts_ms, 'v': None})` 填补缺失位，针对 MACD 因为异常而无法运算的区间（未到慢线周期等），显式地推送包含正确 `ts_ms` 且全部参数值为 `None` 的骨架字典作为时间占坑点。

**2. 前端引入 Whitespace (空白占位) 协议 (`dashboard.html`, `dashboard_5_1.html`)**
重构 `prepareBatchData` 和相关指标装载逻辑：
针对所有带有正确时间点属性 `t` 但数值本身为 `undefined` / `null` 的数据点，**不能抛弃。转而向 Lightweight Charts 插入特殊的 `{ time: ts }` 没有 `value` 属性的数据对象**。
这在 Lightweight Charts 内部被称为 [Whitespace data items](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/WhitespaceData)，它们能够在时间轴上霸占一个真实的业务坐标但本身不进行渲染动作，这就从根本上修复了逻辑索引的位移误差。

**3. 实时增量更新的适配补充 (`dashboard_5_1.html`)**
同步修改了 `updateRSI()`, `updateMACD()` 和 `updateEquity()` 三个核心实时注入方法：如果计算接收到的是无值（诸如策略被终止产生 `null` 或策略尚未启动），不跳过 `update()` 调用，而是继续将 `{ time }` 对象喂入，确保数据管道里的时间流向始终完全平行吻合主K线！

## 交付与验证
代码均已修改并存盘。重新刷新或者重启服务端后，可以观察到无论策略当前指标是否满足运算周期，副图的时间标尺必定与主K线实现严格对齐，右侧留白消失，图形在 X 轴向上的渲染锚定真正做到了 1:1。
