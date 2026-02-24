
• 现在这版策略机制可以简化成 5 步：

  1. 读入行情并更新指标

  - 用最近 K 线计算 RSI、ADX、均线，判断市场状态（上涨趋势/下跌趋势/震荡）。

  2. 动态生成网格区间

  - 用近期高低点 + grid_buffer_pct 生成上下边界。
  - 用 rsi_weight 按 RSI 信号把整个网格上移/下移。

  3. 触发交易信号

  - 买入: 上一根低点在网格线上方，本根低点下穿网格线。
  - 卖出: 上一根高点在网格线下方，本根高点上穿网格线，且当前仓位有利润（约 >0.5%）。
  - 极端 RSI 会过滤：rsi_extreme_buy 以上不买，rsi_extreme_sell 以下不卖。
  - 现在是 MARKET 下单（提高成交响应）。

  4. 仓位与风控

  - 每次下单资金由 base_position_pct + Kelly/RSI/趋势因子共同决定。
  - 有 max_positions 层数限制（已改成真实层数估算）。
  - 止损用 trailing_stop_pct（或 stop_loss_pct 固定止损）。

  5. 周期重置

  - 到 cycle_reset_period 或触发 max_drawdown_reset 时，策略会发出平仓并重置网格。

  ———

  你最常调的参数（按影响排序）

  - 交易频率/敏感度

  1. grid_levels：网格条数，越大越容易触发。
  2. grid_refresh_period：网格更新周期，越小越灵敏。
  3. grid_buffer_pct：网格缓冲，越小越容易触发。

  - RSI 过滤强度

  1. rsi_oversold / rsi_overbought：基础阈值。
  2. rsi_extreme_buy / rsi_extreme_sell：极端过滤阈值。
  3. adaptive_rsi：是否随波动自动调阈值。
  4. rsi_weight：RSI 对网格偏移影响大小。

  - 仓位大小与风险

  1. base_position_pct：基础每次下单比例。
  2. max_positions：最大持仓层数。
  3. use_kelly_sizing / kelly_fraction：是否用凯利和强度。
  4. min_order_usdt：最小下单金额。

  - 止损与保护

  1. trailing_stop / trailing_stop_pct：移动止损。
  2. stop_loss_pct：固定止损。
  3. max_drawdown_reset：回撤触发重置阈值。
  4. cycle_reset_period：周期性强制重置。

  ———

  如果你要“稍微更活跃但不激进”，我建议先试这组：

  1. grid_levels: 10 -> 14
  2. grid_refresh_period: 100 -> 60
  3. grid_buffer_pct: 0.10 -> 0.08
  4. base_position_pct: 0.10 -> 0.12
  5. max_positions: 5 -> 6