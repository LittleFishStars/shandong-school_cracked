#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyInstaller 的入口脚本

打包器会把它当成顶层 `__main__` 执行，此时相对导入（`from .cli import main`）
会因为不在包里而失败，所以单独放一个绝对导入的薄壳。
源码运行时一切照旧用 `python -m shandong_school_cracked`。
"""
from __future__ import annotations

import sys

# 必须在导入 cli 之前执行：cli 在模块导入期就会触碰 sys.stdout（着色判定）。
# Windows GUI 打包下这三个流是 None，不兜底就是 3.0.0-pre1 的启动即崩。
from shandong_school_cracked import stdio
stdio.ensure_streams()

from shandong_school_cracked.cli import main

if __name__ == "__main__":
    sys.exit(main())
