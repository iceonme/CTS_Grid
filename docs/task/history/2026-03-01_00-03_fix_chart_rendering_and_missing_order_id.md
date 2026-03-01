# 任务验收：修复 Dashboard 图表不渲染与服务端日志缺失问题

## 问题发现
在上一轮修复 Socket 流式卡死问题后，用户反馈：
1. **“前端刷数据了，不过没有在画线”**：侧边栏的数字在跳动，但 K 线图、权益图和底部的网格线均停留不动。
2. **“进入房间不论点不点开始K线和其他图表都不动”**：图表表现得像冻结了一样。
3. **“服务端不显示更新的数据”**：终端黑窗口只显示预热完成，之后一片死寂，缺乏心跳反馈。

## 根本原因排查与修复
针对这两个表现，进行了深度排查并修复：

### 1. 修复 K 线图表被“每次强制全景缩放”锁死的问题 (dashboard.html)
原前端代码中有一个严重的渲染死循环逻辑：
```javascript
// 旧代码
const isNewBar = (prevLastTime === null) || (lastCandle.time > prevLastTime);
if (isNewBar) {
    mainChart.timeScale().fitContent(); // 问题所在！
}
```
由于每一分钟都有新的 K 线产生，或者实时推送触发增量，`isNewBar` 可能会被频繁判定为 `true`。每次触发时调用 `fitContent()`，这会强制将整个数百根 K 线的历史塞进屏幕可视区域！这就导致了只要 K线一来，任何用户试图放大或者查看看最新价格线条的动作都会被立即打断并“缩回全景”，视觉上表现就是“死机”、“不画线”（线太细太密看不清）。
**▶ 修复**：去除了每次新增 K 线时的 `fitContent()` 和全盘 `setData`，改为优雅的 `candleSeries.update(lastCandle)`。这不仅彻底解决了冻结问题，也极大降低了浏览器的 CPU 负担。

### 2. 修复网格线疯狂销毁重绘导致的性能雪崩 (dashboard.html)
之前的实现中，每次推送来带网格数据的包，图表都会执行：
```javascript
// 旧代码
window.gridLines.forEach(line => mainChart.removeSeries(line));
// 然后重新 addLineSeries 一遍网格
```
对于 LightweightCharts，这属于开销极大的操作，会导致图表卡顿甚至直接不绘图。
**▶ 修复**：弃用了厚重的 `addLineSeries`，改用官方专用于横线的 `createPriceLine`。只需初始化一次对象，后续每次数据更新仅使用 `window.gridLines[i].applyOptions({ price: price })` 无缝滑动更新横线位置。轻盈丝滑。

### 3. 服务端加上低频的心跳回显 (multi_strategy_runner.py)
因为上一版本为了终端整洁我去掉了单纯的 `print`，使得后端看起来像挂了。
**▶ 修复**：在 `runner.py` 的数据处理主逻辑 `on_bar` 增加了一个 30次一跳（大约每分钟一次）的心跳日志输出：
```text
[15:36:12] [Runner] 接收到最新行情 BTC-USDT = 64889.5
```
这样不仅能知道服务器还在运作，也能看到最新价。


### 4. 修复策略执行时的 `Order.__init__` 缺失参数错误 (multi_strategy_runner.py)
用户反馈在启动策略后，后台打印错误：`[Slot:grid_v40] 执行信号失败: Order.__init__() missing 1 required positional argument: 'order_id'`。
**▶ 修复**：经排查，`Order` 数据类（在 `core/types.py` 中定义）要求第一个参数为 `order_id`，而执行引擎 `live.py` 和 `backtest.py` 在创建 `Order` 时都显式传入了 `order_id=""` 让后续负责交由 `executor` 回填，但 `multi_strategy_runner.py` 遗漏了这个必填项。添加了 `order_id=""` 后，错误解除，测试也都通过了。

## 验收结果
问题已排除，用户重新运行 `run_cts1.py` 后，终端应该能每分钟跳出一次收盘价。同时前端浏览器页面无论是重置、暂停还是切换策略框，K线都能正常移动，网格线也可以秒级追踪变化了。交易执行也将不再因为参数缺失而报错。
