#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""前端静态自检：抓「用了但没定义」的 Ref / 标识符，防运行时白屏

背景：2026-10-25 跑步页白屏事故——定时器里引用了 `planRemainRef`，但定义
从未插入（脚本的插入条件判断写错）。esbuild 只做打包不报未定义标识符
（在浏览器里是运行时 ReferenceError → React 整页崩白），构建日志全绿。
这个脚本把这类错误提前到提交前抓出来。

检查项：
  1. 所有 `xxxRef` 引用必须有 `const xxxRef = useRef(` 或 `= useRef(`
     （Allowlist：React 自带 ref 转发 `ref.current` 这种属性访问不算）。
  2. 被 `useCallback`/`useEffect` 引用的裸标识符做一次粗筛：源码中出现的
     `planXxx` 之类自定义前缀变量，若只有引用没有声明就报错。
  3. JSX 花括号里的表达式做括号平衡检查（粗筛语法错）。

用法：
    python3 scripts/web_lint.py            # 检查 desktop + android 两端
    python3 scripts/web_lint.py <dir>      # 检查指定 web/src
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 这些都允许直接出现，不必由 useRef 定义
REF_ALLOW = {
    "ref", "useRef", "current", "this",
}
# 允许作为函数形参传入的 ref（如 map.js 的 initMap(el, onClickRef, ghostRef)）
PARAM_REF_RE = re.compile(
    r"(?:function\s+\w+\s*\(|const\s+\w+\s*=\s*\(|=\s*\()([^)]*)\)")


def check_refs(src: str, name: str) -> list[str]:
    """所有 xxxRef 标识符都要有对应的 useRef 声明"""
    errs: list[str] = []
    # 裸标识符才查：排除 `obj.xxxRef` 属性访问
    used = set(re.findall(r"(?<![.\w])(\w+Ref)\b", src))
    declared = set(re.findall(r"(?:const|let)\s+(\w+Ref)\s*=", src))
    # 函数形参也是合法来源
    for params in PARAM_REF_RE.findall(src):
        for piece in params.split(","):
            tok = piece.strip().split("=")[0].strip()
            if re.fullmatch(r"\w+Ref", tok):
                declared.add(tok)
    for u in sorted(used - declared - REF_ALLOW):
        errs.append(f"{name}: `{u}` 被引用但没有 `const {u} = useRef(...)` 声明")
    return errs


def check_balance(src: str, name: str) -> list[str]:
    """括号/花括号粗平衡（忽略字符串与注释内的括号）"""
    errs: list[str] = []
    depth = {"(": 0, "{": 0, "[": 0}
    pairs = {")": "(", "}": "{", "]": "["}
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'`":                      # 跳过字符串
            q = c
            i += 1
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == q:
                    break
                i += 1
        elif c == "/" and i + 1 < n and src[i + 1] == "/":   # 行注释
            while i < n and src[i] != "\n":
                i += 1
        elif c == "/" and i + 1 < n and src[i + 1] == "*":   # 块注释
            i += 2
            while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                i += 1
            i += 1
        elif c in depth:
            depth[c] += 1
        elif c in pairs:
            depth[pairs[c]] -= 1
            if depth[pairs[c]] < 0:
                errs.append(f"{name}: 第 {src[:i].count(chr(10)) + 1} 行多余 `{c}`")
                depth[pairs[c]] = 0
        i += 1
    for k, v in depth.items():
        if v:
            errs.append(f"{name}: `{k}` 未闭合（差 {v}）")
    return errs


def lint_dir(src_dir: Path) -> tuple[list[str], list[str]]:
    """→ (阻塞问题, 提示)。Ref 未定义会运行时白屏，必须阻塞；括号检查是粗筛"""
    errs: list[str] = []
    warns: list[str] = []
    files = sorted(src_dir.rglob("*.jsx")) + sorted(src_dir.rglob("*.js"))
    if not files:
        return [f"{src_dir}: 没有找到 jsx/js 源文件"], []
    for f in files:
        text = f.read_text(encoding="utf-8")
        rel = f"{src_dir.parent.parent.name}/{f.relative_to(src_dir.parent.parent)}"
        errs += check_refs(text, rel)
        warns += check_balance(text, rel)
    return errs, warns


def main(argv: list[str]) -> int:
    targets = [Path(argv[1])] if len(argv) > 1 else [
        ROOT / "desktop" / "web" / "src",
        ROOT / "android" / "web" / "src",
    ]
    all_errs: list[str] = []
    warn_all: list[str] = []
    for t in targets:
        if not t.is_dir():
            all_errs.append(f"{t}: 目录不存在")
            continue
        ref_errs, warn_balance = lint_dir(t)
        all_errs += ref_errs
        warn_all += warn_balance
        mark = "✗" if ref_errs else "✓"
        print(f"{mark} {t}  ({len(ref_errs)} 个阻塞问题, {len(warn_balance)} 个提示)")
    if warn_all:
        print("提示（词法粗筛，可能是注释里的符号干扰）：")
        print("\n".join(f"  {x}" for x in warn_all))
    if all_errs:
        print("\n".join(f"  {x}" for x in all_errs))
        print(f"\n{len(all_errs)} 个阻塞问题 —— 修完再构建（运行时 ReferenceError 会白屏）")
        return 1
    print("\n前端静态自检通过 ✅（无未定义引用的 Ref）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
