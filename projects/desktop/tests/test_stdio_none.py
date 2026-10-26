#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows GUI 打包（console=False）标准流兜底测试

背景：3.0.0-pre1 的 Windows 版双击启动即崩——
    'NoneType' object has no attribute 'isatty'
根因：GUI 子系统进程没有控制台，CPython 把 sys.stdin/stdout/stderr 置为
None，而 cli.py 在模块导入期就执行 sys.stdout.isatty()。

这些测试用**子进程**模拟该场景（主进程里的流是好的，必须在干净进程里把
三个流置成 None 再导入），与 Windows 真实环境同构。
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_py(code: str) -> subprocess.CompletedProcess:
    """在子进程里执行；用 __stdout__ 报告结果（print 已不可用）"""
    # 多行 code 的每一行都要缩进进 try 块（只缩进首行会让 try 语法崩掉）
    indented = "\n".join("    " + ln for ln in code.splitlines())
    probe = (
        "import sys\n"
        "_real = sys.__stdout__\n"
        "sys.stdout = None; sys.stderr = None; sys.stdin = None\n"
        "try:\n"
        f"{indented}\n"
        "    _real.write('OK' + chr(10))\n"
        "except Exception as e:\n"
        "    _real.write('CRASH %s: %s' % (type(e).__name__, e) + chr(10))\n"
    )
    return subprocess.run([sys.executable, "-c", probe], capture_output=True,
                          text=True, cwd=str(ROOT), timeout=120)


class None流导入测试(unittest.TestCase):
    def test_三流全None时导入cli不崩(self):
        """原故障：3.0.0-pre1 Windows 版启动即崩"""
        p = run_py("import shandong_school_cracked.cli")
        self.assertIn("OK", p.stdout, f"仍崩：{p.stdout}{p.stderr}")
        self.assertNotIn("CRASH", p.stdout)

    def test_三流全None时导入gui不崩(self):
        p = run_py("import shandong_school_cracked.gui")
        self.assertIn("OK", p.stdout, f"仍崩：{p.stdout}{p.stderr}")

    def test_ensure_streams幂等(self):
        p = run_py(
            "from shandong_school_cracked import stdio\n"
            "stdio.ensure_streams(); stdio.ensure_streams()\n"
            "assert sys.stdout is not None and sys.stderr is not None\n"
        )
        self.assertIn("OK", p.stdout, f"仍崩：{p.stdout}{p.stderr}")

    def test_兜底流可写可isatty(self):
        p = run_py(
            "from shandong_school_cracked import stdio\n"
            "stdio.ensure_streams()\n"
            "print('print 不再崩')\n"
            "assert sys.stdout.isatty() in (True, False)\n"
            "sys.stderr.write('stderr-writable\\n')\n"
        )
        self.assertIn("OK", p.stdout, f"仍崩：{p.stdout}{p.stderr}")


class stream_tty安全测试(unittest.TestCase):
    def test_None返回False不抛异常(self):
        from shandong_school_cracked.stdio import stream_tty
        self.assertFalse(stream_tty(None))

    def test_真TTY按真值(self):
        from shandong_school_cracked.stdio import stream_tty
        self.assertIs(stream_tty(sys.stdout), sys.stdout.isatty())

    def test_坏流按False(self):
        from shandong_school_cracked.stdio import stream_tty

        class Bad:
            def isatty(self):
                raise OSError("broken")

        self.assertFalse(stream_tty(Bad()))


if __name__ == "__main__":
    unittest.main()
