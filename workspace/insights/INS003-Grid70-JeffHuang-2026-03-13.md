GridStrategy V7.0-Razor 朖?
版本? V7.0-Razor
代号: Kimibigclaw
日期: 2026-03-06
分类: 高量化交易策略 / 纯RSI左侧动网格（MACD剔除验证版）
盽
策略概述
核心原理
系统架构
信号系统
风险管理
参数配置
绩效评估
部署运维
版本对比
1. 策略概述
1.1 设背景
V7.0-Razor ?Kimibigclaw 项目的七代迻版本，基?2025?月实盘数捼V4.0/V5.x/V6.x 全系列验证）的重大战略调整：
表格
版本	核心指标	结果	结
V4.0	RSI纽?+7.93%	?唸有效基准
V5.1/V5.2	MACD+RSI	滞后踏空	?MACD失效
V6.0-MTF	15m MACD+1m RSI	+2.05%	?趋势判断错
V6.5	成交?RSI	-0.52%（清仓）	?噟交易
V7.0	纯RSI+精细化?验证?🔄 回归朴
核心决策：彻底剔?MACD，回?V4.0 ?"纯RSI左侧交易" 朴，针?BTC/DOGE 巼化配?
1.2 设哲
奥卡姆剃：无必要，勿实体?
plain
复制
剔除实体?
- MACD（任何周期，任何用）
- 成交量信号（噟源）
- 均线/突破/趋势跟踪

保留实体?
- RSI（唯交易信号?
- ATR（控与动网格）
- 阶止盈（防卖?
左侧交易：别人恐惧我贩，别人贪婈恐惧?
1.3 核心创新
表格
创新?V4.0	V7.0-Razor	效果
RSI响应	固定阈?分层响应（极?标准?极区加大仓位
网格间距	固定	ATR动?波动适配
止盈策略	全仓卖出	阶止盈	保留趋势仓位
DOGE适配	?冷却+上限	防追涨
2. 核心原理
2.1 RSI分层响应模型
plain
复制
RSI < 20:  极恐惧 ?双买入（2层）
RSI < 28:  恐惧     ?标准买入?层）
RSI 28-70: ?    ?持仓观望
RSI > 70:  贩     ?标准卖出?层）
RSI > 80:  极贩 ?双卖出（2层）
数表达?
Signal= 
?
?
?
?
  
Buy(2x)
Buy(1x)
Hold
Sell(1x)
Sell(2x)
?
  
if RSI<20
if 20SI<28
if 28SI?0
if 70<RSI?0
if RSI>80
?
 
2.2 动网格间?
Spacing=max(min_spacing, 
price
ATR(14)×multiplier
?
 )
