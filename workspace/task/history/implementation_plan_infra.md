# 彻底消除 Infra 目录与密钥 .env 隔离方案

按照 Skill 标准，彻底移除根目录 `infra/`。引入 `.env` 机制来实现 Skill 的密钥隔离，确保 `config.json` 只包含纯粹的策略参数。

## 用户审核要求

> [!IMPORTANT]
> - **密钥隔离**: API 密钥将存储在 Skill 目录下的 `.env` 文件中（该文件应被列入 `.gitignore`）。
> - **自动加载**: `SkillLoader` 将自动识别并加载 Skill 目录下的 `.env`，将其注入实例化参数。
> - **架构纯净化**: 根目录将不再有 `infra/`，所有业务逻辑均由 Skill 驱动。

## 拟议变更

### [Component] Console Core (SkillLoader)

#### [MODIFY] [skill_loader.py](file:///c:/CS/CTA2/console/runner/skill_loader.py)
在 `_load_config` 流程中增加对 `.env` 文件的扫描。如果存在，则解析为 Key-Value 对并合并到 `params` 中。这样做可以无缝支持 Skill 内部的密钥隔离。

### [Component] Bridge Layer Utilities

#### [NEW] [cartridges/bridge/utils/okx_api.py](file:///c:/CS/CTA2/cartridges/bridge/utils/okx_api.py)
迁移原 `infra/config/okx_config.py` 的 API 请求封装逻辑。

#### [MODIFY] [okx-feed/scripts/feed.py](file:///c:/CS/CTA2/cartridges/bridge/datafeeds/okx-feed/scripts/feed.py)
- 更新导入路径。
- 移除对全局 `infra.config` 的任何依赖。

### [Component] File System Cleanup

#### [DELETE] [infra/](file:///c:/CS/CTA2/infra)
删除根目录下的 `infra/` 目录。

#### [NEW] [factory/research/data_extraction/](file:///c:/CS/CTA2/factory/research/data_extraction)
承接原 `infra/scripts/` 内容。

#### [NEW] [cartridges/bridge/datafeeds/okx-feed/.env.example](file:///c:/CS/CTA2/cartridges/bridge/datafeeds/okx-feed/.env.example)
提供密钥配置模板，引导用户创建私有的 `.env` 文件。

## 验证计划

### 自动化测试
- 启动 `python launcher.py grid-v60`。
- 验证 `okx-feed` 是否成功加载了其目录下的 `.env` 密钥。

### 手动验证
- 确认 `infra/` 目录已消失。
- 确认 `config.json` 中仅保留策略/运行参数，不含密钥。
