#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""局域网文件接收：手机浏览器上传抓包文件 → tmp/capture/

HarmonyOS NEXT 无 adb/hdc，手机抓的 pcap 用浏览器直接传最快。
用法：python scripts/upload_server.py [端口]
手机访问 http://<本机IP>:8899 ，选文件上传，多文件可重复传。
"""
from __future__ import annotations

import html
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent.parent.parent / "tmp" / "capture"
PAGE = """<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>抓包文件上传</title>
<style>
body{font-family:system-ui;margin:0;padding:24px;background:#f5f6f8;color:#222}
h1{font-size:20px} .card{background:#fff;border-radius:16px;padding:24px;
box-shadow:0 2px 12px rgba(0,0,0,.06);margin-bottom:16px}
input[type=file]{width:100%;margin:12px 0}
input[type=submit]{width:100%;padding:14px;border:0;border-radius:12px;
background:#1677ff;color:#fff;font-size:16px}
.ok{color:#0a0;padding:8px 0;font-weight:600}
ul{padding-left:20px;line-height:1.8}
</style>
<h1>抓包文件上传</h1>
<div class=card>
<form method=POST enctype=multipart/form-data>
<input type=file name=f accept=".pcap,.pcapng,.cap,.har,.json,.zip,.txt,.log" multiple>
<input type=submit value="上 传">
</form>__MSG__
</div>
<div class=card><b>已收到的文件</b><ul>__FILES__</ul></div>
<p>上传完成后回到电脑告诉 AI 一声即可。</p>
"""


def listing() -> str:
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(OUT.iterdir(), key=lambda p: p.stat().st_mtime)
    if not files:
        return "<li>（暂无）</li>"
    return "".join(f"<li>{html.escape(p.name)} — {p.stat().st_size} B</li>"
                   for p in files)


class H(BaseHTTPRequestHandler):
    def _page(self, msg: str = "") -> None:
        body = (PAGE
                .replace("__MSG__", f'<div class=ok>{msg}</div>' if msg else "")
                .replace("__FILES__", listing())
                .encode("utf-8"))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._page()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            self._page("空请求")
            return
        body = self.rfile.read(length)
        # 解析 multipart：只取第一个文件部分（够用）
        ctype = self.headers.get("Content-Type", "")
        boundary = ctype.split("boundary=")[-1].encode()
        name = "capture.bin"
        data = b""
        for part in body.split(b"--" + boundary):
            if b"filename=" not in part:
                continue
            head, _, payload = part.partition(b"\r\n\r\n")
            payload = payload.rsplit(b"\r\n", 1)[0]
            for line in head.split(b"\r\n"):
                if b"filename=" in line:
                    seg = line.split(b"filename=")[1]
                    name = seg.split(b'"')[1].decode("utf-8", "replace") if b'"' in seg \
                        else seg.decode("utf-8", "replace")
                    name = Path(name).name or "capture.bin"
            data = payload
        if not data:
            self._page("未取到文件内容")
            return
        OUT.mkdir(parents=True, exist_ok=True)
        target = OUT / f"{int(__import__('time').time())}_{name}"
        target.write_bytes(data)
        print(f"[收到] {target.name} — {len(data)} 字节", flush=True)
        self._page(f"已收到 {name}（{len(data)} 字节）")

    def log_message(self, *a):  # 静默访问日志
        pass


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:  # noqa: BLE001
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"手机浏览器访问：http://{lan_ip()}:{port}", flush=True)
    print(f"文件落盘：{OUT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
