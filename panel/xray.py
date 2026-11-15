"""Xray 配置生成、进程控制与流量统计。

生成的是完整 server 配置：REALITY 入站 + 本地 API 入站 + 路由 + 出站。
面板不直接持有 Xray 进程，只负责写配置、测试、调用 systemctl 重启，
这样 Xray 由 systemd 托管，面板重启不会断线。
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
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


def _log_target(settings: dict[str, str]) -> str:
    """决定 Xray 的 error 日志写到哪。

    `xray run -test` 会真的去初始化 logger：目录不存在或当前用户写不了，
    测试直接失败、配置永远下发不了（真机上踩过）。所以只有确认目录存在且
    可写时才用文件，否则退回 stderr（journald），由日志页回退读 journal。
    """
    path = (settings.get("xray_log") or "").strip()
    if not path:
        return ""
    directory = os.path.dirname(path) or "."
    if os.path.isdir(directory) and os.access(directory, os.W_OK):
        return path
    return ""


def _api_address(settings: dict[str, str]) -> tuple[str, int]:
    raw = (settings.get("xray_api") or "127.0.0.1:10085").strip()
    host, _, port = raw.rpartition(":")
    if not host:
        return "127.0.0.1", 10085
    # 设置页允许手填，[::1]:10085 这种带方括号的写法要剥掉，
    # 否则 listen 会变成 "[::1]"、statquery 也会拼错，统计静默归零。
    host = host.strip("[]")
    try:
        return host, int(port)
    except ValueError:
        return "127.0.0.1", 10085


def _snapshot(path: str) -> str | None:
    """把现有配置复制一份到同目录，返回快照路径；没有旧配置时返回 None。"""
    if not path or not os.path.exists(path):
        return None
    backup = f"{path}.panel-bak"
    try:
        shutil.copy2(path, backup)
        return backup
    except OSError:
        return None


def _restore(path: str, backup: str | None) -> bool:
    """用快照覆盖回配置；成功返回 True。"""
    if not backup or not os.path.exists(backup):
        return False
    try:
        shutil.copy2(backup, path)
        return True
    except OSError:
        return False


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
        # 目录不可写时退回 ""（stderr / journald），绝不能因为日志路径把配置写死
        "log": {
            "loglevel": "warning",
            "access": "none",
            "error": _log_target(settings),
        },
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

    def render(self, server_id: int | None = None) -> tuple[dict, str]:
        """按数据库当前状态渲染某台服务器的配置对象与 JSON 文本（不落盘）。"""
        store = self.store
        nodes = store.nodes(only_enabled=True, server_id=server_id)
        node_ids = {int(node["id"]) for node in nodes}
        clients = [
            client
            for client in store.clients()
            if client.get("enabled")
            and client.get("sub_enabled", 1)
            and int(client["node_id"]) in node_ids
        ]
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

    def apply(self, server_id: int = 1) -> dict:
        """渲染 -> 写入 -> 测试 -> 重启。返回给前端展示的结果。"""
        config, text = self.render(server_id)
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
            "backup": None,
            "rolled_back": False,
            "rolled_back_restarted": False,
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

        # `xray run -test` 只校验 JSON，不会真的 bind 端口：
        # 端口撞上 nginx 回落 / 面板 / Xray API 时，只有重启这一步才会失败。
        # 所以写盘前必须先留一份快照，失败时能退回上一份，否则新配置会把
        # 唯一一份能用的配置覆盖掉，用户从此一直掉线。
        backup = _snapshot(path)
        result["backup"] = backup

        try:
            # Xray 官方 systemd 服务以 nobody 运行，配置必须对其他用户可读
            atomic_write(path, text, 0o644)
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
            if _restore(path, backup):
                result["rolled_back"] = True
                result["warnings"].append(
                    "新配置重启失败，已回滚到上一份配置；请检查节点端口是否与 "
                    "nginx 回落端口 / 面板端口 / Xray API 端口冲突。"
                )
                try:
                    retry = self._run(shlex.split(command), timeout=40)
                    result["rolled_back_restarted"] = retry.returncode == 0
                    if not result["rolled_back_restarted"]:
                        result["warnings"].append("回滚后 Xray 仍无法启动，请立即查看系统日志。")
                except (OSError, subprocess.SubprocessError, ValueError) as exc:
                    result["warnings"].append(f"回滚后重启命令执行失败：{exc}")
            else:
                result["warnings"].append(
                    "配置已写入，但 Xray 重启失败，而且没有找到可回滚的旧配置。"
                )
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
        """本机：把 Xray 的累计计数换算成增量写进数据库。"""
        return self.collect_from(self.stats())

    def collect_from(self, raw: dict[str, dict[str, int]]) -> int:
        """把任意节点的 {email: {up, down}} 计数换算成增量。"""
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

        path = self.settings.get("xray_log") or ""
        if path:
            rows = tail_lines(path, lines)
            if rows:
                return rows
        # 文件不存在（正常，日志可能写在 journald 里）就回退读 journal，
        # 面板服务在 install.sh 里加了 systemd-journal 组
        service = self.settings.get("xray_service") or "xray"
        try:
            proc = self._run(
                ["journalctl", "-u", service, "-n", str(max(1, min(int(lines), 5000))), "--no-pager", "-o", "cat"],
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if proc.returncode != 0:
            return []
        return (proc.stdout or "").splitlines()[-lines:]


def new_node_keys() -> tuple[str, str]:
    """生成 REALITY 密钥对（内置 X25519，无需 xray 二进制）。"""
    return generate_keypair()


def repair_public_key(private_key: str) -> str:
    return public_from_private_b64(private_key)
