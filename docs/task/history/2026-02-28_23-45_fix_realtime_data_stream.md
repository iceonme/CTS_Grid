# 任务验收：修复 Dashboard 实时数据流卡住问题

## 问题发现
在多策略并发运行时，Dashboard 在预热完成后，不再接收新的实时K线数据，控制台卡在 `启动 OKX 数据流: BTC-USDT 1m` 之后。

## 原因分析
这是因为 `flask-socketio` 默认会在检测到系统中安装了 `eventlet` 时切换到 `eventlet` 运行模式。然而，由于代码尚未在顶部进行 `eventlet.monkey_patch()`，主线程中的 `requests.get()`（`okx_feed.py` 里调用 OKX API）会使用原生 socket 阻塞整个 Eventlet 事件循环，导致死锁，使 K 线轮询永远无法继续。

## 解决办法
在 `CTS1/dashboard/server.py` 中初始化 `SocketIO` 时，强制指定 `async_mode='threading'`，让它使用 Werkzeug 的多线程原生态模式，放弃 Eventlet。这彻底解决了因为 Socket 阻塞引发的死锁问题。

```diff
-        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
+        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode='threading')
```

## 验证结果
1. 已加入 debug 日志排查，确认执行到 `get_candles` 时发生了无限阻塞。
2. 强制指定 `threading` 模式后，再次启动 `run_cts1.py` 服务，控制台顺利输出了每分钟的实时轮询更新。
3. 清理了 debug 打印代码。
4. 现在 Dashboard 能够源源不断地收到新的实时行情数据。
