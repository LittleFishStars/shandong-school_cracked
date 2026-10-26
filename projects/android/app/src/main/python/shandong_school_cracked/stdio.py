#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标准流兜底：Windows GUI 打包（console=False）下 sys.stdout/stderr 是 None

现象（2026-10-26 v3.0.0-pre1 Windows 版）：
    Failed to execute script 'launcher' ... 'NoneType' object has no attribute 'isatty'
    File "shandong_school_cracked\\cli.py", line 36, in <module>

根因：spec 里 `console=(sys.platform != "win32")`——Windows 发布件是 GUI 子系统。
双击启动时进程**没有控制台**，CPython 把 sys.stdin/stdout/stderr 置为 None；
而 cli.py 在模块导入期就执行 `sys.stdout.isatty()`，直接崩。

处理策略（ensure_streams，按序）：
  ① 流不是 None → 什么都不做
  ② Windows：AttachConsole(ATTACH_PARENT_PROCESS) 尝试接管父进程的控制台，
     成功后重开 CONOUT$（从 cmd 启动时输出仍然可见）
  ③ 兜底：接 os.devnull（打印静默丢弃，绝不崩）

必须在**任何**触碰 sys.stdout/stderr 的模块导入之前调用——launcher.py 的
第一行、`python -m` 入口 cli.py 的头部都会调。模块级 `_TTY` 这类立即求值
也要同时改安全写法（本文件修完后 cli.py 已改），双保险。
"""
from __future__ import annotations

import os
import sys
from typing import Optional

_ATTACH_PARENT_PROCESS = -1
_STD_OUTPUT_HANDLE = -11
_STD_ERROR_HANDLE = -12


def _console_stream(name: str) -> Optional[object]:
    """Windows：尝试接管父进程控制台并重开 CONOUT$；失败返回 None"""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32        # type: ignore[attr-defined]
        if not kernel32.AttachConsole(_ATTACH_PARENT_PROCESS):
            return None
        which = _STD_OUTPUT_HANDLE if name == "stdout" else _STD_ERROR_HANDLE
        handle = kernel32.GetStdHandle(which)
        if handle in (None, 0, -1):
            return None
        import msvcrt
        fd = msvcrt.open_osfhandle(handle, os.O_WRONLY)
        return os.fdopen(fd, "w", encoding="utf-8", errors="replace")
    except Exception:                             # noqa: BLE001
        return None


def _null_stream() -> object:
    """最后兜底：写 devnull，静默丢弃（比 None 强——print/isatty 都不会崩）"""
    try:
        return open(os.devnull, "w", encoding="utf-8", errors="replace")
    except Exception:                             # noqa: BLE001
        return _DevNull()


class _DevNull:
    """连 devnull 都打不开时的最终兜底"""

    def isatty(self) -> bool:
        return False

    def write(self, *_a, **_k) -> int:
        return 0

    def flush(self) -> None:
        pass

    def reconfigure(self, *a, **k) -> None:
        pass

    def close(self) -> None:
        pass


def ensure_streams() -> None:
    """保证 sys.stdout / sys.stderr / sys.stdin 不是 None（幂等，可重复调用）"""
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            stream = _console_stream(name) or _null_stream()
            setattr(sys, name, stream)
    if getattr(sys, "stdin", None) is None:
        try:
            sys.stdin = open(os.devnull, "r", encoding="utf-8")
        except Exception:                          # noqa: BLE001
            sys.stdin = _DevNull()


def stream_tty(stream) -> bool:
    """流上安全的 isatty（None / 任意异常都按非 TTY 处理）"""
    try:
        return bool(stream is not None and stream.isatty())
    except Exception:                              # noqa: BLE001
        return False
