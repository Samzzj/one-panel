#!/usr/bin/env python3
"""One Panel Node Agent —— 装在被管理机器上的小型执行端。

职责只有四件事：
    GET  /health   报告 Xray 与主机状态
    POST /apply    写入 Xray 配置 -> 测试 -> 重启
    GET  /stats    读取每个用户的流量计数
    POST /nginx    写入自偷自 Nginx 配置 -> 测试 -> reload

鉴权：请求头 X-Agent-Token，必须与服务端启动参数一致。
只依赖 Python 标准库，单文件即可运行。
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import shlex
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

AGENT_VERSION = "0.4.0"
MAX_BODY = 2 * 1024 * 1024


# ---------------------------------------------------------------- 工具


def now() -> int:
    return int(time.time())


def run(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def atomic_write(path: str, text: str, mode: int = 0o640) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.chmod(tmp, mode)
        except OSError:
            pass
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Agent:
    def __init__(self, args: argparse.Namespace):
        self.token = args.token
        self.xray_bin = args.xray_bin
        self.xray_config = args.xray_config
        self.api = args.xray_api
        self.restart_cmd = args.restart_cmd
        self.status_cmd = args.status_cmd
        self.nginx_dir = os.path.realpath(args.nginx_dir)
        self.started_at = now()

    # ------------------------------------------------------------ Xray

    def xray_version(self) -> str:
        try:
            proc = run([self.xray_bin, "version"], timeout=8)
        except (OSError, subprocess.SubprocessError):
            return ""
        if proc.returncode != 0:
            return ""
        lines = (proc.stdout or proc.stderr or "").strip().splitlines()
        return lines[0].strip() if lines else ""

    def xray_active(self) -> bool:
        try:
            proc = run(shlex.split(self.status_cmd), timeout=8)
        except (OSError, subprocess.SubprocessError, ValueError):
            return False
        return proc.returncode == 0 and "active" in (proc.stdout or "").strip()

    def apply(self, config: dict) -> dict:
        text = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
        result: dict[str, Any] = {
            "ok": False, "tested": False, "test_ok": False, "test_output": "",
            "restarted": False, "restart_output": "", "warnings": [],
        }

        if not self.xray_version():
            atomic_write(self.xray_config, text)
            result["warnings"].append("节点上未找到 xray，已写入配置但未测试/重启")
            result["ok"] = True
            return result

        tmp = self.xray_config + ".agent-test.json"
        try:
            atomic_write(tmp, text, 0o600)
            proc = run([self.xray_bin, "run", "-test", "-c", tmp], timeout=20)
        except (OSError, subprocess.SubprocessError) as exc:
            result["test_output"] = f"无法执行 xray：{exc}"
            return result
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

        result["tested"] = True
        result["test_ok"] = proc.returncode == 0
        result["test_output"] = ((proc.stdout or "") + (proc.stderr or "")).strip()[-4000:]
        if proc.returncode != 0:
            return result

        try:
            atomic_write(self.xray_config, text, 0o640)
        except OSError as exc:
            result["warnings"].append(f"写入 {self.xray_config} 失败：{exc}")
            return result

        try:
            proc = run(shlex.split(self.restart_cmd), timeout=40)
            result["restarted"] = proc.returncode == 0
            result["restart_output"] = ((proc.stdout or "") + (proc.stderr or "")).strip()[-2000:]
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            result["restart_output"] = str(exc)
        result["ok"] = result["restarted"]
        if not result["restarted"]:
            result["warnings"].append("配置已写入，但重启 Xray 失败")
        return result

    def stats(self) -> dict:
        try:
            proc = run(
                [self.xray_bin, "api", "statsquery", f"--server={self.api}", "-pattern", "user>>>"],
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return {}
        if proc.returncode != 0:
            return {}
        try:
            payload = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            return {}
        users: dict[str, dict[str, int]] = {}
        for item in payload.get("stat") or []:
            parts = (item.get("name") or "").split(">>>")
            if len(parts) != 4 or parts[0] != "user":
                continue
            email, direction = parts[1], parts[3]
            try:
                value = int(item.get("value") or 0)
            except (TypeError, ValueError):
                continue
            slot = users.setdefault(email, {"up": 0, "down": 0})
            if direction == "uplink":
                slot["up"] = value
            elif direction == "downlink":
                slot["down"] = value
        return users

    # ------------------------------------------------------------ Nginx

    def apply_nginx(self, path: str, conf: str) -> dict:
        result: dict[str, Any] = {"ok": False, "tested": False, "test_output": "", "reloaded": False}
        real = os.path.realpath(path)
        if not real.startswith(self.nginx_dir + os.sep) or not real.endswith(".conf"):
            result["test_output"] = f"拒绝写入 {path}：只允许 {self.nginx_dir}/*.conf"
            return result
        if not conf.strip():
            result["test_output"] = "配置为空"
            return result

        backup = None
        if os.path.exists(real):
            try:
                backup = Path(real).read_text(encoding="utf-8")
            except OSError:
                backup = None
        try:
            atomic_write(real, conf, 0o644)
        except OSError as exc:
            result["test_output"] = f"写入失败：{exc}"
            return result

        try:
            proc = run(["nginx", "-t"], timeout=20)
        except (OSError, subprocess.SubprocessError):
            if backup is not None:
                atomic_write(real, backup, 0o644)
            else:
                try:
                    os.unlink(real)
                except OSError:
                    pass
            result["test_output"] = "节点上未找到 nginx"
            return result

        result["tested"] = True
        result["test_output"] = ((proc.stdout or "") + (proc.stderr or "")).strip()[-4000:]
        if proc.returncode != 0:
            if backup is not None:
                atomic_write(real, backup, 0o644)
            else:
                try:
                    os.unlink(real)
                except OSError:
                    pass
            return result

        try:
            proc = run(["systemctl", "reload", "nginx"], timeout=30)
            result["reloaded"] = proc.returncode == 0
            result["test_output"] += "\n" + ((proc.stdout or "") + (proc.stderr or "")).strip()[-1000:]
        except (OSError, subprocess.SubprocessError):
            result["reloaded"] = False
        result["ok"] = result["reloaded"]
        return result


# ---------------------------------------------------------------- HTTP


class Handler(BaseHTTPRequestHandler):
    server_version = "OnePanelAgent"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    agent: Agent  # set by server

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        return

    def _send(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _auth(self) -> bool:
        token = self.headers.get("X-Agent-Token", "")
        return bool(token) and hmac.compare_digest(token, self.agent.token)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?")[0] != "/health":
            self._send({"ok": False, "error": "not found"}, 404)
            return
        if not self._auth():
            self._send({"ok": False, "error": "invalid token"}, 401)
            return
        version = self.agent.xray_version()
        self._send(
            {
                "ok": True,
                "agent": AGENT_VERSION,
                "hostname": socket.gethostname(),
                "now": now(),
                "uptime": now() - self.agent.started_at,
                "xray": {
                    "installed": bool(version),
                    "version": version,
                    "active": self.agent.xray_active(),
                    "config": self.agent.xray_config,
                },
            }
        )

    def do_POST(self) -> None:  # noqa: N802
        if not self._auth():
            self._send({"ok": False, "error": "invalid token"}, 401)
            return
        path = self.path.split("?")[0]
        try:
            if path == "/apply":
                payload = self._body()
                config = payload.get("config")
                if not isinstance(config, dict):
                    self._send({"ok": False, "error": "缺少 config 对象"}, 400)
                    return
                self._send(self.agent.apply(config))
                return
            if path == "/nginx":
                payload = self._body()
                conf = payload.get("conf")
                target = payload.get("path") or os.path.join(self.agent.nginx_dir, "reality-selfsteal.conf")
                if not isinstance(conf, str):
                    self._send({"ok": False, "error": "缺少 conf 文本"}, 400)
                    return
                self._send(self.agent.apply_nginx(str(target), conf))
                return
            if path == "/stats":
                self._send({"ok": True, "users": self.agent.stats()})
                return
            self._send({"ok": False, "error": "not found"}, 404)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._send({"ok": False, "error": "agent internal error"}, 500)

    def do_HEAD(self) -> None:  # noqa: N802
        self._send({"ok": True})


class AgentServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], agent: Agent):
        Handler.agent = agent
        super().__init__(address, Handler)
        self.agent = agent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One Panel node agent")
    parser.add_argument("--bind", default=os.environ.get("AGENT_BIND", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("AGENT_PORT", "8787")))
    parser.add_argument("--token", default=os.environ.get("AGENT_TOKEN", ""))
    parser.add_argument("--xray-bin", default=os.environ.get("AGENT_XRAY_BIN", "xray"))
    parser.add_argument(
        "--xray-config",
        default=os.environ.get("AGENT_XRAY_CONFIG", "/usr/local/etc/xray/config.json"),
    )
    parser.add_argument("--xray-api", default=os.environ.get("AGENT_XRAY_API", "127.0.0.1:10085"))
    parser.add_argument(
        "--restart-cmd",
        default=os.environ.get("AGENT_RESTART_CMD", "systemctl restart xray"),
    )
    parser.add_argument(
        "--status-cmd",
        default=os.environ.get("AGENT_STATUS_CMD", "systemctl is-active xray"),
    )
    parser.add_argument("--nginx-dir", default=os.environ.get("AGENT_NGINX_DIR", "/etc/nginx/conf.d"))
    parser.add_argument("--version", action="version", version=f"one-panel-agent {AGENT_VERSION}")
    args = parser.parse_args(argv)

    if not args.token:
        print("缺少 --token（或 AGENT_TOKEN）", file=sys.stderr)
        return 2

    agent = Agent(args)
    server = AgentServer((args.bind, args.port), agent)
    print(f"[agent] {AGENT_VERSION} listening on {args.bind}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
