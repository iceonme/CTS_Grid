# 任务验收：修澶?Dashboard 实时数据流卡住问棰?

## 问题发现
在多策略并发运行ʱ，Dashboard 在预热完成后，不再接收新的实ʱK线数据，控制台卡鍦?`启动 OKX 数据娴? BTC-USDT 1m` 之后銆?

## 原因分析
这是因为 `flask-socketio` 默认会在妫€测到ϵͳ中安װ了 `eventlet` 时切换到 `eventlet` 运行模式。然而，由于代码尚未在顶部进琛?`eventlet.monkey_patch()`，主线程中的 `requests.get()`（`okx_feed.py` 里调鐢?OKX API）会使用原生 socket 阻塞整个 Eventlet 事件循环，导致死锁，浣?K 线轮询永远无法继缁€?

## 解决办法
鍦?`CTS1/dashboard/server.py` 中初始化 `SocketIO` 时，强制指定 `async_mode='threading'`，让它使鐢?Werkzeug 的多线程原生态模式，放弃 Eventlet。这彻底解决了因涓?Socket 阻塞引发的死锁问棰樸€?

```diff
-        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
+        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode='threading')
```

## 验证结果
1. 已加鍏?debug 日志排查，确认执行到 `get_candles` 时发生了无限阻塞銆?
2. 强制指定 `threading` 模式后，再次启动 `run_cts1.py` 服务，控制台顺利输出了每分钟的实时轮询更鏂般€?
3. 清理浜?debug 打印代码銆?
4. 现在 Dashboard 能够源源不断地收到新的ʵ时行情数鎹€?
