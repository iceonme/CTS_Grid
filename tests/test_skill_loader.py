"""
SkillLoader 单元测试

运行: python -m pytest tests/test_skill_loader.py -v
"""

import json
import os
import sys
import tempfile
import textwrap
import unittest

# 确保项目根目录在 sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from runner.skill_loader import SkillLoader, SkillLoadError
from strategies.base import BaseStrategy


ZEN_SKILL_DIR = os.path.join(PROJECT_ROOT, "strategies", "skills", "zen-7-1")


class TestSkillLoaderWithZen71(unittest.TestCase):
    """用真实 zen-7-1 Skill 包测试 SkillLoader"""

    def setUp(self):
        self.loader = SkillLoader()
        # 若 zen-7-1 目录不存在则跳过整个测试类
        if not os.path.isdir(ZEN_SKILL_DIR):
            self.skipTest("zen-7-1 Skill 目录不存在，跳过测试")

    def test_load_returns_tuple(self):
        """load() 应返回 (strategy, meta, config) 三元组"""
        result = self.loader.load(ZEN_SKILL_DIR)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)

    def test_strategy_is_base_strategy(self):
        """返回的 strategy 应为 BaseStrategy 子类实例"""
        strategy, _, _ = self.loader.load(ZEN_SKILL_DIR)
        self.assertIsInstance(strategy, BaseStrategy)

    def test_skill_meta_name(self):
        """skill_meta['name'] 应与目录名一致"""
        _, meta, _ = self.loader.load(ZEN_SKILL_DIR)
        self.assertEqual(meta.get("name"), "zen-7-1")

    def test_skill_meta_has_version(self):
        """skill_meta 应包含 metadata.version"""
        _, meta, _ = self.loader.load(ZEN_SKILL_DIR)
        self.assertIn("metadata", meta)
        self.assertIn("version", meta["metadata"])

    def test_config_has_params(self):
        """config 应包含 params 字段"""
        _, _, config = self.loader.load(ZEN_SKILL_DIR)
        self.assertIn("params", config)

    def test_strategy_params_match_config(self):
        """strategy.params 应与 config.json 中的 params 一致"""
        strategy, _, config = self.loader.load(ZEN_SKILL_DIR)
        config_params = config.get("params", {})
        for key, value in config_params.items():
            self.assertIn(key, strategy.params,
                         f"strategy.params 缺少 config.json 中的参数: {key}")
            self.assertEqual(strategy.params[key], value,
                            f"参数 {key} 不一致: strategy={strategy.params[key]}, config={value}")

    def test_strategy_name_matches_skill_name(self):
        """strategy.name 应与 skill name 一致"""
        strategy, meta, _ = self.loader.load(ZEN_SKILL_DIR)
        self.assertEqual(strategy.name, meta["name"])


class TestSkillLoaderErrors(unittest.TestCase):
    """测试 SkillLoader 错误处理"""

    def setUp(self):
        self.loader = SkillLoader()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_skill_dir(self, name: str, skill_md: str, config: dict, strategy_code: str) -> str:
        """在临时目录下创建一个 Skill 包"""
        skill_dir = os.path.join(self.tmpdir, name)
        os.makedirs(skill_dir)
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(skill_md)
        with open(os.path.join(skill_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump(config, f)
        with open(os.path.join(skill_dir, "strategy.py"), "w", encoding="utf-8") as f:
            f.write(strategy_code)
        return skill_dir

    def test_missing_skill_dir_raises(self):
        """不存在的目录应抛出 SkillLoadError"""
        with self.assertRaises(SkillLoadError):
            self.loader.load("/nonexistent/path/skill")

    def test_missing_skill_md_raises(self):
        """缺少 SKILL.md 应抛出 SkillLoadError"""
        skill_dir = os.path.join(self.tmpdir, "bad-skill")
        os.makedirs(skill_dir)
        with self.assertRaises(SkillLoadError):
            self.loader.load(skill_dir)

    def test_name_mismatch_raises(self):
        """SKILL.md 中 name 与目录名不一致时应抛出 SkillLoadError"""
        skill_md = textwrap.dedent("""\
            ---
            name: wrong-name
            description: test
            ---
            """)
        config = {"params": {}}
        strategy_code = textwrap.dedent("""\
            from strategies.base import BaseStrategy
            from core import MarketData, StrategyContext
            class TestStrat(BaseStrategy):
                def on_data(self, data, context):
                    return []
            """)
        skill_dir = self._make_skill_dir("my-skill", skill_md, config, strategy_code)
        with self.assertRaises(SkillLoadError, msg="name 不一致应报错"):
            self.loader.load(skill_dir)

    def test_valid_minimal_skill_loads(self):
        """最小合法 Skill 包应能成功加载"""
        name = "min-skill"
        skill_md = textwrap.dedent(f"""\
            ---
            name: {name}
            description: minimal test skill
            ---
            # 最小 Skill
            """)
        config = {"params": {"capital": 1000}}
        strategy_code = textwrap.dedent("""\
            import sys, os
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))
            from strategies.base import BaseStrategy
            from core import MarketData, StrategyContext
            class MinimalStrategy(BaseStrategy):
                def on_data(self, data, context):
                    return []
            """)
        skill_dir = self._make_skill_dir(name, skill_md, config, strategy_code)
        strategy, meta, cfg = self.loader.load(skill_dir)
        self.assertIsInstance(strategy, BaseStrategy)
        self.assertEqual(meta["name"], name)
        self.assertEqual(cfg["params"]["capital"], 1000)

    def test_local_config_overrides(self):
        """config.local.json 应覆盖 config.json 中的对应字段"""
        name = "local-skill"
        skill_md = textwrap.dedent(f"""\
            ---
            name: {name}
            description: test local override
            ---
            """)
        config = {"initial_balance": 10000, "params": {"capital": 10000}}
        strategy_code = textwrap.dedent("""\
            import sys, os
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))
            from strategies.base import BaseStrategy
            from core import MarketData, StrategyContext
            class LocalStrategy(BaseStrategy):
                def on_data(self, data, context):
                    return []
            """)
        skill_dir = self._make_skill_dir(name, skill_md, config, strategy_code)

        # 写入 config.local.json
        local_config = {"initial_balance": 5000, "params": {"capital": 5000}}
        with open(os.path.join(skill_dir, "config.local.json"), "w") as f:
            json.dump(local_config, f)

        _, _, cfg = self.loader.load(skill_dir)
        self.assertEqual(cfg["initial_balance"], 5000)
        self.assertEqual(cfg["params"]["capital"], 5000)


if __name__ == "__main__":
    unittest.main()
