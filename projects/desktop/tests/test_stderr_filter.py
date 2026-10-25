#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stderr 噪音过滤器的行为测试

覆盖 2026-10-25 的真实故障序列：GTK 剪贴板警告 + 它自带的两个空行，
以及"不能误吞真错误"的边界（BrokenPipeError 堆栈、普通空行排版）。
"""
from __future__ import annotations

import unittest

from shandong_school_cracked.stderr_filter import StderrNoiseFilter, is_muted

WARN = ("(__main__.py:2292571): Gdk-WARNING **: 15:42:07.487: "
        "Error writing selection data: 写入文件描述符时出错：断开的管道")


def run_filter(chunks):
    f = StderrNoiseFilter()
    out = b"".join(f.feed(c) for c in chunks)
    return out + f.flush()


class 判定测试(unittest.TestCase):
    def test_英文原文命中(self):
        self.assertTrue(is_muted(WARN))

    def test_中文翻译也命中(self):
        self.assertTrue(is_muted("某处: 写入选择数据时出错：断开的管道"))

    def test_裸BrokenPipe不算噪音(self):
        # Python 的 BrokenPipeError 堆栈里有 "Broken pipe"，但没有上下文提示词
        self.assertFalse(is_muted("BrokenPipeError: [Errno 32] Broken pipe"))

    def test_裸写入文件描述符不算噪音(self):
        self.assertFalse(is_muted("写入文件描述符时出错"))

    def test_上下文与片段同时出现才算(self):
        self.assertTrue(is_muted("Gdk: Broken pipe"))
        self.assertTrue(is_muted("写入文件描述符时出错（clipboard）"))

    def test_普通错误行不命中(self):
        self.assertFalse(is_muted("ValueError: 真错误必须可见"))


class 过滤测试(unittest.TestCase):
    def test_警告行被吞(self):
        out = run_filter([(WARN + "\n").encode()])
        self.assertEqual(out, b"")

    def test_警告自带的两个空行也被吞(self):
        """这就是用户报的"警告没了但多两个空行"的场景"""
        raw = (WARN + "\n" + "\n" + "\n").encode()
        self.assertEqual(run_filter([raw]), b"")

    def test_警告后跟普通行只留普通行(self):
        raw = (WARN + "\n\n\nReal line\n").encode()
        self.assertEqual(run_filter([raw]), b"Real line\n")

    def test_尾随空行吃完后恢复正常空行(self):
        # 警告行末尾的 \n 之后还有 5 个空行；上限吞 3 个，剩下 2 个属于正常排版
        raw = (WARN + "\n" + "\n" * 5).encode()
        self.assertEqual(run_filter([raw]), b"\n\n")

    def test_普通空行排版不受影响(self):
        self.assertEqual(run_filter([b"a\n\nb\n"]), b"a\n\nb\n")

    def test_普通空行在无噪音时全部保留(self):
        self.assertEqual(run_filter([b"\n\n\n\n\n\n"]), b"\n\n\n\n\n\n")

    def test_真错误完整保留(self):
        err = b"Traceback (most recent call last):\nValueError: boom\n"
        self.assertEqual(run_filter([err]), err)

    def test_BrokenPipeError堆栈保留(self):
        err = (b"Traceback (most recent call last):\n"
               b"BrokenPipeError: [Errno 32] Broken pipe\n")
        self.assertEqual(run_filter([err]), err)

    def test_多次复制连续噪音(self):
        raw = ((WARN + "\n\n\n") * 3).encode()
        self.assertEqual(run_filter([raw]), b"")

    def test_分块喂入也能识别(self):
        """真实读管道时会被任意切开，必须按行缓冲而不是按块判断"""
        raw = (WARN + "\n\n\nReal\n").encode()
        chunks = [raw[i:i + 7] for i in range(0, len(raw), 7)]
        self.assertEqual(run_filter(chunks), b"Real\n")

    def test_跨块切断的噪音行仍被吞(self):
        head, tail = WARN[:40].encode(), (WARN[40:] + "\n\n\n").encode()
        self.assertEqual(run_filter([head, tail]), b"")

    def test_未换行尾行保留(self):
        # 流结束但没换行：不完整行不做判定，原样吐出（避免丢真错误）
        self.assertEqual(run_filter([b"partial without newline"]),
                         b"partial without newline")

    def test_未换行尾行是噪音则吞(self):
        self.assertEqual(run_filter([WARN.encode()]), b"")

    def test_空输入(self):
        self.assertEqual(run_filter([b""]), b"")


class 集成测试(unittest.TestCase):
    def test_真实故障序列(self):
        """完整还原一次 Ctrl+C：正常输出 + 警告记录 + 正常输出"""
        raw = (
            "已登录\n"
            + WARN + "\n\n\n"
            + "上传成功\n"
        ).encode()
        self.assertEqual(run_filter([raw]), "已登录\n上传成功\n".encode())

    def test_带时间戳前缀的警告(self):
        raw = ("2026-10-25 15:42:07 Gdk-WARNING **: Error writing selection data: "
               "写入文件描述符时出错：断开的管道\n\n\n").encode()
        self.assertEqual(run_filter([raw]), b"")


if __name__ == "__main__":
    unittest.main()
