#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""桌面版 ↔ 安卓版「发往服务端的全部数据」一致性验证

核心思路：两端跑**同一个脚本化操作序列**，都在 `Transport._send` 这一层
抓下每个请求的 **path + 请求体原文**，逐字段比对。不依赖 mock 的
world.calls（它只记 path），也不靠人工读代码。

为什么抓 Transport：桌面 `gui/CLI` 与安卓 `android_api.dispatch` 最终都
汇聚到同一个 `shandong_school_cracked` 包的 Transport，这是唯一的出网口
——在这里抓到的就是「真正发给服务端的东西」。

用法：
    python3 projects/scripts/parity_check.py             # 比对
    python3 projects/scripts/parity_check.py --verbose   # 打印字段明细
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent          # projects/
DESKTOP = ROOT / "desktop"
ANDROID_PY = ROOT / "android" / "app" / "src" / "main" / "python"

# 两端包必须**同一顺序**导入：桌面在前，安卓 vendored 在后。
# 中途再插 path 会让 android_api 里的 App 指向另一份包副本（两个实例互不相干）。
sys.path.insert(0, str(DESKTOP))
sys.path.insert(0, str(ANDROID_PY))

# 值天然因会话/随机/设备而异：只比类型骨架，不比字面值
VOLATILE = {
    "runRecordCode", "timestamp", "deviceId", "satoken", "Authorization", "sign",
    "targetPoints", "pois", "stepList", "paceList", "strideList",
    "faceCheckRecordList", "runImgRecord", "startTime", "lat", "lng",
    "accessKeyId", "accessKeySecret", "securityToken", "expiration", "domain",
    "directory", "code", "token", "ticket", "satoken", "userId",
    # 由随机种子决定的合成量：安卓桥没暴露 seed 参数，两端各自随机，
    # 结构/类型/单位必须一致，具体数值必然不同（真实跑步也不会两次一样）
    "distance", "duration", "totalStep", "pace", "calorie",
}


def skeleton(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: skeleton(x) for k, x in v.items()}
    if isinstance(v, list):
        return [skeleton(v[0])] if v else []
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "number"
    if v is None:
        return "null"
    return "string"


def norm(body: Dict[str, Any]) -> Dict[str, Any]:
    return {k: (skeleton(v) if k in VOLATILE else v) for k, v in body.items()}


# ── 抓包器：给任一 Transport 实例装钩子 ──
def install_spy(transport, sink: List[Dict[str, Any]]) -> None:
    orig = transport._send

    def patched(url: str, headers: Dict[str, str], body):
        try:
            # GET 的 9 指纹在 query 里（含 timestamp），必须裁掉 query 才能归并
            raw = str(url)
            path = raw.split("run-front/")[-1].split("?")[0]
            parsed = json.loads(body.decode("utf-8")) if body else {}
        except Exception:  # noqa: BLE001
            path, parsed = str(url), {}
        sink.append({"path": path, "body": norm(parsed) if isinstance(parsed, dict) else {}})
        return orig(url, headers, body)

    transport._send = patched  # type: ignore[method-assign]


def wait_run(app, limit: int = 120) -> str:
    """等异步 run_auto 真正结算完

    mock 下整趟 0.1 秒就跑完，不能靠「此刻没在运行」判定。直接读
    app._last_result（status() 的同源字段，但省掉一次完整状态组装），
    以 upload/finish 出现为完成信号。
    """
    import time
    t0 = time.time()
    while time.time() - t0 < limit:
        last = getattr(app, "_last_result", None) or {}
        if last.get("finish") or last.get("upload"):
            return ""
        time.sleep(0.05)
    return f"超时（>{limit}s）未结算"




def bridge(method: str, args: Any) -> Dict[str, Any]:
    """调 android_api.dispatch 并把返回的 JSON 字符串解析成 dict"""
    import android_api
    raw = android_api.dispatch(method, json.dumps(args))
    try:
        return json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception:  # noqa: BLE001
        return {"_raw": raw}


def run_desktop() -> Tuple[List[Dict[str, Any]], str]:
    """桌面：App 门面（GUI/CLI 同一入口）"""
    from shandong_school_cracked.app import App

    tmp = Path(tempfile.mkdtemp(prefix="parity-desktop-"))
    app = App(data_dir=tmp, config_path=tmp / "config.json", mode="mock")
    sink: List[Dict[str, Any]] = []
    install_spy(app.client.transport, sink)
    err = ""
    try:
        app.login("13800138000", "any-password", False)
        app.run_prepare()
        r = app.run_auto(target_m=1200, fence_index=0, do_upload=True, do_finish=True)
        if r.get("code") != 0:
            err = f"run_auto: {r.get('message')}"
        else:
            err = wait_run(app)
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    finally:
        app.stop_mock()
    return sink, err


