# -*- coding: utf-8 -*-
"""首次启动设备码：device_id 为空时随机生成并写回配置，之后固定复用

旧行为：回落 Build 指纹定值（所有电脑都是 9a35c7a900000662），没有区分度。
新行为：首次启动 random_device_id() 生成 → 立即写回 config.json → 之后固定。
"""
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from shandong_school_cracked.app import App


class 首次启动设备码(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="shandong-school_cracked-dev-"))
        self.cfg_path = self.tmp / "config.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _app(self, data_name="data"):
        return App(data_dir=self.tmp / data_name,
                   config_path=self.cfg_path, mode="mock")

    def test_首启随机生成并落盘(self):
        app = self._app()
        did = app.client.transport.device_id
        self.assertRegex(did, re.compile(r"^[0-9a-f]{16}$"), "16 位小写 hex")
        self.assertTrue(self.cfg_path.exists(), "首次启动必须把生成的 device_id 写回配置")
        saved = json.loads(self.cfg_path.read_text(encoding="utf-8"))
        self.assertEqual(saved.get("device_id"), did)

    def test_第二次启动复用同一设备码(self):
        a = self._app("data-a")
        b = self._app("data-b")          # 数据目录不同、配置同一个 → id 必须不变
        self.assertEqual(a.client.transport.device_id, b.client.transport.device_id)
        self.assertEqual(b.client.transport.device_id,
                         json.loads(self.cfg_path.read_text(encoding="utf-8"))["device_id"])

    def test_显式配置优先不被覆盖(self):
        self.cfg_path.write_text(json.dumps({"device_id": "abcdef0123456789"}),
                                 encoding="utf-8")
        app = self._app()
        self.assertEqual(app.client.transport.device_id, "abcdef0123456789")
        saved = json.loads(self.cfg_path.read_text(encoding="utf-8"))
        self.assertEqual(saved.get("device_id"), "abcdef0123456789")


if __name__ == "__main__":
    unittest.main()