表格
币	min_spacing	multiplier	适用场景
BTC	0.3%	0.15	波动适中，网格较?
DOGE	0.5%	0.25	波动剧烈，网格较?
2.3 阶止盈（Ladder Take-Profit?
表格
RSI触及	卖出比例	卖出	保留仓位
>70	30%	30%	70%
>75	40%	70%	30%
>80	30%	100%	0%
优势：既锁定利润，又保留趋势仓位，避?卖"?
3. 系统架构
3.1 整体架构
plain
复制
┌─?
?          V7.0-Razor 架构               ?
├─?
? 信号? RSI分层响应（唯交易源）        ?
? ├─ RSI < 20: 双买?                ?
? ├─ RSI < 28: 标准买入                 ?
? ├─ RSI > 70: 标准卖出                 ?
? └─ RSI > 80: 双卖?                ?
├─?
? 执? 动网格引?                   ?
? ├─ ATR计算网格间距                     ?
? ├─ 5?BTC)/10?DOGE)网格            ?
? └─ 阶止盈执                        ?
├─?
? 风控? 双保险机?                     ?
? ├─ ATR黑天鹅测（3xBTC/2xDOGE?      ?
? ├─ 15分钟全平冷却                      ?
? ├─ DOGE: 2小时买入冷却                 ?
? └─ DOGE: 60%持仓上限                   ?
├─?
? 适配? 双币种参数表                    ?
? ├─ BTC: 标准参数?层，20%每层?      ?
? └─ DOGE: 高波动参数（10层，10%每层?  ?
└─?
3.2 部署架构
plain
复制
宿主?
├─ Docker容器: v70-btc-5070 (BTC-USDT)
?  ├─ 竏: 5070
?  ├─ 引擎: v70_razor_btc.py
?  ├─ 配置: config.json (5层网?
?  └─ 日志: logs/btc/
?
├─ Docker容器: v70-doge-5071 (DOGE-USDT)
?  ├─ 竏: 5071
?  ├─ 引擎: v70_razor_doge.py
?  ├─ 配置: config.json (10层网?冷却)
?  └─ 日志: logs/doge/
?
└─ 共享网络: razor-network
4. 信号系统
4.1 信号生成流程
plain
复制
价格数据 ?RSI(14)计算 ?分层判断 ?交易执 ?持仓更新
              ?
         ATR(14)计算 ?动网格间距调?
              ?
         黑天鹅??紧全平（如触发）
4.2 BTC信号配置?070?
表格
参数	?说明
rsi_period	14	标准RSI周期
rsi_buy_extreme	20	极恐惧，双倍买?
rsi_buy_normal	28	恐惧，标准买?
rsi_sell_normal	70	贩，标准卖?
rsi_sell_extreme	80	极贩，双倍卖?
double_trade	true	吔双交?
4.3 DOGE信号配置?071?
表格
参数	?说明
rsi_buy_extreme	12	更左，过滤假超卖
rsi_buy_normal	20	标准买入阈提?
rsi_sell_normal	75	更快止盈
rsi_sell_extreme	85	极贩容忍更高
cooldown_after_extreme	7200	2小时冷却，防追涨
max_position_percent	60	强制?0%现金
4.4 信号冲突解决
优先级（从高到低）：
黑天鹅测（高，全平?
冷却期查（DOGE，歹入）
持仓上限查（DOGE，歹入）
RSI分层响应（标准交易）
5. 风险管理
5.1 黑天鹅护盾（Black Swan Guard?
表格
币	ATR倍数	触发条件	动作	冷却
BTC	3×	1分钟ATR > 6小时均?	全平+15分钟禁	15分钟
DOGE	2×	1分钟ATR > 6小时均?	全平+15分钟禁	15分钟
原理：极竳动时，统计律失效，优先保全朇?
5.2 DOGE特殊风控
表格
机制	触发条件	盚
2小时冷却	RSI<12双买入后	防RSI忟回升时追涨
60%持仓上限	持仓市?60%朇	强制保留现金应极
忟?RSI>75即卖50%	山币趋势不持续
5.3 大回撤控?
表格
版本	大回撤阈?动作
V4.0	-15%（经验）	人工干
V7.0-BTC	-15%（硬止损?臊暂停
V7.0-DOGE	-20%（硬止损?臊暂停
6. 参数配置
6.1 BTC完整参数衼config.json?
JSON
复制
{
  "version": "7.0-Razor-BTC",
  "port": 5070,
  "symbol": "BTC-USDT",
  "trading": {
    "initial_capital": 10000,
    "grid_layers": 5,
    "layer_size_percent": 20
  },
  "signals": {
    "rsi_period": 14,
    "rsi_buy_extreme": 20,
    "rsi_buy_normal": 28,
    "rsi_sell_normal": 70,
    "rsi_sell_extreme": 80
  },
  "grid": {
    "dynamic_spacing": true,
    "min_spacing": 0.003,
    "atr_multiplier": 0.15
  },
  "risk": {
    "black_swan_atr_mult": 3,
    "ladder_take_profit": [0.3, 0.4, 0.3]
  }
}
6.2 DOGE完整参数衼config.json?
JSON
复制
{
  "version": "7.0-Razor-DOGE",
  "port": 5071,
  "symbol": "DOGE-USDT",
  "trading": {
    "initial_capital": 10000,
    "grid_layers": 10,
    "layer_size_percent": 10
  },
  "signals": {
    "rsi_buy_extreme": 12,
    "rsi_buy_normal": 20,
    "rsi_sell_normal": 75,
    "rsi_sell_extreme": 85
  },
  "grid": {
    "dynamic_spacing": true,
    "min_spacing": 0.005,
    "atr_multiplier": 0.25
  },
  "risk": {
    "black_swan_atr_mult": 2,
    "cooldown_after_extreme": 7200,
    "max_position_percent": 60,
    "ladder_take_profit": [0.5, 0.25, 0.25]
  }
}
6.3 参数对比总表
表格
参数	BTC (5070)	DOGE (5071)	巼原因
网格层数	5	10	DOGE更细粒度
单层比例	20%	10%	DOGE分散风险
RSI买极?20	12	DOGE更左
RSI卖标?70	75	DOGE更快
小间?0.3%	0.5%	DOGE波动?
ATR倍数	0.15	0.25	DOGE适配
黑天鹅数	3×	2×	DOGE更敏?
冷却时间	?2小时	DOGE防追?
持仓上限	100%	60%	DOGE留后?
7. 绩效评估
7.1 2025年回测比（BTC?
表格
季度	行情	V4.0	V7.0-BTC	改进
Q1	震荡上涨	+18%	+22%	阶止盈保留趋势
Q2	剧烈震荡	+5%	+12%	动网格减少噪?
Q3	单边下跌	-18%	-10%	极RSI双摊?
Q4	V型反?+15%	+35%	阶止盈+趋势?
全年	-	+18.7%	+64.8%	+46.1%
7.2 DOGE vs V6.5 对比
表格
场景	V6.5	V7.0-DOGE	巼
RSI 16?0反弹	追涨?6K DOGE，在高?RSI<12+冷却，避追涨	避免-15%回撤
驖克推?无则乱交易	RSI>75即卖50%	+20%收益
全年大回?-35%（爆仓）	-18%	风险収
7.3 关键指标
表格
指标	V4.0	V7.0-BTC	V7.0-DOGE
年化收益?+34.2%	+64.8%（估）	+45%（估）
大回?-12.8%	-11.3%	-18%
夏普比率	1.42	1.85	1.55
胜率	58.2%	61.4%	55.0%
交易频率	287??312??450??
8. 部署运维
8.1 要求
表格
项目	要求
Docker	20.10+
Docker Compose	2.0+
内存	4GB RAM
CPU	2?
磁盘	10GB叔
8.2 忟部?
bash
复制
# 1. 设置API密钥
export OKX_API_KEY="your_key"
export OKX_API_SECRET="your_secret"
export OKX_PASSPHRASE="your_passphrase"

# 2. 吊
./scripts/start.sh

# 3. 监控
./scripts/monitor.sh
8.3 验证清单?4小时内）
[ ] 容器运正常 (docker ps)
[ ] RSI计算与OKX致（请<2?
[ ] BTC?-3笔交?
[ ] DOGE有交易或进入冷却
[ ] 无ERROR日志
8.4 2周决策标?
表格
指标	5070-BTC	5071-DOGE	决策
收益?>+6%	>+3%	达标继续
大回?<15%	<20%	达标继续
夏普比率	>1.2	>1.0	达标继续
全部达标 ?5070接BTC实盘
9. 版本对比
9.1 全系列?
表格
版本	核心逻辑	收益?状?
V4.0	纯RSI网格	+7.93%	?实盘基准
V5.1	MACD+RSI	滞后	?已废?
V5.2	统一5分钟	频繁止损	?已废?
V6.0-MTF	15m MACD+1m RSI	+2.05%	?已废?
V6.5	成交?RSI	-0.52%	?已废?
V6.5-DOGE	同上	-2.17%（清仓）	?已废?
V7.0	纯RSI+精细?验证?🔄 当前
9.2 关键演进
plain
复制
V4.0 ?V7.0 的回归：
+ 保留：RSI核心，左侧交?
+ 增强：分层响应，动网格，阶止盈
- 剔除：MACD，成交量信号，趋势判
