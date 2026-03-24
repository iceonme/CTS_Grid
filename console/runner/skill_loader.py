"""
SkillLoader - 交易 Skill 包通用加载器 (v2.0)
支持动态加载 Strategy, DataFeed, Executor 等不同类型的技能包。
遵循 Agent Skills & Trading Skill Specification 规范。
"""

import importlib.util
import inspect
import json
import os
import sys
from typing import Any, Tuple, Dict, Optional, Type

import yaml

# 基本类型定义（用于类型校验）
from cartridges.strategies.base import BaseStrategy

class SkillLoadError(Exception):
    """Skill 加载失败时抛出"""
    pass

class SkillLoader:
    """
    通用 Skill 包加载器。
    """

    def load(self, skill_dir: str) -> Tuple[Any, Dict, Dict]:
        """
        加载一个 Skill 包。
        返回: (instance, skill_meta, config)
        """
        skill_dir = os.path.abspath(skill_dir)
        if not os.path.isdir(skill_dir):
            raise SkillLoadError(f"Skill 目录不存在：{skill_dir}")

        # 1. 读取元数据
        meta = self._load_skill_md(skill_dir)
        skill_type = meta.get("metadata", {}).get("type", "strategy")
        
        # 2. 校验组件名称
        dir_name = os.path.basename(skill_dir)
        if meta.get("name") != dir_name:
            raise SkillLoadError(f"SKILL.md name '{meta.get('name')}' 与目录名 '{dir_name}' 不一致")

        # 3. 读取并合并配置
        config = self._load_config(skill_dir)
        params = config.get("params", {})

        # 4. 动态发现类
        # 定义类型与脚本名、基类名的映射
        type_map = {
            "strategy": ("strategy.py", "BaseStrategy"),
            "datafeed": ("feed.py", "BaseDataFeed"),
            "executor": ("executor.py", "BaseExecutor")
        }
        
        if skill_type not in type_map:
            raise SkillLoadError(f"不支持的 Skill 类型: {skill_type}")
            
        script_name, base_class_name = type_map[skill_type]
        skill_class = self._discover_skill_class(skill_dir, script_name, base_class_name)

        # 5. 实例化
        try:
            # 所有新一代 Skill (Microservice) 均接受 name 参数
            instance = skill_class(name=meta["name"], **params)
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise SkillLoadError(f"{skill_type} 实例化失败: {e}") from e

        print(f"[SkillLoader] 成功加载 {skill_type}: {meta['name']} (v{meta.get('metadata', {}).get('version', '1.0')})")
        return instance, meta, config

    def _load_skill_md(self, skill_dir: str) -> Dict:
        path = os.path.join(skill_dir, "SKILL.md")
        if not os.path.exists(path):
            raise SkillLoadError(f"缺失 SKILL.md: {path}")

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.startswith("---"):
            raise SkillLoadError("SKILL.md 格式错误：缺少 YAML Header")

        parts = content.split("---", maxsplit=2)
        try:
            return yaml.safe_load(parts[1]) or {}
        except Exception as e:
            raise SkillLoadError(f"SKILL.md YAML 解析失败: {e}")

    def _load_config(self, skill_dir: str) -> Dict:
        path = os.path.join(skill_dir, "config.json")
        if not os.path.exists(path):
            raise SkillLoadError(f"缺失 config.json: {path}")

        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)

        # 加载本地覆盖配置 (config.local.json)
        local_path = os.path.join(skill_dir, "config.local.json")
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                local_config = json.load(f)
            config = self._deep_merge(config, local_config)

        # 核心增强：加载 .env 密钥文件
        # 这允许将敏感信息从 config.json 中物理隔离
        env_path = os.path.join(skill_dir, ".env")
        if os.path.exists(env_path):
            env_vars = self._load_env_file(env_path)
            if "params" not in config:
                config["params"] = {}
            # 将环境变量注入到 params 中，供实例化使用
            config["params"].update(env_vars)
            
        return config

    def _load_env_file(self, path: str) -> Dict[str, str]:
        """解析简单的 .env 文件"""
        env_vars = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        # 去除引号并清理空白
                        env_vars[key.strip()] = val.strip().strip("'").strip('"')
        except Exception as e:
            print(f"[SkillLoader] 警告: 加载 .env 失败: {e}")
        return env_vars

    def _discover_skill_class(self, skill_dir: str, script_name: str, base_name: str) -> Type:
        script_path = os.path.join(skill_dir, "scripts", script_name)
        if not os.path.exists(script_path):
            raise SkillLoadError(f"找不到入口脚本: {script_path}")

        skill_unique_name = os.path.basename(skill_dir).replace('-', '_')
        module_name = f"_skill_mod_{skill_unique_name}_{script_name.replace('.py', '')}"

        # 确保项目根目录在 sys.path
        project_root = os.getcwd()
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        spec = importlib.util.spec_from_file_location(module_name, script_path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            raise SkillLoadError(f"脚本加载失败 [{script_name}]: {e}")

        # 查找匹配基类的类
        candidates = []
        for name, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ != module_name:
                continue
            
            # 检查继承关系 (通过类名字符串匹配，避免循环导入)
            for parent in cls.__mro__:
                if parent.__name__ == base_name:
                    candidates.append(cls)
                    break
        
        if not candidates:
            raise SkillLoadError(f"在 {script_name} 中未找到继承自 {base_name} 的类")
        if len(candidates) > 1:
            # 优先找名字包含 Skill 的或与目录名相关的
            for c in candidates:
                if "Skill" in c.__name__: return c
            raise SkillLoadError(f"在 {script_name} 中发现多个候选类: {[c.__name__ for c in candidates]}")
            
        return candidates[0]

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        res = base.copy()
        for k, v in override.items():
            if k in res and isinstance(res[k], dict) and isinstance(v, dict):
                res[k] = self._deep_merge(res[k], v)
            else:
                res[k] = v
        return res
