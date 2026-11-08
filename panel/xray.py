"""Xray 配置生成、进程控制与流量统计。

生成的是完整 server 配置：REALITY 入站 + 本地 API 入站 + 路由 + 出站。
面板不直接持有 Xray 进程，只负责写配置、测试、调用 systemctl 重启，
这样 Xray 由 systemd 托管，面板重启不会断线。
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
from typing import Any

from .db import Store
from .util import atomic_write
from .x25519 import generate_keypair, public_from_private_b64

# 路由里显式列出的内网网段，避免依赖 geoip.dat（缺文件会导致启动失败）
PRIVATE_CIDRS = [
    "0.0.0.0/8",
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.0.0.0/24",
    "192.168.0.0/16",
    "198.18.0.0/15",
    "::1/128",
    "fc00::/7",
    "fe80::/10",
]

CLIENT_LEVEL = 0


def _api_address(settings: dict[str, str]) -> tuple[str, int]:
    raw = (settings.get("xray_api") or "127.0.0.1:10085").strip()
    host, _, port = raw.rpartition(":")
    if not host:
        return "127.0.0.1", 10085
    return host, int(port)


def _client_entry(client: dict, transport: str) -> dict:
    entry: dict[str, Any] = {
        "id": client["uuid"],
        "email": f"c{client['id']}",
        "level": CLIENT_LEVEL,
    }
    if transport != "xhttp":
        entry["flow"] = "xtls-rprx-vision"
    return entry


def _stream_settings(node: dict) -> dict:
    transport = (node.get("transport") or "vision").lower()
    stream: dict[str, Any] = {
        "network": "xhttp" if transport == "xhttp" else "tcp",
        "security": "reality",
        "realitySettings": {
            "show": False,
            "dest": node["dest"],
            "xver": int(node.get("xver") or 0),
            "serverNames": [node["sni"]],
            "privateKey": node["private_key"],
            "shortIds": node.get("short_ids") or [""],
        },
    }
    if transport == "xhttp":
        stream["xhttpSettings"] = {
            "path": node.get("xhttp_path") or "/",
            "mode": node.get("xhttp_mode") or "auto",
        }
    return stream


def build_inbound(node: dict, clients: list[dict]) -> dict:
    transport = (node.get("transport") or "vision").lower()
    return {
        "tag": f"node-{node['id']}",
        "listen": node.get("listen") or "0.0.0.0",
        "port": int(node["port"]),
        "protocol": "vless",
        "settings": {
            "clients": [_client_entry(c, transport) for c in clients],
            "decryption": "none",
        },
        "streamSettings": _stream_settings(node),
        "sniffing": {
            "enabled": True,
            "destOverride": ["http", "tls", "quic"],
            "routeOnly": True,
        },
        # 让 Xray 把 REALITY 回落流量的真实源 IP 交给 nginx（PROXY protocol）
    }


def build_config(nodes: list[dict], clients: list[dict], settings: dict[str, str]) -> dict:
    """组装完整配置。clients 需已按 node_id 分组，且过滤掉禁用项。"""
    by_node: dict[int, list[dict]] = {}
    for client in clients:
        by_node.setdefault(int(client["node_id"]), []).append(client)

    inbounds: list[dict] = []
    api_host, api_port = _api_address(settings)
    inbounds.append(
        {
            "tag": "api",
            "listen": api_host,
            "port": api_port,
            "protocol": "dokodemo-door",
            "settings": {"address": api_host},
        }
    )
    for node in nodes:
        inbounds.append(build_inbound(node, by_node.get(int(node["id"]), [])))

    config: dict[str, Any] = {
        "log": {"loglevel": "warning", "access": "none", "error": ""},
        "api": {
            "tag": "api",
            "services": ["HandlerService", "LoggerService", "StatsService"],
        },
        "stats": {},
        "policy": {
            "levels": {
                str(CLIENT_LEVEL): {"statsUserUplink": True, "statsUserDownlink": True}
            },
            "system": {
                "statsInboundUplink": False,
                "statsInboundDownlink": False,
                "statsOutboundUplink": False,
                "statsOutboundDownlink": False,
            },
        },
        "inbounds": inbounds,
        "outbounds": [
            {"tag": "direct", "protocol": "freedom", "settings": {}},
            {"tag": "blocked", "protocol": "blackhole", "settings": {}},
        ],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {"type": "field", "inboundTag": ["api"], "outboundTag": "api"},
                {"type": "field", "ip": PRIVATE_CIDRS, "outboundTag": "blocked"},
                {"type": "field", "protocol": ["bittorrent"], "outboundTag": "blocked"},
            ],
        },
    }
    return config


class Xray:
    def __init__(self, store: Store):
        self.store = store

    # ------------------------------------------------------------ 路径/命令

    @property
    def settings(self) -> dict[str, str]:
        return self.store.settings()

    def _run(self, args: list[str], timeout: int = 20) -> subprocess.CompletedProcess:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )

    def version(self) -> str:
        binary = self.settings.get("xray_bin") or "xray"
        try:
            proc = self._run([binary, "version"], timeout=8)
        except (OSError, subprocess.SubprocessError):
            return ""
        if proc.returncode != 0:
            return ""
        first = (proc.stdout or proc.stderr or "").strip().splitlines()
        return first[0].strip() if first else ""

    def installed(self) -> bool:
        return bool(self.version())

    def service_active(self) -> bool:
        command = self.settings.get("status_cmd") or "systemctl is-active xray"
        try:
            proc = self._run(shlex.split(command), timeout=8)
        except (OSError, subprocess.SubprocessError, ValueError):
            return False
        return proc.returncode == 0 and "active" in (proc.stdout or "").strip()

    def status(self) -> dict:
        version = self.version()
        return {
            "installed": bool(version),
            "version": version,
            "service_active": self.service_active(),
            "config_path": self.settings.get("xray_config"),
            "config_exists": os.path.exists(self.settings.get("xray_config") or ""),
        }

    # ------------------------------------------------------------ 配置

    def render(self) -> tuple[dict, str]:
        """按数据库当前状态渲染配置对象与 JSON 文本（不落盘）。"""
        store = self.store
        nodes = store.nodes(only_enabled=True)
        clients = [c for c in store.clients() if c.get("enabled") and c.get("sub_enabled", 1)]
        config = build_config(nodes, clients, store.settings())
        return config, json.dumps(config, ensure_ascii=False, indent=2) + "\n"

    def test(self, config_text: str) -> tuple[bool, str]:
        """调用 `xray run -test -c <临时文件>`；未安装 xray 时跳过。"""
        binary = self.settings.get("xray_bin") or "xray"
        fd, tmp = tempfile.mkstemp(prefix="reality-panel-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(config_text)
            proc = self._run([binary, "run", "-test", "-c", tmp], timeout=20)
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"无法执行 xray：{exc}"
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        output = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return proc.returncode == 0, output[-4000:]

    def apply(self) -> dict:
        """渲染 -> 写入 -> 测试 -> 重启。返回给前端展示的结果。"""
        config, text = self.render()
        settings = self.settings
        path = settings.get("xray_config") or "/usr/local/etc/xray/config.json"
        result: dict[str, Any] = {
            "config": config,
            "path": path,
            "warnings": [],
            "tested": False,
            "test_ok": False,
            "test_output": "",
            "restarted": False,
            "restart_output": "",
            "ok": False,
        }

        ok, output = self.test(text)
        if not self.installed():
            result["warnings"].append("未检测到 xray 可执行文件，已跳过配置测试与服务重启。")
            result["test_output"] = "skipped: xray not found"
        else:
            result["tested"] = True
            result["test_ok"] = ok
            result["test_output"] = output
            if not ok:
                result["ok"] = False
                return result

        try:
            atomic_write(path, text, 0o640)
            result["written"] = True
        except OSError as exc:
            result["ok"] = False
            result["warnings"].append(f"写入 {path} 失败：{exc}")
            return result

        if not self.installed():
            result["ok"] = True
            return result

        command = settings.get("restart_cmd") or "sudo -n systemctl restart xray"
        try:
            proc = self._run(shlex.split(command), timeout=40)
            result["restarted"] = proc.returncode == 0
            result["restart_output"] = ((proc.stdout or "") + (proc.stderr or "")).strip()[-2000:]
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            result["restart_output"] = str(exc)
            result["warnings"].append(f"重启命令执行失败：{exc}")
        result["ok"] = result["restarted"]
        if not result["restarted"]:
            result["warnings"].append("配置已写入，但 Xray 重启失败，请查看系统日志。")
        return result

    # ------------------------------------------------------------ 统计

    def stats(self) -> dict[str, dict[str, int]]:
        """通过 Xray API 读取每用户累计流量：{email: {up, down}}。"""
        host, port = _api_address(self.settings)
        binary = self.settings.get("xray_bin") or "xray"
        try:
            proc = self._run(
                [binary, "api", "statsquery", f"--server={host}:{port}", "-pattern", "user>>>"],
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
        result: dict[str, dict[str, int]] = {}
        for item in payload.get("stat") or []:
            name = item.get("name") or ""
            parts = name.split(">>>")
            if len(parts) != 4 or parts[0] != "user":
                continue
            email, _, direction = parts[1], parts[2], parts[3]
            try:
                value = int(item.get("value") or 0)
            except (TypeError, ValueError):
                continue
            slot = result.setdefault(email, {"up": 0, "down": 0})
            if direction == "uplink":
                slot["up"] = value
            elif direction == "downlink":
                slot["down"] = value
        return result

    def collect_stats(self) -> int:
        """把 Xray 的累计计数换算成增量写进数据库，返回本次更新的客户端数。"""
        raw = self.stats()
        updated = 0
        for email, counters in raw.items():
            if not email.startswith("c") or not email[1:].isdigit():
                continue
            client_id = int(email[1:])
            up_delta = self._delta(f"{email}:up", counters.get("up", 0))
            down_delta = self._delta(f"{email}:down", counters.get("down", 0))
            if up_delta or down_delta:
                self.store.add_traffic(client_id, up_delta, down_delta)
                updated += 1
        return updated

    def _delta(self, key: str, raw: int) -> int:
        last = self.store.stat_mark(key)
        # Xray 重启后计数归零：此时 raw < last，增量就是 raw 本身
        delta = raw - last if raw >= last else raw
        self.store.set_stat_mark(key, raw)
        return max(0, delta)

    # ------------------------------------------------------------ 日志

    def log_tail(self, lines: int = 200) -> list[str]:
        from .util import tail_lines

        path = self.settings.get("xray_log") or "/var/log/xray/error.log"
        return tail_lines(path, lines)


def new_node_keys() -> tuple[str, str]:
    """生成 REALITY 密钥对（内置 X25519，无需 xray 二进制）。"""
    return generate_keypair()


def repair_public_key(private_key: str) -> str:
    return public_from_private_b64(private_key)
