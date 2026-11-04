#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""关闭软件时自动结束进行中跑步（finalize_pending_run）测试

场景：摇杆实走到一半直接关窗口 → 自动 stop + 上传 + 结算，
不再产生"数据在库里既没上传也没结算"的废记录。
"""
from __future__ import annotations

import random
import tempfile
import time
import unittest
from pathlib import Path

from shandong_school_cracked.app import App


class 自动收尾测试(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="test-finalize-"))
        cls.app = App(data_dir=cls.tmp, config_path=cls.tmp / "config.json", mode="mock")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.stop_mock()
        except Exception:  # noqa: BLE001
            pass

    def setUp(self):
        # finalize 有防重入标志；类共享 app，每个用例前复位
        self.app._finalized = False
        if not self.app.client.logged_in:
            r = self.app.login("13800138000", "test-pass", False)
            assert r.get("code") == 0, f"mock 登录失败：{r}"

    def _start_walk(self, target_m: float = 0.0):
        r = self.app.walk_start("real", target_m=target_m, fence_index=0,
                                speed_mps=2.5, auto_route=False, auto_start=True)
        self.assertEqual(r.get("code"), 0, f"walk_start 失败：{r}")
        # 推杆走一小段
        self.app.walk_joystick(0.6, 0.4, 0.9)
        time.sleep(4.0)          # 让 tick 产生采样点

    def test_实走进行中关闭_自动停止并结算(self):
        self._start_walk()
        rc = self.app.walk.run_code
        self.assertTrue(rc, "应有 runRecordCode")
        self.assertTrue(self.app.walk.running())

        out = self.app.finalize_pending_run("测试关闭")

        # walk 已停止并结算
        self.assertFalse(self.app.walk.running())
        self.assertIn("walk", out)
        self.assertEqual(out["walk"].get("run_code"), rc)
        self.assertEqual(out["walk"].get("code"), 0,
                         f"结算失败：{out}")
        # 结算事件已发出（mock finishSunRun_v2 路由返回成功）
        run = self.app.store.get_run(rc) or {}
        self.assertIsNotNone(run.get("end_ms"), "runs 表应有结束时间")

    def test_无进行中时无副作用(self):
        r = self.app.finalize_pending_run("测试")
        self.assertEqual(r, {})

    def test_防重入(self):
        r1 = self.app.finalize_pending_run("测试")
        r2 = self.app.finalize_pending_run("测试")
        self.assertEqual(r2, {})     # 第二次直接空返回

    def test_开关关闭时跳过(self):
        self.app.cfg["auto_finish_on_exit"] = False
        try:
            self._start_walk()
            rc = self.app.walk.run_code
            out = self.app.finalize_pending_run("测试")
            self.assertEqual(out.get("skipped"), "auto_finish_on_exit=false")
            # walk 没被停（用户显式关闭了自动收尾）
            self.assertTrue(self.app.walk.running())
            self.app.walk.stop(emit=False)
        finally:
            self.app.cfg["auto_finish_on_exit"] = True

    def test_结算后跑后行为链被mock跳过(self):
        """mock 模式下 post_run_browse 应跳过（无这些路由）"""
        from shandong_school_cracked import behavior
        steps = behavior.post_run_browse(self.app, "RC-MOCK", 1, random.Random(1))
        self.assertEqual(steps[0][0], "mock 模式跳过（本地仿真无风控语义）")


if __name__ == "__main__":
    unittest.main()
