# 任务验收：修澶?Dashboard 图表不渲染与服务端日־ȱʧ问棰?

## 问题发现
在上涓€轮修澶?Socket 流ʽ卡死问题后，用户反馈锛?
1. **“ǰ端刷数据了，不过没有在画绾库€?*：侧边栏的数字在跳动，但 K 线图、权益图和底部的网格线均停留不动銆?
2. **“进入房间不论点不点寮€ʼK线和其他图表都不鍔ㄢ€?*：图表表现得像冻结了涓€鏍枫€?
3. **“服务端不显示更新的数据鈥?*：终端黑窗口只显示预热完成，之后涓€片死寂，缺乏心跳反馈銆?

## 根本原因排查与修澶?
针对这两个表现，进行了深度排查并修复锛?

### 1. 修复 K 线ͼ表被“每次强制ȫ景缩鏀锯€濋攣死的问题 (dashboard.html)
ԭǰ端代码中有һ个严重的渲染死循鐜€昏緫锛?
```javascript
// 旧代鐮?
const isNewBar = (prevLastTime === null) || (lastCandle.time > prevLastTime);
if (isNewBar) {
    mainChart.timeScale().fitContent(); // 问题鎵€在！
}
```
由于每一分钟都有新的 K 线产生，鎴栬€呭疄时推送触发增量，`isNewBar` 可能会被Ƶ繁判定涓?`true`。每次触发时调用 `fitContent()`，这会强制将整个数百鏍?K 线的历史塞进屏Ļ可视区域！这就导致了只要 K线一来，任何用户试图放大鎴栬€呮煡看看鏈€新价格线条的动作都会被立即打断并“缩回全鏅€濓紝视觉上表现就鏄€滄鏈衡€濄€佲€滀笉画线”（线太细太密看不清锛夈€?
**鈻?修复**：去除了每次新增 K 线时鐨?`fitContent()` 和全鐩?`setData`，改为优雅的 `candleSeries.update(lastCandle)`。这不仅彻底解决了冻结问题，也极大降低了浏览器的 CPU 负担銆?

### 2. 修复网格线疯狂销毁重绘导致的性能雪崩 (dashboard.html)
之前的实现中，每次推送来带网格数据的包，图表都会执行锛?
```javascript
// 旧代鐮?
window.gridLines.forEach(line => mainChart.removeSeries(line));
// 然后重新 addLineSeries 涓€遍网鏍?
```
对于 LightweightCharts，这属于寮€锢㼫大的操作，会导致图表卡顿甚至直接不绘图銆?
**鈻?修复**：弃用了厚重鐨?`addLineSeries`，改用官方专用于横线鐨?`createPriceLine`。只闇€初始化һ次对象，后续每次数据更新仅使鐢?`window.gridLines[i].applyOptions({ price: price })` 无缝滑动更新横线λ置。轻盈丝婊戙€?

### 3. 服务端加上低频的心跳回显 (multi_strategy_runner.py)
因为上一版本为了终端整洁我去掉了单纯鐨?`print`，使得后端看起来像挂浜嗐€?
**鈻?修复**：在 `runner.py` 的数据处理主逻辑 `on_bar` 增加了一涓?30次一跳（大约每分钟一次）的心跳日志输出：
```text
[15:36:12] [Runner] 接收到最新行鎯?BTC-USDT = 64889.5
```
这样不仅能知道服务器还在运作，也能看到最新价銆?


### 4. 修复策略执行ʱ的 `Order.__init__` 缺失参数错误 (multi_strategy_runner.py)
用户反馈在启动策略后，后台打印错误：`[Slot:grid_v40] 执行信号失败: Order.__init__() missing 1 required positional argument: 'order_id'`銆?
**鈻?修复**：经排查，`Order` 数据类（鍦?`core/types.py` 中定义）要求第一个参数为 `order_id`锛岃€屾墽行引鎿?`live.py` 鍜?`backtest.py` 在创寤?`Order` 时都显式传入浜?`order_id=""` 让后续负责交鐢?`executor` 回填，但 `multi_strategy_runner.py` 遗漏了这个必填项。添加了 `order_id=""` 后，错误解除，测试也閮介€氳繃浜嗐€?

## 验收结果
问题已排除，用户重新运行 `run_cts1.py` 后，终端应该能每分钟跳出涓€次收盘价。ͬʱǰ端浏览器页面无论是重缃€佹殏停还是切换策略框，K线都能正常移动，网格线Ҳ可以秒级追踪变化浜嗐€備氦易执行也将不再因为参数缺澶辫€屾姤閿欍€?
