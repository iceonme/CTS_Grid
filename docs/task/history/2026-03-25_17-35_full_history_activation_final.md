# 任务归档：全量激活 Dashboard 三图历史 (2026-03-25 17:35)

## 技术实现
- **V93 协议**：增加 `history_rsi` 与 `history_equity` 字段。
- **时间戳**：全量对正为 Unix 秒数 (Integer)。
- **逻辑剥离**：`BaseStrategy` 不再包裹 `history_candles` 假盒。

## 交付确认
- 360 根 K 线全量显示：确认。
- RSI 历史曲线激活：确认。
- PNL 历史净值点亮：确认。
- 收益率基准校正 (5000)：确认。
