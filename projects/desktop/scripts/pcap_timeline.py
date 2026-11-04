#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""华为「网络报文分析」pcap/pcapng → 闪动校园请求时间线

华为开发者选项的报文抓包导出的是 pcap/pcapng。HTTPS 加密，看不到
path/body，但能看到：
  · TLS ClientHello 的 SNI（访问了哪些域名）
  · 每条连接的时间与方向（启动行为的**节奏**）
  · 明文 HTTP（原 app usesCleartextTraffic=true，可能有少量明文请求）

本脚本用 tshark 把这三类抽成统一时间线，按域名过滤，输出与
docs/capture-huawei.md 的「预期序列」对照。

用法：
    python scripts/pcap_timeline.py capture.pcapng
    python scripts/pcap_timeline.py capture.pcapng --host huachenjie --out timeline.txt
依赖：tshark（本机已装 /usr/bin/tshark）
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

DEFAULT_HOSTS = ("huachenjie",)


def _ts(fmt: str, f: str) -> datetime:
    """tshark 的 frame.time_epoch（秒.微秒）→ datetime（本地时区）"""
    try:
        return datetime.fromtimestamp(float(f))
    except Exception:  # noqa: BLE001
        return datetime.min.replace(tzinfo=timezone.utc)


def run_tshark(pcap: Path, display_filter: str, fields: List[str]) -> List[List[str]]:
    cmd = ["tshark", "-r", str(pcap), "-Y", display_filter,
           "-T", "fields", "-E", "separator=|", "-E", "occurrence=a"]
    for fld in fields:
        cmd += ["-e", fld]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        err = (p.stderr or "").strip().splitlines()
        raise RuntimeError(f"tshark 失败：{err[-1] if err else p.returncode}")
    rows = []
    for line in p.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        parts += [""] * (len(fields) - len(parts))
        rows.append(parts)
    return rows


def collect(pcap: Path, hosts: Tuple[str, ...]) -> List[Tuple[datetime, str, str]]:
    """→ [(时间, 类别, 摘要)]，按时间排序；类别 ∈ DNS/SNI/HTTP/TCP"""
    host_re = "|".join(hosts)
    events: List[Tuple[datetime, str, str]] = []

    # ① TLS ClientHello 的 SNI（HTTPS 目标域名）
    for row in run_tshark(pcap,
                          f"tls.handshake.type == 1 && tls.handshake.extensions_server_name contains \"{host_re}\"",
                          ["frame.time_epoch", "tls.handshake.extensions_server_name",
                           "ip.dst"]):
        events.append((_ts("epoch", row[0]), "SNI",
                       f"HTTPS → {row[1]} (dst {row[2]})"))

    # ② 明文 HTTP 请求（usesCleartextTraffic=true，可能有）
    for row in run_tshark(pcap,
                          f'http.request && http.host contains "{host_re}"',
                          ["frame.time_epoch", "http.host", "http.request.method",
                           "http.request.uri"]):
        events.append((_ts("epoch", row[0]), "HTTP",
                       f"{row[2]} http://{row[1]}{row[3]}"))

    # ③ DNS 查询（启动期解析了哪些域名）
    for row in run_tshark(pcap,
                          f'dns.flags.response == 0 && dns.qry.name contains "{host_re}"',
                          ["frame.time_epoch", "dns.qry.name"]):
        events.append((_ts("epoch", row[0]), "DNS", f"解析 {row[1]}"))

    events.sort(key=lambda e: e[0])
    return events


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="华为报文分析 pcap → 闪动校园时间线")
    ap.add_argument("pcap", type=Path, help="pcap / pcapng 抓包文件")
    ap.add_argument("--host", default=",".join(DEFAULT_HOSTS),
                    help=f"域名过滤（逗号分隔，默认 {','.join(DEFAULT_HOSTS)}）")
    ap.add_argument("--out", type=Path, default=None, help="输出文件（默认打印）")
    ap.add_argument("--t0", type=float, default=None,
                    help="以第一条事件为 0 的相对秒数（默认直接打印绝对时间）")
    args = ap.parse_args(argv)

    hosts = tuple(h.strip() for h in args.host.split(",") if h.strip())
    try:
        # 文件不存在交给 tshark 报错（collect 内 run_tshark 会转 RuntimeError）；
        # 这样 run_tshark 可被打桩测试，生产行为不变
        events = collect(args.pcap, hosts)
    except RuntimeError as e:
        print(f"✗ {e}", file=sys.stderr)
        print("  提示：华为导出的若是专有格式（非 pcap/pcapng），tshark 无法直接读，"
              "先在手机上用「导出/分享」拿到标准 pcap。", file=sys.stderr)
        return 1

    lines = []
    t_base = args.t0 if args.t0 is not None else (
        events[0][0].timestamp() if events else 0.0)
    for t, kind, desc in events:
        rel = t.timestamp() - t_base
        lines.append(f"{rel:8.3f}s  [{kind:<4}]  {desc}")
    header = (f"# {args.pcap.name} — 闪动校园时间线（{len(events)} 条，"
              f"域名过滤 {hosts}）")
    if args.out:
        args.out.write_text("\n".join([header] + lines) + "\n", encoding="utf-8")
        print(f"✓ {len(events)} 条事件 → {args.out}")
    else:
        print(header)
        print("\n".join(lines))
    if not events:
        print("⚠ 没有匹配事件：确认 ①抓包期间完整走了登录→首页 ②过滤域名是否正确 "
              "③抓的是不是目标手机的网卡流量", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
