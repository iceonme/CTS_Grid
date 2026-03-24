# MACD/RSI 图表时间轴未对齐的修澶?(时间尺度错λ问题)

## 问题描述
用户反馈鍦?`V5.1` (以及 `V4` 兼容策略) 面板中，K线实时数据更新正常并显示当前时间（例濡?17:06），但下方的 MACD 指标、RSI 指标以及资产曲线的连绾?*都在 K线右侧留白（未能连接到当鍓?K线时间的垂直网格线上锛?*。虽然鼠标悬鍋?(Crosshair) 鏃?tooltip 能够正确显示对应的最新指标数据，但在视觉表现上形成了“指标图比K线ͼ短一鎴€濈殑剥离感，未能做到严格鐨勨€滃悜右对榻愨€濄€?

## 根本原因 (Root Cause)
由于采用 `Lightweight Charts` 库作为ǰ端组件，各个副图（RSI、MACD、Equity）分别在不同鐨?`Chart` 实例中渲Ⱦ，骞堕€氳繃 `timeScale().subscribeVisibleTimeRangeChange` 进行互相绑定。此ʱ存在һ个底层渲染机制陷阱：

1. **`logicalRange` (逻辑索引偏移)**
前端鐨?`syncCharts` 同步逻辑复用浜?`timeScale().getVisibleLogicalRange()` 去跨图表同步。由于依赖了**逻辑索引 (Index)** 而非独立ʱ间戳，这要求主图与鎵€有副图的**数据鐐规€绘祦长必须严鏍?1:1 对等**銆?
2. **后加载指鏍?(Warm-up 阶段剔除绌哄€煎致的点数不匹閰?**
在系统初始化阶段 (`build_history_data`)，计绠?RSI 鍜?MACD 时由于需要预留计算窗鍙?(例如 14, 26 周期绛?，初始的若干根历鍙?K线不会产生有意义的指鏍囧€硷紝Python 后端虽然输出了空值列表，但ǰ端原有的 `prepareBatchData` 函数在解析时锛?*直接利用 `continue` 跳过了所鏈?`v === null` 的坏鐐?*銆?
3. **连锁反应**
因为早期数据点被ֱ接抛弃，MACD/RSI 组件鏈€终填充到 DataFrame 里的有效点数閲?*少于 K线的总点鏁?*。例如缺失了鏈€寮€始的 14 个点。这就导致当 K线运行至绝对索引 N（即右边界最末端）时，RSI 组件的右边界绝对索引仅为 N-14。因此在两图通过 `logicalIndex` 保持同步ƽ移时，副图表现涓?*在右侧向后回閫€浜?14 鏍?K线的距离，留下明显留白！**

## 解决方案

**1. 后端补充空数据节点占浣?(`run_cts1.py`)**
在主循环 `build_history_data` 里，不仅 RSI 初始化时瑕?`history_rsi.append({'t': ts_ms, 'v': None})` 填补缺失位，针对 MACD 因为异常而无法运算的区间（未到慢线周期等），显式地推送包含正纭?`ts_ms` 且全部参鏁板€间负 `None` 的骨架字典作为时间占坑点銆?

**2. 前端引入 Whitespace (空白占λ) 协议 (`dashboard.html`, `dashboard_5_1.html`)**
重构 `prepareBatchData` 和相关ָ标装杞介€昏緫锛?
针对鎵€有带有正确时间点灞炴€?`t` 但数值本身为 `undefined` / `null` 的数据点锛?*不能抛弃。转而向 Lightweight Charts 插入特殊鐨?`{ time: ts }` 没有 `value` 灞炴€х殑数据对象**銆?
这在 Lightweight Charts 内部被称涓?[Whitespace data items](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/WhitespaceData)，它们能够在时间轴上霸占涓€个真ʵ的业务坐标但本身不进行渲染动作，这就从根本上修复了逻辑索引的λ移误宸€?

**3. 实时增量更新鐨勯€傞厤补充 (`dashboard_5_1.html`)**
同步修改浜?`updateRSI()`, `updateMACD()` 鍜?`updateEquity()` 三个核心实时注入方法：如果计算接收到的是鏃犲€硷紙诸如策略被终止产鐢?`null` 或策略尚未启动），不跳过 `update()` 调用锛岃€屾槸继续灏?`{ time }` 对象喂入，确保数据管道里的时间流向始终完全平行吻合主K线！

## 交付与验璇?
代码均已修改并存鐩樸€傞噸新刷新或者重启服务端后，可以观察到无论策略当前指标是否满足运算周期，副图的时间标尺必定与主K线实现严格对齐，右侧留白消失，图形在 X 轴向上的渲染锚定真正做到浜?1:1銆?
