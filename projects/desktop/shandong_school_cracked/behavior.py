#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""行为链：模拟真机「登录后进首页浏览」与「结算后看成绩」的请求序列

为什么要有它：真机用户进 App 不会直奔跑步模块——先看消息红点、刷社区流、
点开帖子、看排行榜、瞄一眼个人资料，然后才进阳光跑。服务端若比对「起跑前
N 分钟的行为序列」，一个只有 startSunRun 而没有首页痕迹的账号本身就是异常
（方法论来自 ShandongTool 的 pre_run_behavior/post_run_behavior/keepalive，
路径与入参已按本项目反编译注解逐个核实，见 constants.EP 的"行为链"段）。

设计约定：
  · **失败静默**：行为链任何一步失败都绝不影响主流程（登录/结算该怎样还怎样）；
  · **真实时间**：请求之间用 time.sleep 走真实间隔（用户确认过），总时长
    控制在 ~8 秒内——真机浏览是分钟级，但工具里等太久伤可用性，取下限；
  · **节流防重**：同一天内多次进入不重复跑完整链（kv 记上次完成时间），
    避免每次启动都刷一遍反而假；
  · **仅真实服务端**：mock 模式没有这些路由，跳过（由调用方判断）。
"""
from __future__ import annotations

import random
import time
from typing import Any, List, Optional, Tuple

# 行为链配置键与节流键
CFG_KEY = "behavior"
KV_LAST_BROWSE = "behavior_last_browse"
BROWSE_COOLDOWN_S = 6 * 3600          # 同一账号 6 小时内不重复完整浏览链


def enabled(cfg: Any) -> bool:
    """配置开关：cfg.behavior（默认开）"""
    try:
        return bool(cfg.get(CFG_KEY, True))
    except Exception:                  # noqa: BLE001
        return True


def _gap(rng: random.Random, lo: float, hi: float) -> None:
    """两步之间的真实停顿"""
    try:
        time.sleep(rng.uniform(lo, hi))
    except Exception:                  # noqa: BLE001
        pass


def _should_run(app: Any) -> Tuple[bool, str]:
    """前置检查：(可跑?, 原因)"""
    if app is None or getattr(app, "_mock", None) is not None:
        return False, "mock 模式跳过（本地仿真无风控语义）"
    cli = getattr(app, "client", None)
    if cli is None or not getattr(cli, "logged_in", False):
        return False, "未登录"
    if not enabled(getattr(app, "cfg", {})):
        return False, "behavior 配置关闭"
    return True, ""


def _recently_browsed(app: Any) -> bool:
    try:
        last = app.store.kv_get(KV_LAST_BROWSE, {}) or {}
        rid = str(getattr(app.client, "user_id", "") or "")
        if str(last.get("user_id") or "") != rid:
            return False
        return (time.time() - float(last.get("ts", 0))) < BROWSE_COOLDOWN_S
    except Exception:                  # noqa: BLE001
        return False


def _mark_browsed(app: Any) -> None:
    try:
        app.store.kv_set(KV_LAST_BROWSE, {
            "user_id": str(getattr(app.client, "user_id", "") or ""),
            "ts": time.time(),
        })
    except Exception:                  # noqa: BLE001
        pass


def post_login_browse(app: Any, rng: Optional[random.Random] = None,
                      force: bool = False) -> List[Tuple[str, bool]]:
    """登录后/进入首页的浏览行为（2026-11-05 鸿蒙真机抓包实序，真实时间 ~10s）

    真机顺序（timestamp 排序）：
      api/works/worksConfig → api/jackpot/award/home → account/queryCommonUserInfo
      → api/common/getCommonConfig → api/tasks/loginOnce → api/works/…(社区)
      → api/search/suggestion/list → 排行榜 → schoolLetter/redDot
      → schoolLetter/importantLetterList → account/getUserResourceList
      → task/getDescription

    本实现按同序编排；每步真实停顿（总 ~10s，真机是分钟级，取下限）。
    返回 [(步骤名, 是否成功)]；任何异常都被吞掉。
    """
    steps: List[Tuple[str, bool]] = []
    ok, why = _should_run(app)
    if not ok:
        steps.append((why, False))
        return steps
    if not force and _recently_browsed(app):
        steps.append(("冷却期内跳过", False))
        return steps

    cli = app.client
    rng = rng or random.Random()

    def _step(name: str, fn) -> None:
        try:
            fn()
            steps.append((name, True))
        except Exception:              # noqa: BLE001
            steps.append((name, False))

    try:
        # —— 真机序列 1：首页模块 ——
        _step("社区配置", cli.works_config)
        _gap(rng, 0.3, 0.9)
        _step("抽奖首页", cli.jackpot_home)
        _gap(rng, 0.3, 0.9)
        _step("用户资料", cli.load_user)
        _gap(rng, 0.3, 0.9)
        _step("公共配置v2", cli.common_config_v2)
        _gap(rng, 0.3, 0.9)
        _step("登录任务", cli.tasks_login_once)
        _gap(rng, 0.4, 1.2)

        # —— 真机序列 2：社区浏览 ——
        works = {"code": -1, "data": {}}
        _step("社区推荐流", lambda: works.update(
            cli.works_recommend(page_size=rng.choice([5, 10, 20])) or {}))
        _gap(rng, 0.5, 1.4)
        try:
            lst = ((works.get("data") or {}).get("list")
                   if isinstance(works.get("data"), dict) else []) or []
            for w in lst[:rng.randint(1, 2)]:
                wn = str((w or {}).get("worksNo") or "")
                if not wn:
                    continue
                _gap(rng, 0.8, 2.0)
                _step("帖子详情", lambda wn=wn: cli.works_detail(wn))
                _gap(rng, 1.0, 2.5)        # 阅读停留
                _step("上报浏览", lambda wn=wn: cli.works_visit(wn))
        except Exception:              # noqa: BLE001
            pass
        _gap(rng, 0.4, 1.2)
        _step("搜索热词", cli.search_suggest)
        _gap(rng, 0.4, 1.2)
        _step("里程排行榜", cli.rank_distance)
        _gap(rng, 0.4, 1.2)

        # —— 真机序列 3：校园信 / 资源 / 任务 ——
        _step("校园信红点", cli.school_letter_red)
        _gap(rng, 0.3, 0.9)
        _step("重要信件", cli.school_letter_list)
        _gap(rng, 0.3, 0.9)
        _step("用户资源", cli.user_resource)
        _gap(rng, 0.3, 0.9)
        _step("任务描述", cli.task_description)

        _mark_browsed(app)
    except Exception:                  # noqa: BLE001  整链兜底：绝不外抛
        steps.append(("行为链异常", False))
    return steps


def post_run_browse(app: Any, run_code: str, sport_type: int = 1,
                    rng: Optional[random.Random] = None) -> List[Tuple[str, bool]]:
    """结算后的行为：看成绩详情 → 看排行榜 → 刷红点

    真机结算完不会立刻退出 App：成绩页停留 → 点进详情看轨迹 → 回排行榜。
    结算后 0 请求直接下线等于"跑完就把手机关了"，是可识别的行为缺口。
    在后台线程里跑（由 engine.finish 触发），不阻塞结算返回。
    """
    steps: List[Tuple[str, bool]] = []
    ok, why = _should_run(app)
    if not ok:
        steps.append((why, False))
        return steps
    cli = app.client
    rng = rng or random.Random()
    try:
        _gap(rng, 1.2, 3.0)            # 成绩页停留
        try:
            cli.run_detail(run_code, sport_type=int(sport_type))
            steps.append(("跑单详情", True))
        except Exception:              # noqa: BLE001
            steps.append(("跑单详情", False))
        _gap(rng, 1.5, 4.0)
        try:
            cli.rank_distance()
            steps.append(("排行榜", True))
        except Exception:              # noqa: BLE001
            steps.append(("排行榜", False))
        _gap(rng, 1.0, 3.0)
        try:
            cli.message_red_dot()
            steps.append(("刷新红点", True))
        except Exception:              # noqa: BLE001
            steps.append(("刷新红点", False))
    except Exception:                  # noqa: BLE001
        steps.append(("跑后行为异常", False))
    return steps


def browse_async(app: Any, run_code: str = "", sport_type: int = 1,
                 which: str = "post_run") -> Optional[Any]:
    """把行为链丢到后台线程（跑后场景用；登录后场景因要覆盖 loading 页，走同步）"""
    import threading
    if which == "post_run" and run_code:
        t = threading.Thread(target=post_run_browse, args=(app, run_code, sport_type),
                             name="shandong-behavior-post-run", daemon=True)
        t.start()
        return t
    return None
