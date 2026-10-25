#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stderr 噪声过滤：吞掉 GTK/Wayland 剪贴板的无害 GDK 警告

为什么要单独成模块：这段逻辑原先内嵌在 gui.py 的线程里，既没法单测，也
容易改错。抽出来后用 tests/test_stderr_filter.py 直接覆盖各种行序。

要吞的原始输出（Ctrl+C 复制界面文字时刷屏）：
    (__main__.py:2292571): Gdk-WARNING **: 15:42:07.487:
    Error writing selection data: 写入文件描述符时出错：断开的管道
    <空行>
    <空行>

那条警告本身无害（Wayland 惰性剪贴板的 EPIPE 竞态，数据已进剪贴板），
但它**自带尾随空行**：GLib 把这条记录分多次写，正文行之后还跟着两个空行。
只删正文行会留下"两个空行"——警告没了但观感仍脏。所以本模块的做法是：

  · 命中噪音行 → 丢弃，并把「紧随其后最多 N 个空行」也一并吃掉
  · 普通行 → 正常输出，并复位该计数（不会无限吞下去）

为什么用"紧随其后"而不是"暂存所有空行再判断"：暂存只是延迟输出，空行
迟早还会冒出来（第一版就是这么写错的）。只吞紧跟噪音的那几个，既能清掉
GLib 记录的尾巴，又不会影响程序别处正常的空行排版。
"""
from __future__ import annotations

from typing import List

# 整句命中即可判定：GTK 剪贴板写失败的固定文案（英文原文 + 中文翻译）
MUTE_SENTENCES = (
    "Error writing selection data",
    "写入选择数据时出错",
)

# 片段命中需要上下文佐证：单独出现可能是别处的真错误
# （例如 Python 的 BrokenPipeError 堆栈里就有 "Broken pipe"）
MUTE_FRAGMENTS = (
    "写入文件描述符时出错",
    "Broken pipe",
)

# 上下文提示词：出现任一即可佐证"这是 GTK 剪贴板那条"
CONTEXT_HINTS = (
    "selection", "选择数据", "剪贴板", "clipboard", "Gdk", "Gtk",
)


def is_muted(text: str) -> bool:
    """该行是否为要吞掉的 GTK 剪贴板噪音

    判据分两档：整句文案直接命中；片段文案必须同时出现上下文提示，
    避免把别处真正的 Broken pipe / fd 写失败错误一起吞掉。
    """
    if any(s in text for s in MUTE_SENTENCES):
        return True
    if any(f in text for f in MUTE_FRAGMENTS) and any(c in text for c in CONTEXT_HINTS):
        return True
    return False


class StderrNoiseFilter:
    """逐行过滤 stderr：噪音行 + 其自带的尾随空行一起吞掉"""

    # GLib 那条记录后面固定跟 2 个空行；取 3 留一点余量
    TRAILING_BLANKS = 3

    def __init__(self, trailing_blanks: int = TRAILING_BLANKS) -> None:
        self._buf: bytes = b""
        self._trailing = 0
        self._max_trailing = max(0, int(trailing_blanks))

    def feed(self, chunk: bytes) -> bytes:
        """喂入一段原始字节，返回应当真正输出的字节"""
        self._buf += chunk
        out: List[bytes] = []
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            out.append(self._handle(line))
        return b"".join(out)

    def flush(self) -> bytes:
        """流结束：吐出未换行的尾行（不完整行不吞，避免丢真错误）"""
        tail, self._buf = self._buf, b""
        if tail and not is_muted(tail.decode("utf-8", "replace")):
            return tail
        return b""

    # ── 内部 ──
    def _handle(self, line: bytes) -> bytes:
        text = line.decode("utf-8", "replace")
        if is_muted(text):
            # 这条记录后面还跟着空行，一起吃掉
            self._trailing = self._max_trailing
            return b""
        if text.strip() == "":
            if self._trailing > 0:
                self._trailing -= 1
                return b""            # 属于噪音记录的尾巴
            return b"\n"
        self._trailing = 0            # 普通行出现，复位
        return line + b"\n"
