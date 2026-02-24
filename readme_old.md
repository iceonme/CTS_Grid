# BTC动态网格策略 - 本地模拟盘系统

## 📁 项目结构

```
grid_trading_system/
├── paper_trading.py          # 模拟盘引擎（核心）
├── grid_strategy.py          # 策略适配器（优化版V4）
├── okx_config.py             # OKX交易所配置
├── run_paper_trading.py      # 运行脚本
├── dashboard.py              # 实时监控面板
├── templates/
│   └── dashboard.html        # Web界面模板
├── data/
│   └── btc_1m.csv           # 历史数据文件
└── README.md                 # 本文件
```

## 🚀 快速开始

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

## 🔧 OKX配置详细步骤

### 步骤1: 注册OKX账号
1. 访问 https://www.okx.com

### 步骤2: 创建API Key（模拟盘）
1. 登录后点击右上角【个人中心】
2. 选择【API】->【创建API Key】
3. 选择【模拟交易】
4. 设置API Key名称、Passphrase并保存。

### 步骤3: 获取模拟资金
1. 进入OKX模拟交易页面获取虚拟USDT。

## 📊 核心功能

### 1. 自适应滑点模型
根据订单簿深度自动调整滑点。

### 2. 网络延迟模拟
模拟 200ms 的网络往返延迟。

### 3. 动态仓位调整（优化版V4）
- 自适应 RSI 指标。
- 凯利公式仓位管理。
- 移动止损机制。

## 🖥️ 启动监控面板

```bash
python dashboard.py
# 浏览器访问 http://localhost:5000
```

## ⚠️ 风险提示
1. **模拟盘≠实盘**。
2. **API安全**：请勿泄露 API Key。
3. **资金安全**：实盘请从小资金开始。




# 可用API  （模拟盘）
apikey = "72aac042-9859-48ec-8e27-9722524429a6"
secretkey = "CCFE2963EBD154027557D24CFA2CAA57"
IP = ""
备注名 = "Paper_trading_1"
权限 = "读取", "交易"