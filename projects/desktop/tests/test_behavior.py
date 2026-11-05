#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""行为链（behavior.py）测试：登录后浏览链 + 跑后行为

用 FakeClient 记录调用序列（不发网络），验证：
  · mock/未登录/配置关闭 → 跳过
  · 6h 冷却期内跳过、跨账号不跳
  · 正常链的步骤顺序与真实时序（sleep 已注入 rng 但仍是真 sleep，测试用极小间隔）
  · 任一步失败 → 链继续、绝不外抛（主流程安全）
"""
from __future__ import annotations

import random
import time
import unittest
from typing import Any, Dict, List

from shandong_school_cracked import behavior


class FakeClient:
    """记录方法调用顺序；可指定哪些方法抛异常"""

    def __init__(self, fail: tuple = ()):
        self.calls: List[str] = []
        self.fail = set(fail)
        self.logged_in = True
        self.user_id = "U1"
        self.school_code = "SCH1"
        self._mock_host = None
        self.user = {"userName": "测试"}

    def _rec(self, name, fn):
        self.calls.append(name)
        if name in self.fail:
            raise RuntimeError(f"{name} 网络失败")
        return fn()

    # 行为链用到的方法
    def message_red_dot(self):
        return self._rec("red_dot", lambda: {"code": 0})

    def works_recommend(self, page_num=1, page_size=10, keyword="", refresh_time="",
                        works_type=None):
        return self._rec("recommend", lambda: {
            "code": 0,
            "data": {"list": [{"worksNo": f"W{i}"} for i in range(3)]},
        })

    def works_detail(self, works_no: str):
        return self._rec(f"detail:{works_no}", lambda: {"code": 0})

    def works_visit(self, works_no: str, visit: int = 1):
        return self._rec(f"visit:{works_no}", lambda: {"code": 0})

    def rank_distance(self, *a, **k):
        return self._rec("rank", lambda: {"code": 0})

    def personal_info(self, extra=None):
        return self._rec("personal", lambda: {"code": 0})

    def my_school_info(self, school_code: str = ""):
        return self._rec("school", lambda: {"code": 0})

    def run_detail(self, run_code: str, sport_type: int = 1):
        return self._rec(f"run_detail:{run_code}", lambda: {"code": 0})

    # —— 鸿蒙真机行为链方法 ——
    def works_config(self):
        return self._rec("works_config", lambda: {"code": 0})

    def jackpot_home(self):
        return self._rec("jackpot_home", lambda: {"code": 0})

    def tasks_login_once(self):
        return self._rec("tasks_login_once", lambda: {"code": 0})

    def common_config_v2(self):
        return self._rec("common_config_v2", lambda: {"code": 0})

    def search_suggest(self):
        return self._rec("search_suggest", lambda: {"code": 0})

    def school_letter_red(self):
        return self._rec("school_letter_red", lambda: {"code": 0})

    def school_letter_list(self):
        return self._rec("school_letter_list", lambda: {"code": 0})

    def user_resource(self):
        return self._rec("user_resource", lambda: {"code": 0})

    def task_description(self):
        return self._rec("task_description", lambda: {"code": 0})

    def load_user(self):
        return self._rec("load_user", lambda: {"code": 0, "data": {}})


class FakeStore:
    def __init__(self):
        self.kv: Dict[str, Any] = {}

    def kv_get(self, k, d=None):
        return self.kv.get(k, d)

    def kv_set(self, k, v):
        self.kv[k] = v


class FakeApp:
    def __init__(self, client, cfg: Dict[str, Any]):
        self.client = client
        self.cfg = cfg
        self.store = client.store = FakeStore()
        self._mock = None


def fast_rng() -> random.Random:
    """把真实 sleep 压到接近 0：区间退化 (0, 0.001)"""
    return random.Random(1)


# 把 behavior 的 _gap 打成瞬时（测试不真等 8 秒）
_orig_gap = behavior._gap
behavior._gap = lambda rng, lo, hi: time.sleep(0.001)


class 跳过场景(unittest.TestCase):
    def test_mock跳过(self):
        app = FakeApp(FakeClient(), {})
        app._mock = "http://127.0.0.1:1234"
        steps = behavior.post_login_browse(app, fast_rng())
        self.assertEqual(steps[0][0], "mock 模式跳过（本地仿真无风控语义）")
        self.assertEqual(len(app.client.calls), 0)

    def test_未登录跳过(self):
        c = FakeClient()
        c.logged_in = False
        steps = behavior.post_login_browse(FakeApp(c, {}), fast_rng())
        self.assertEqual(steps[0][0], "未登录")
        self.assertEqual(len(c.calls), 0)

    def test_配置关闭跳过(self):
        c = FakeClient()
        steps = behavior.post_login_browse(FakeApp(c, {"behavior": False}), fast_rng())
        self.assertEqual(steps[0][0], "behavior 配置关闭")
        self.assertEqual(len(c.calls), 0)

    def test_冷却期内跳过_同账号(self):
        c = FakeClient()
        app = FakeApp(c, {})
        behavior.post_login_browse(app, fast_rng())          # 第一次：完整跑
        n1 = len(c.calls)
        self.assertGreater(n1, 0)
        steps = behavior.post_login_browse(app, fast_rng())  # 第二次：冷却
        self.assertEqual(steps[0][0], "冷却期内跳过")
        self.assertEqual(len(c.calls), n1)                   # 没有新请求

    def test_跨账号不冷却(self):
        c = FakeClient()
        app = FakeApp(c, {})
        behavior.post_login_browse(app, fast_rng())
        c.user_id = "U2"
        steps = behavior.post_login_browse(app, fast_rng())
        self.assertNotEqual(steps[0][0], "冷却期内跳过")


class 正常链(unittest.TestCase):
    def test_步骤顺序符合真机路径(self):
        """2026-11-05 鸿蒙真机抓包实序"""
        c = FakeClient()
        app = FakeApp(c, {})
        steps = behavior.post_login_browse(app, fast_rng())
        names = [s for s, _ in steps]
        # 真机顺序：社区配置 → 抽奖 → 用户资料 → 公共配置v2 → 登录任务
        #   → 推荐流 → (详情→上报)×N → 搜索热词 → 排行 → 校园信红点 →
        #   重要信件 → 用户资源 → 任务描述
        self.assertEqual(names[0], "社区配置")
        self.assertEqual(names[1], "抽奖首页")
        self.assertEqual(names[2], "用户资料")
        self.assertEqual(names[3], "公共配置v2")
        self.assertEqual(names[4], "登录任务")
        self.assertEqual(names[5], "社区推荐流")
        self.assertIn("帖子详情", names)
        self.assertIn("上报浏览", names)
        self.assertIn("搜索热词", names)
        self.assertIn("校园信红点", names)
        self.assertIn("重要信件", names)
        self.assertIn("用户资源", names)
        self.assertEqual(names[-1], "任务描述")
        self.assertTrue(all(g for _, g in steps), f"有失败步骤：{steps}")

    def test_点开帖子数在1到2之间(self):
        c = FakeClient()
        app = FakeApp(c, {})
        behavior.post_login_browse(app, random.Random(7))
        details = [x for x in c.calls if x.startswith("detail:")]
        self.assertTrue(1 <= len(details) <= 2)

    def test_任一步失败链继续(self):
        c = FakeClient(fail=("works_config", "recommend", "personal"))
        app = FakeApp(c, {})
        steps = behavior.post_login_browse(app, fast_rng())
        self.assertFalse(steps[0][1])            # 社区配置失败
        rec = dict(steps)
        rec2 = {n: g for n, g in steps}
        self.assertFalse(rec2.get("社区推荐流", True))   # 推荐流失败
        # 无推荐数据就没有帖子步骤，但后续照走
        names = [s for s, _ in steps]
        self.assertIn("里程排行榜", names)
        self.assertEqual(names[-1], "任务描述")
        self.assertTrue(steps[-1][1])            # 任务描述成功

    def test_跑后行为顺序(self):
        c = FakeClient()
        app = FakeApp(c, {})
        steps = behavior.post_run_browse(app, "RC1", 1, fast_rng())
        names = [s for s, _ in steps]
        self.assertEqual(names, ["跑单详情", "排行榜", "刷新红点"])
        self.assertIn("run_detail:RC1", c.calls)


if __name__ == "__main__":
    unittest.main()