def run_android() -> Tuple[List[Dict[str, Any]], str]:
    """安卓：android_api.dispatch（WebView 桥唯一入口）"""
    import android_api  # noqa: E402  （路径已在模块顶层准备好）
    from shandong_school_cracked.app import App  # noqa: E402

    tmp = Path(tempfile.mkdtemp(prefix="parity-android-"))
    app = App(data_dir=tmp, config_path=tmp / "config.json", mode="mock")
    android_api._set_app(app)          # 官方测试钩子：注入 App 实例
    live = android_api.get_app() or app
    sink: List[Dict[str, Any]] = []
    install_spy(live.client.transport, sink)
    app = live
    err = ""
    try:
        bridge("login", ["13800138000", "any-password", False])
        bridge("prepare", [])
        r = bridge("run_auto", [1200.0, 0, True, True, 1])
        if r.get("code") != 0:
            err = f"run_auto: {r}"
        else:
            err = wait_run(app)
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    finally:
        app.stop_mock()
    return sink, err


def group(calls: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for c in calls:
        out.setdefault(c["path"], c["body"])
    return out


def compare(a: Dict[str, Dict[str, Any]], b: Dict[str, Dict[str, Any]],
            verbose: bool) -> List[str]:
    probs: List[str] = []
    only_a, only_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
    if only_a:
        probs.append(f"仅桌面发出 {len(only_a)} 个接口：{only_a}")
    if only_b:
        probs.append(f"仅安卓发出 {len(only_b)} 个接口：{only_b}")
    for path in sorted(set(a) & set(b)):
        ba, bb = a[path], b[path]
        ka, kb = set(ba), set(bb)
        if ka != kb:
            probs.append(f"{path}: 字段集不同 桌面多{sorted(ka-kb)} 安卓多{sorted(kb-ka)}")
        for k in sorted(ka & kb):
            va, vb = ba[k], bb[k]
            if type(va) is not type(vb):
                probs.append(f"{path}.{k}: 类型不同 {type(va).__name__} vs {type(vb).__name__}")
            elif k not in VOLATILE and va != vb:
                probs.append(f"{path}.{k}: 值不同 {va!r} vs {vb!r}")
        if verbose:
            print(f"\n◆ {path} —— {len(ka)} 字段")
            for k in sorted(ka):
                tag = " (动态)" if k in VOLATILE else ""
                print(f"    {k:<22} {ba[k]!r}{tag}")
    return probs


def run_side(side: str, out_path: Path) -> int:
    """单侧执行并落盘抓包（分进程跑，避免两端包在同一进程里互相污染）"""
    sink, err = run_desktop() if side == "desktop" else run_android()
    out_path.write_text(json.dumps({"calls": sink, "err": err}, ensure_ascii=False),
                        encoding="utf-8")
    return 0


def main(argv: List[str]) -> int:
    if "--side" in argv:
        side = argv[argv.index("--side") + 1]
        out = Path(argv[argv.index("--out") + 1])
        return run_side(side, out)
    verbose = "--verbose" in argv
    import subprocess
    tmpdir = Path(tempfile.mkdtemp(prefix="parity-out-"))
    results: Dict[str, Tuple[List[Dict[str, Any]], str]] = {}
    for side, label in (("desktop", "桌面版（App 门面）"),
                        ("android", "安卓版（android_api.dispatch）")):
        outp = tmpdir / f"{side}.json"
        print(f"① 跑{label}（mock，独立进程）…")
        cp = subprocess.run(
            [sys.executable, __file__, "--side", side, "--out", str(outp)],
            capture_output=True, text=True, timeout=300)
        if not outp.exists():
            print(f"   ✗ 子进程失败：{(cp.stderr or cp.stdout)[-400:]}")
            return 1
        data = json.loads(outp.read_text(encoding="utf-8"))
        results[side] = (data["calls"], data["err"])
        print(f"   {len(data['calls'])} 个请求" +
              (f"  ⚠ {data['err']}" if data["err"] else ""))
    sink_d, err_d = results["desktop"]
    sink_a, err_a = results["android"]

    a, b = group(sink_d), group(sink_a)
    print(f"\n③ 接口覆盖：桌面 {len(a)} / 安卓 {len(b)}")
    for p in sorted(set(a) | set(b)):
        both = "✓" if p in a and p in b else "✗"
        print(f"   {both} {p}")
    probs = compare(a, b, verbose)
    print()
    if probs:
        print(f"✗ {len(probs)} 处不一致：")
        for p in probs:
            print("   " + p)
        return 1
    print(f"✓ 两端上传数据完全一致（{len(a)} 个接口逐字段比对通过）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
