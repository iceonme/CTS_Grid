"""
SkillLoader — 策略 Skill 包动态加载器

从符合 trading_skill_spec.md 标准的 Skill 目录中，
自动发现并实例化 BaseStrategy 子类，无需修改主程序代码。
"""

import importlib.util
import inspect
import json
import os
import sys
from typing import Optional

import yaml

from strategies.base import BaseStrategy


class SkillLoadError(Exception):
    """Skill 加载失败时抛出"""
    pass


class SkillLoader:
    """
    策略 Skill 包动态加载器。

    用法：
        loader = SkillLoader()
        strategy, meta, config = loader.load("strategies/skills/zen-7-1")
    """

    def load(self, skill_dir: str) -> tuple[BaseStrategy, dict, dict]:
        """
        加载一个 Skill 包。

        Args:
            skill_dir: Skill 包目录路径（绝对路径或相对于项目根目录的相对路径）

        Returns:
            (strategy_instance, skill_meta, config)
            - strategy_instance: 已实例化的 BaseStrategy 子类
            - skill_meta: SKILL.md frontmatter 解析后的 dict
            - config: config.json（已合并 config.local.json）的完整内容

        Raises:
            SkillLoadError: 目录格式不符合规范时
        """
        skill_dir = os.path.abspath(skill_dir)

        if not os.path.isdir(skill_dir):
            raise SkillLoadError(f"Skill 目录不存在：{skill_dir}")

        # Step 1: 读取 SKILL.md frontmatter
        skill_meta = self._load_skill_md(skill_dir)

        # Step 2: 校验目录名与 name 字段一致
        dir_name = os.path.basename(skill_dir)
        if skill_meta.get("name") != dir_name:
            raise SkillLoadError(
                f"SKILL.md 中的 name '{skill_meta.get('name')}' "
                f"与目录名 '{dir_name}' 不一致"
            )

        # Step 3: 读取 config.json（+ 合并 config.local.json）
        config = self._load_config(skill_dir)

        # Step 4: 动态导入 strategy.py，发现 BaseStrategy 子类
        strategy_class = self._discover_strategy_class(skill_dir)

        # Step 5: 实例化策略
        params = config.get("params", {})
        strategy_name = skill_meta.get("name", dir_name)
        try:
            strategy = strategy_class(name=strategy_name, **params)
        except Exception as e:
            raise SkillLoadError(f"策略实例化失败：{e}") from e

        print(f"[SkillLoader] 已加载 Skill: {strategy_name} "
              f"(v{skill_meta.get('metadata', {}).get('version', '?')}) "
              f"→ {strategy_class.__name__}")

        return strategy, skill_meta, config

    # ──────────────────────────────────────────────
    # 内部方法
    # ──────────────────────────────────────────────

    def _load_skill_md(self, skill_dir: str) -> dict:
        """读取并解析 SKILL.md frontmatter"""
        skill_md_path = os.path.join(skill_dir, "SKILL.md")
        if not os.path.exists(skill_md_path):
            raise SkillLoadError(f"缺少 SKILL.md：{skill_md_path}")

        with open(skill_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 提取 YAML frontmatter（--- ... --- 之间的内容）
        if not content.startswith("---"):
            raise SkillLoadError("SKILL.md 缺少 YAML frontmatter（应以 '---' 开头）")

        parts = content.split("---", maxsplit=2)
        if len(parts) < 3:
            raise SkillLoadError("SKILL.md frontmatter 格式错误（找不到结束的 '---'）")

        try:
            meta = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError as e:
            raise SkillLoadError(f"SKILL.md frontmatter YAML 解析失败：{e}") from e

        if "name" not in meta:
            raise SkillLoadError("SKILL.md frontmatter 缺少必填字段 'name'")
        if "description" not in meta:
            raise SkillLoadError("SKILL.md frontmatter 缺少必填字段 'description'")

        return meta

    def _load_config(self, skill_dir: str) -> dict:
        """读取 config.json，并用 config.local.json 覆盖"""
        config_path = os.path.join(skill_dir, "config.json")
        if not os.path.exists(config_path):
            raise SkillLoadError(f"缺少 config.json：{config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        # 合并 config.local.json（机器私有配置，不入 git）
        local_config_path = os.path.join(skill_dir, "config.local.json")
        if os.path.exists(local_config_path):
            with open(local_config_path, "r", encoding="utf-8") as f:
                local_config = json.load(f)
            config = self._deep_merge(config, local_config)
            print(f"[SkillLoader] 已合并本地配置: config.local.json")

        return config

    def _discover_strategy_class(self, skill_dir: str) -> type:
        """动态导入 scripts/strategy.py，自动发现 BaseStrategy 子类"""
        strategy_path = os.path.join(skill_dir, "scripts", "strategy.py")
        if not os.path.exists(strategy_path):
            raise SkillLoadError(f"缺少 scripts/strategy.py：{strategy_path}")

        # 生成唯一模块名，避免多个 Skill 的 strategy.py 命名冲突
        skill_name = os.path.basename(skill_dir)
        module_name = f"_skill_{skill_name.replace('-', '_')}_strategy"

        # 将 Skill 的父目录（skills/）临时加入 sys.path，供 strategy.py 内部 import 使用
        skills_root = os.path.dirname(skill_dir)
        project_root = os.path.dirname(os.path.dirname(skills_root))  # CTS1/
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        spec = importlib.util.spec_from_file_location(module_name, strategy_path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            raise SkillLoadError(f"strategy.py 导入失败：{e}") from e

        # 发现 BaseStrategy 子类（排除 BaseStrategy 自身）
        strategy_classes = [
            cls for _, cls in inspect.getmembers(module, inspect.isclass)
            if issubclass(cls, BaseStrategy) and cls is not BaseStrategy
            and cls.__module__ == module_name
        ]

        if len(strategy_classes) == 0:
            raise SkillLoadError(
                f"strategy.py 中未找到 BaseStrategy 子类"
            )
        if len(strategy_classes) > 1:
            names = [c.__name__ for c in strategy_classes]
            raise SkillLoadError(
                f"strategy.py 中发现多个 BaseStrategy 子类：{names}，每个 Skill 只允许一个"
            )

        return strategy_classes[0]

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """递归合并两个 dict，override 中的值优先"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
