# Trading Skill Specification v2.0

## 1. 概述
Trading Skill 是 CTA2 项目中用于执行交易任务的标准模块。它必须遵循统一的目录结构和元数据规范，以便 `SkillLoader` 能够自动识别、加载并实例化。

## 2. 目录结构规范
每个 Trading Skill 必须是一个独立的目录，结构如下：
```text
skill-name/
├── SKILL.md           # 核心元数据定义 (必须)
├── config.json        # 默认参数配置 (必须)
├── config.local.json  # 本地覆盖配置 (可选，不进入版本控制)
└── scripts/           # 入口代码目录
    └── [type].py      # 入口脚本 (如 strategy.py/feed.py/executor.py)
```

## 3. 元数据规范 (SKILL.md)
必须包含标准的 YAML Frontmatter：
```yaml
---
name: skill-base-name  # 必须与目录名一致
description: 简短描述
metadata:
  type: strategy|datafeed|executor  # 组件类型
  version: 1.0.0
  author: AI-Agent
---
# 详细说明文档
...
```

## 4. 类型接口规范

### 4.1 Strategy (类型: strategy)
- **脚本路径**: `scripts/strategy.py`
- **基类**: `BaseStrategy`
- **核心方法**: `__init__(self, name, **params)`, `on_data(self, data, context)`

### 4.2 DataFeed (类型: datafeed)
- **脚本路径**: `scripts/feed.py`
- **基类**: `BaseDataFeed`
- **核心方法**: `fetch_latest(self)`

### 4.3 Executor (类型: executor)
- **脚本路径**: `scripts/executor.py`
- **基类**: `BaseExecutor`
- **核心方法**: `execute(self, signal)`

---
> 更新日期: 2026-03-15
