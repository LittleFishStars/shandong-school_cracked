#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pcap_timeline.py 单元测试：用 stub tshark 输出验证时间线解析

不依赖真实抓包权限（沙箱里 dumpcap 需要 root），把 run_tshark 打成桩，
覆盖：域名过滤、三类事件、时间排序、相对秒数、无匹配报错、绝对时间兜底。
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "pcap_timeline", ROOT / "scripts" / "pcap_timeline.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class 时间线解析测试(unittest.TestCase):
    def test_三类事件按时间排序(self):
        # (epoch, SNI)，(epoch, HTTP...)，(epoch, DNS...)
        rows = {
            "tls": [["1730000002.500000", "mh5.huachenjie.com", "10.0.0.2"]],
            "http": [["1730000001.000000", "api.huachenjie.com", "GET", "/run-front/a"]],
            "dns": [["1730000000.000000", "api.huachenjie.com"]],
        }

        def fake(pcap, flt, fields):
            if "tls.handshake" in flt:
                return rows["tls"]
            if "http.request" in flt:
                return rows["http"]
            return rows["dns"]

        with mock.patch.object(mod, "run_tshark", fake):
            events = mod.collect(Path("dummy.pcap"), ("huachenjie",))
        self.assertEqual(len(events), 3)
        kinds = [k for _, k, _ in events]
        self.assertEqual(kinds, ["DNS", "HTTP", "SNI"])
        self.assertIn("GET http://api.huachenjie.com/run-front/a",
                      events[1][2])
        self.assertIn("HTTPS → mh5.huachenjie.com", events[2][2])

    def test_域名过滤参数透传(self):
        seen = []

        def fake(pcap, flt, fields):
            seen.append(flt)
            return []

        with mock.patch.object(mod, "run_tshark", fake):
            mod.collect(Path("dummy.pcap"), ("huachenjie", "aliyun"))
        self.assertTrue(all("huachenjie|aliyun" in f for f in seen),
                        f"过滤器未透传多域名：{seen}")

    def test_相对秒数与输出(self, ):
        rows = {"tls": [], "http": [],
                "dns": [["1730000000.000000", "api.huachenjie.com"],
                        ["1730000003.500000", "oss-cdn.huachenjie.com"]]}

        def fake(pcap, flt, fields):
            return rows["dns"] if "dns.flags" in flt else []

        out = ROOT / "build" / "timeline_test_out.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        with mock.patch.object(mod, "run_tshark", fake):
            rc = mod.main(["dummy.pcap", "--out", str(out), "--t0", "1730000000"])
        self.assertEqual(rc, 0)
        text = out.read_text(encoding="utf-8")
        self.assertIn("0.000s", text)
        self.assertIn("3.500s", text)
        self.assertIn("[DNS ]", text)

    def test_无匹配时返回失败(self):
        with mock.patch.object(mod, "run_tshark", lambda *a, **k: []):
            rc = mod.main(["dummy.pcap"])
        self.assertEqual(rc, 1)

    def test_坏时间戳不崩(self):
        rows = {"tls": [["not-a-number", "api.huachenjie.com", "10.0.0.1"]],
                "http": [], "dns": []}

        def fake(pcap, flt, fields):
            return rows["tls"] if "tls.handshake" in flt else []

        with mock.patch.object(mod, "run_tshark", fake):
            events = mod.collect(Path("dummy.pcap"), ("huachenjie",))
        self.assertEqual(len(events), 1)   # 不抛异常，仍产出事件

    def test_tshark失败转RuntimeError(self):
        def fake(*a, **k):
            raise RuntimeError("tshark 失败：文件损坏")

        with mock.patch.object(mod, "run_tshark", fake):
            with self.assertRaises(RuntimeError):
                mod.collect(Path("dummy.pcap"), ("huachenjie",))


if __name__ == "__main__":
    unittest.main()
