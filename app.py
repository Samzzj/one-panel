#!/usr/bin/env python3
"""Reality Panel 入口。

用法：
    python3 app.py                     # 默认 127.0.0.1:8080，数据在 ./data
    python3 app.py --host 0.0.0.0      # 直接对外（请自行加 TLS / 防火墙）
    python3 app.py sweep               # 采样流量 + 停用过期/超额订阅（systemd timer 调用）

环境变量：
    REALITY_PANEL_DATA   数据目录
    REALITY_PANEL_HOST   监听地址
    REALITY_PANEL_PORT   监听端口
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

from panel import __version__
from panel.access import is_allowed, normalize
from panel.api import build_router
from panel.auth import LoginLimiter
from panel.db import Database, Store
from panel.httpd import build_server, serve_forever
from panel.util import now
from panel.xray import Xray


class App:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.data_dir, 0o700)
        except OSError:
            pass
        self.db = Database(self.data_dir / "panel.db")
        self.db.init()
        self.store = Store(self.db)
        self.xray = Xray(self.store)
        self.limiter = LoginLimiter()
        self.router = build_router()
        self.started_at = now()
        self._log_lock = threading.Lock()
        if self.store.meta("dirty", "") == "":
            self.store.set_meta("dirty", "0")

    # ------------------------------------------------------------ 状态

    def mark_dirty(self, dirty: bool = True) -> None:
        self.store.set_meta("dirty", "1" if dirty else "0")

    def setup_required(self) -> bool:
        return self.store.user_count() == 0

    def access_blocked(self, ip: str, path: str) -> bool:
        """面板级 IP 白名单。空名单=不限制；/sub/ 默认不限制。"""
        settings = self.store.settings()
        text = (settings.get("access_allowlist") or "").strip()
        if not text:
            return False
        if path == "/healthz":
            return False
        if path.startswith("/sub/") and settings.get("access_allowlist_sub", "0") != "1":
            return False
        include_loopback = settings.get("access_allowlist_loopback", "1") == "1"
        return not is_allowed(ip, text, include_loopback)

    # ------------------------------------------------------------ 日志

    @staticmethod
    def _scrub(path: str) -> str:
        # 订阅 token 是凭据，不写进日志
        if path.startswith("/sub/"):
            return "/sub/***"
        return path

    def log_request(self, method: str, path: str, status: int, duration: float) -> None:
        if path.startswith(("/assets/", "/healthz")) or path == "/favicon.svg":
            return
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{stamp}] {method} {self._scrub(path)} {status} {duration * 1000:.0f}ms"
        with self._log_lock:
            print(line, file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VLESS + REALITY 管理面板")
    parser.add_argument("--host", default=os.environ.get("REALITY_PANEL_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("REALITY_PANEL_PORT", "8080"))
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("REALITY_PANEL_DATA", str(Path(__file__).parent / "data")),
    )
    parser.add_argument("--version", action="version", version=f"reality-panel {__version__}")
    parser.add_argument(
        "command",
        nargs="?",
        choices=["serve", "sweep", "status", "allow"],
        default="serve",
        help="serve=启动面板（默认）, sweep=采样并停用过期订阅, status=打印概览, allow=追加白名单 IP",
    )
    parser.add_argument(
        "value",
        nargs="?",
        help="allow 命令的参数：IP / CIDR，或 clear 清空白名单",
    )
    args = parser.parse_args(argv)

    app = App(args.data_dir)

    if args.command == "allow":
        if not args.value:
            print("用法: python3 app.py allow <IP 或 CIDR>   |   python3 app.py allow clear", file=sys.stderr)
            return 2
        if args.value.lower() == "clear":
            app.store.save_settings({"access_allowlist": ""})
            print("访问白名单已清空，面板恢复为不限制")
            return 0
        try:
            text = normalize(f"{app.store.setting('access_allowlist')}\n{args.value}")
        except ValueError as exc:
            print(f"格式不正确：{exc}", file=sys.stderr)
            return 2
        app.store.save_settings({"access_allowlist": text})
        print("当前访问白名单：\n" + text)
        return 0

    if args.command == "sweep":
        # 先采样流量，否则额度判断用的还是上一次的旧数据
        app.xray.collect_stats()
        changed = app.store.sweep()
        if changed:
            app.mark_dirty()
        # 有改动，或上次应用失败留下了 dirty 标记，都重新应用一次
        if app.store.meta("dirty", "0") == "1":
            result = app.xray.apply()
            print(json.dumps({"changed": changed, "applied": result.get("ok")}, ensure_ascii=False))
        else:
            print(json.dumps({"changed": False, "applied": False}, ensure_ascii=False))
        return 0

    if args.command == "status":
        print(json.dumps({"summary": app.store.summary(), "xray": app.xray.status()}, ensure_ascii=False, indent=2))
        return 0

    server = build_server(args.host, args.port, app)
    print(f"[panel] reality-panel {__version__}", flush=True)
    print(f"[panel] 数据目录: {app.data_dir.resolve()}", flush=True)
    print(f"[panel] 初始化: {'待完成（首次打开页面设置管理员）' if app.setup_required() else '已完成'}", flush=True)
    print(f"[panel] 访问: http://{args.host}:{args.port}/", flush=True)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("[panel] 警告: 面板直接监听在非回环地址，请务必用防火墙限制来源 IP", flush=True)

    def _stop(signum, frame):  # noqa: ARG001
        raise KeyboardInterrupt

    try:
        signal.signal(signal.SIGTERM, _stop)
    except (ValueError, OSError):
        pass

    serve_forever(server)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
