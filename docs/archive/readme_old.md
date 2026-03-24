# BTC鍔ㄦ€佺綉格策鐣?- 本地模拟盘系缁?

## 📁 项目结构

```
grid_trading_system/
├─鈹€ paper_trading.py          # 模拟盘引擎（核心锛?
├─鈹€ grid_strategy.py          # 策略适配器（优化版V4锛?
├─鈹€ okx_config.py             # OKX交易鎵€配置
├─鈹€ run_paper_trading.py      # 运行脚本
├─鈹€ dashboard.py              # 实时监控面板
├─鈹€ templates/
鈹?  └─鈹€ dashboard.html        # Web界面模板
├─鈹€ data/
鈹?  └─鈹€ btc_1m.csv           # 历史数据文件
└─鈹€ README.md                 # 本文浠?
```

## 🚀 蹇€熷紑濮?

### 1. 安装依赖

```bash
pip install pandas numpy ccxt flask flask-socketio plotly requests
```

### 2. 准备数据

CSV格式要求（保存为 `btc_1m.csv`）：
```csv
timestamp,open,high,low,close,volume
2024-01-01 00:00:00,42500,42600,42400,42550,100.5
2024-01-01 00:01:00,42550,42650,42500,42620,95.3
```

### 3. 运行回测

```bash
python run_paper_trading.py
# 选择模式: 1 (回测模式)
```

## 🔧 OKX配置详ϸ步骤

### 步骤1: 注册OKX账号
1. 访问 https://www.okx.com

### 步骤2: 创建API Key（模拟盘锛?
1. 登录后点击右上角【个人中蹇冦€?
2. 选择【API銆?>【创建API Key銆?
3. 选择【模拟交鏄撱€?
4. 设置API Key名称、Passphrase并保瀛樸€?

### 步骤3: 获取模拟资金
1. 进入OKX模拟交易页面获取虚拟USDT銆?

## 📊 核心功能

### 1. 鑷€傚簲滑点模型
根据订单簿深度自动调整滑鐐广€?

### 2. 网络延迟模拟
模拟 200ms 的网络往返延杩熴€?

### 3. 鍔ㄦ€佷粨位调整（优化版V4锛?
- 鑷€傚簲 RSI 指标銆?
- 凯利公式仓位管理銆?
- 移动止损机制銆?

## 🖥锔?启动监控面板

```bash
python dashboard.py
# 浏览器访闂?http://localhost:5000
```

## ⚠️ 风险提示
1. **模拟盘≠实盘**銆?
2. **API安ȫ**：请勿泄闇?API Key銆?
3. **资金安全**：ʵ盘请从小资金寮€濮嬨€?




# 可用API  （模拟盘锛?
apikey = "72aac042-9859-48ec-8e27-9722524429a6"
secretkey = "CCFE2963EBD154027557D24CFA2CAA57"
IP = ""
备注鍚?= "Paper_trading_1"
权限 = "读取", "交易"
