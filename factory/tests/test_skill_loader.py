"""
SkillLoader 鍗曞厓娴嬭瘯

杩愯: python -m pytest tests/test_skill_loader.py -v
"""

import json
import os
import sys
import tempfile
import textwrap
import unittest

# 纭繚椤圭洰鏍圭洰褰曞湪 sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from console.runner.skill_loader import SkillLoader, SkillLoadError
from cartridges.strategies.base_strategy import BaseStrategy


ZEN_SKILL_DIR = os.path.join(PROJECT_ROOT, "strategies", "skills", "zen-7-1")


class TestSkillLoaderWithZen71(unittest.TestCase):
    """鐢ㄧ湡瀹?zen-7-1 Skill 鍖呮祴璇?SkillLoader"""

    def setUp(self):
        self.loader = SkillLoader()
        # 鑻?zen-7-1 鐩綍涓嶅瓨鍦ㄥ垯璺宠繃鏁翠釜娴嬭瘯绫?
        if not os.path.isdir(ZEN_SKILL_DIR):
            self.skipTest("zen-7-1 Skill 鐩綍涓嶅瓨鍦紝璺宠繃娴嬭瘯")

    def test_load_returns_tuple(self):
        """load() 搴旇繑鍥?(strategy, meta, config) 涓夊厓缁?""
        result = self.loader.load(ZEN_SKILL_DIR)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)

    def test_strategy_is_base_strategy(self):
        """杩斿洖鐨?strategy 搴斾负 BaseStrategy 瀛愮被瀹炰緥"""
        strategy, _, _ = self.loader.load(ZEN_SKILL_DIR)
        self.assertIsInstance(strategy, BaseStrategy)

    def test_skill_meta_name(self):
        """skill_meta['name'] 搴斾笌鐩綍鍚嶄竴鑷?""
        _, meta, _ = self.loader.load(ZEN_SKILL_DIR)
        self.assertEqual(meta.get("name"), "zen-7-1")

    def test_skill_meta_has_version(self):
        """skill_meta 搴斿寘鍚?metadata.version"""
        _, meta, _ = self.loader.load(ZEN_SKILL_DIR)
        self.assertIn("metadata", meta)
        self.assertIn("version", meta["metadata"])

    def test_config_has_params(self):
        """config 搴斿寘鍚?params 瀛楁"""
        _, _, config = self.loader.load(ZEN_SKILL_DIR)
        self.assertIn("params", config)

    def test_strategy_params_match_config(self):
        """strategy.params 搴斾笌 config.json 涓殑 params 涓€鑷?""
        strategy, _, config = self.loader.load(ZEN_SKILL_DIR)
        config_params = config.get("params", {})
        for key, value in config_params.items():
            self.assertIn(key, strategy.params,
                         f"strategy.params 缂哄皯 config.json 涓殑鍙傛暟: {key}")
            self.assertEqual(strategy.params[key], value,
                            f"鍙傛暟 {key} 涓嶄竴鑷? strategy={strategy.params[key]}, config={value}")

    def test_strategy_name_matches_skill_name(self):
        """strategy.name 搴斾笌 skill name 涓€鑷?""
        strategy, meta, _ = self.loader.load(ZEN_SKILL_DIR)
        self.assertEqual(strategy.name, meta["name"])


class TestSkillLoaderErrors(unittest.TestCase):
    """娴嬭瘯 SkillLoader 閿欒澶勭悊"""

    def setUp(self):
        self.loader = SkillLoader()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_skill_dir(self, name: str, skill_md: str, config: dict, strategy_code: str) -> str:
        """鍦ㄤ复鏃剁洰褰曚笅鍒涘缓涓€涓?Skill 鍖?""
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
        """涓嶅瓨鍦ㄧ殑鐩綍搴旀姏鍑?SkillLoadError"""
        with self.assertRaises(SkillLoadError):
            self.loader.load("/nonexistent/path/skill")

    def test_missing_skill_md_raises(self):
        """缂哄皯 SKILL.md 搴旀姏鍑?SkillLoadError"""
        skill_dir = os.path.join(self.tmpdir, "bad-skill")
        os.makedirs(skill_dir)
        with self.assertRaises(SkillLoadError):
            self.loader.load(skill_dir)

    def test_name_mismatch_raises(self):
        """SKILL.md 涓?name 涓庣洰褰曞悕涓嶄竴鑷存椂搴旀姏鍑?SkillLoadError"""
        skill_md = textwrap.dedent("""\
            ---
            name: wrong-name
            description: test
            ---
            """)
        config = {"params": {}}
        strategy_code = textwrap.dedent("""\
            from cartridges.strategies.base_strategy import BaseStrategy
            from console.core import MarketData, StrategyContext
            class TestStrat(BaseStrategy):
                def on_data(self, data, context):
                    return []
            """)
        skill_dir = self._make_skill_dir("my-skill", skill_md, config, strategy_code)
        with self.assertRaises(SkillLoadError, msg="name 涓嶄竴鑷村簲鎶ラ敊"):
            self.loader.load(skill_dir)

    def test_valid_minimal_skill_loads(self):
        """鏈€灏忓悎娉?Skill 鍖呭簲鑳芥垚鍔熷姞杞?""
        name = "min-skill"
        skill_md = textwrap.dedent(f"""\
            ---
            name: {name}
            description: minimal test skill
            ---
            # 鏈€灏?Skill
            """)
        config = {"params": {"capital": 1000}}
        strategy_code = textwrap.dedent("""\
            import sys, os
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))
            from cartridges.strategies.base_strategy import BaseStrategy
            from console.core import MarketData, StrategyContext
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
        """config.local.json 搴旇鐩?config.json 涓殑瀵瑰簲瀛楁"""
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
            from cartridges.strategies.base_strategy import BaseStrategy
            from console.core import MarketData, StrategyContext
            class LocalStrategy(BaseStrategy):
                def on_data(self, data, context):
                    return []
            """)
        skill_dir = self._make_skill_dir(name, skill_md, config, strategy_code)

        # 鍐欏叆 config.local.json
        local_config = {"initial_balance": 5000, "params": {"capital": 5000}}
        with open(os.path.join(skill_dir, "config.local.json"), "w") as f:
            json.dump(local_config, f)

        _, _, cfg = self.loader.load(skill_dir)
        self.assertEqual(cfg["initial_balance"], 5000)
        self.assertEqual(cfg["params"]["capital"], 5000)


if __name__ == "__main__":
    unittest.main()
