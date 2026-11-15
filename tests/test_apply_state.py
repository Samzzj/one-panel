"""下发状态的并发测试：sweep 定时器不能把面板刚提交的变更标成已应用。"""

from __future__ import annotations

import os
import shutil
import unittest

from app import App


class DirtyEpochTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # 和 test_api_e2e 一样用固定目录：受限环境下 mkdtemp 的目录可能不可访问
        cls.data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".test-epoch")
        shutil.rmtree(cls.data_dir, ignore_errors=True)
        os.makedirs(cls.data_dir, exist_ok=True)
        cls.app = App(cls.data_dir, auto_apply=False)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.data_dir, ignore_errors=True)

    def setUp(self) -> None:
        self.app.store.set_meta("dirty", "0")
        self.app.store.set_meta("dirty_epoch", "0")

    def stub(self, mid_change: bool):
        app = self.app

        class Deployer:
            def apply_all(self):
                if mid_change:
                    # 模拟「下发期间又有人改了配置」
                    app.mark_dirty()
                return {"ok": True, "warnings": []}

        return Deployer()

    def test_clean_apply_clears_dirty(self) -> None:
        self.app.deployer = self.stub(False)
        self.app.mark_dirty()
        self.assertEqual(self.app.store.meta("dirty", "0"), "1")
        self.app.apply_now()
        self.assertEqual(self.app.store.meta("dirty", "0"), "0")

    def test_change_during_apply_keeps_dirty(self) -> None:
        self.app.deployer = self.stub(True)
        self.app.mark_dirty()
        before = int(self.app.store.meta("dirty_epoch", "0"))
        self.app.apply_now()
        self.assertEqual(self.app.store.meta("dirty", "0"), "1")
        self.assertGreater(int(self.app.store.meta("dirty_epoch", "0")), before)

    def test_mark_dirty_bumps_epoch(self) -> None:
        self.app.mark_dirty()
        first = int(self.app.store.meta("dirty_epoch", "0"))
        self.app.mark_dirty()
        self.assertEqual(int(self.app.store.meta("dirty_epoch", "0")), first + 1)

    def test_failed_apply_keeps_dirty(self) -> None:
        self.app.deployer = type("D", (), {"apply_all": lambda _self: {"ok": False, "warnings": []}})()
        self.app.mark_dirty()
        self.app.apply_now()
        self.assertEqual(self.app.store.meta("dirty", "0"), "1")


if __name__ == "__main__":
    unittest.main()
