"""分享链接与订阅生成。

输出三种格式：
1. vless:// URI      —— v2rayN / v2rayNG / NekoBox / sing-box 等
2. Base64 订阅       —— 标准 v2ray 订阅，换行分隔的 URI 列表
3. Clash / mihomo YAML —— 仅 mihomo（Clash.Meta）支持 REALITY
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

from urllib.parse import quote, urlencode

# 客户端可选的 uTLS 指纹
FINGERPRINTS = ["chrome", "firefox", "safari", "ios", "android", "edge", "360", "qq", "random"]
XHTTP_MODES = ["auto", "packet-up", "stream-up", "stream-one"]


def _short_ids(node: dict) -> list[str]:
    value = node.get("short_ids") or []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = []
    return [str(v) for v in value] or [""]


def _host_port(host: str, port: int) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]:{port}"
    return f"{host}:{port}"


def node_endpoint(node: dict) -> tuple[str, int]:
    return str(node.get("sni") or ""), int(node.get("port") or 443)


def vless_link(node: dict, uuid: str, remark: str, host: str) -> str:
    """生成一条 vless:// 分享链接。"""
    transport = (node.get("transport") or "vision").lower()
    fingerprint = node.get("fingerprint") or "chrome"
    short_id = _short_ids(node)[0]

    params: list[tuple[str, str]] = [
        ("encryption", "none"),
        ("security", "reality"),
        ("sni", str(node.get("sni") or "")),
        ("fp", str(fingerprint)),
        ("pbk", str(node.get("public_key") or "")),
        ("sid", short_id),
    ]

    if transport == "xhttp":
        path = str(node.get("xhttp_path") or "/")
        params += [
            ("type", "xhttp"),
            ("path", path),
            ("mode", str(node.get("xhttp_mode") or "auto")),
            ("host", str(node.get("sni") or "")),
        ]
    else:
        params += [
            ("type", "tcp"),
            ("headerType", "none"),
            ("flow", "xtls-rprx-vision"),
            ("spx", "/"),
        ]

    query = urlencode(params, quote_via=quote, safe="")
    authority = _host_port(host, int(node.get("port") or 443))
    return f"vless://{uuid}@{authority}?{query}#{quote(remark, safe='')}"


def clash_proxy(node: dict, uuid: str, remark: str, host: str) -> dict[str, Any]:
    """生成 Clash / mihomo 的 proxies 条目。"""
    transport = (node.get("transport") or "vision").lower()
    proxy: dict[str, Any] = {
        "name": remark,
        "type": "vless",
        "server": host,
        "port": int(node.get("port") or 443),
        "uuid": uuid,
        "udp": True,
        "tls": True,
        "servername": str(node.get("sni") or ""),
        "client-fingerprint": node.get("fingerprint") or "chrome",
        "reality-opts": {
            "public-key": str(node.get("public_key") or ""),
            "short-id": _short_ids(node)[0],
            # Xray 26.9+ 的 REALITY 默认使用 X25519MLKEM768；mihomo 必须显式开启，
            # 否则会报 "REALITY authentication failed"，但回落 curl 仍然正常。
            "support-x25519mlkem768": True,
        },
    }
    if transport == "xhttp":
        proxy["network"] = "xhttp"
        proxy["xhttp-opts"] = {
            "path": str(node.get("xhttp_path") or "/"),
            "mode": str(node.get("xhttp_mode") or "auto"),
        }
    else:
        proxy["network"] = "tcp"
        proxy["flow"] = "xtls-rprx-vision"
    return proxy


# ------------------------------------------------------------------ YAML

_PLAIN_KEY = re.compile(r"^[A-Za-z0-9_.-]+$")
_PLAIN_VALUE = re.compile(r"^[A-Za-z0-9_./:@+-]+$")


def _yaml_key(key: str) -> str:
    key = str(key)
    return key if _PLAIN_KEY.match(key) else json.dumps(key, ensure_ascii=False)


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return "null"
    text = str(value)
    if text and _PLAIN_VALUE.match(text) and not text.startswith(("-", ":")):
        return text
    return json.dumps(text, ensure_ascii=False)


def _yaml_lines(obj: Any, indent: int) -> list[str]:
    pad = "  " * indent
    lines: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            name = _yaml_key(key)
            if isinstance(value, dict):
                if value:
                    lines.append(f"{pad}{name}:")
                    lines.extend(_yaml_lines(value, indent + 1))
                else:
                    lines.append(f"{pad}{name}: {{}}")
            elif isinstance(value, list):
                if value:
                    lines.append(f"{pad}{name}:")
                    lines.extend(_yaml_lines(value, indent + 1))
                else:
                    lines.append(f"{pad}{name}: []")
            else:
                lines.append(f"{pad}{name}: {_yaml_scalar(value)}")
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                if not item:
                    lines.append(f"{pad}- {{}}")
                    continue
                block = _yaml_lines(item, indent + 1)
                block[0] = f"{pad}- {block[0].lstrip()}"
                lines.extend(block)
            elif isinstance(item, list):
                lines.append(f"{pad}-")
                lines.extend(_yaml_lines(item, indent + 1))
            else:
                lines.append(f"{pad}- {_yaml_scalar(item)}")
    return lines


def clash_config(proxies: list[dict], panel_name: str = "Reality Panel") -> str:
    """生成一份可直接导入 mihomo 的完整配置。"""
    names = [str(p["name"]) for p in proxies]
    doc: dict[str, Any] = {
        "mixed-port": 7890,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "warning",
        "external-controller": "127.0.0.1:9090",
        "proxies": proxies,
        "proxy-groups": [
            {
                "name": "PROXY",
                "type": "select",
                "proxies": names + ["DIRECT"] if names else ["DIRECT"],
            }
        ],
        "rules": [
            "GEOIP,LAN,DIRECT,no-resolve",
            "GEOIP,CN,DIRECT",
            "MATCH,PROXY",
        ],
    }
    head = [
        f"# {panel_name} - Clash / mihomo 订阅",
        "# 需要 mihomo 内核（Clash.Meta），原版 Clash 不支持 REALITY",
        "# 生成时间仅代表配置快照，节点变更后请重新拉取订阅",
        "",
    ]
    return "\n".join(head + _yaml_lines(doc, 0)) + "\n"


def subscription_payload(links: list[str]) -> str:
    """v2rayN 标准订阅：URI 换行拼接后整体 base64。"""
    raw = "\n".join(links).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def build_links(sub: dict, host: str) -> list[str]:
    """按 sub_by_token() 的结果生成全部节点链接。

    每台服务器用自己的公网地址（server_address），所以多机订阅里
    同一个用户在不同机器上的链接会自动指向对应机器。
    """
    links: list[str] = []
    for client in sub.get("clients", []):
        if not client.get("node_enabled") or not client.get("enabled"):
            continue
        if client.get("server_enabled") is not None and not client.get("server_enabled"):
            continue
        node = {
            "transport": client.get("transport"),
            "port": client.get("port"),
            "sni": client.get("sni"),
            "public_key": client.get("public_key"),
            "short_ids": client.get("short_ids"),
            "xhttp_path": client.get("xhttp_path"),
            "xhttp_mode": client.get("xhttp_mode"),
            "fingerprint": client.get("fingerprint"),
        }
        remark = f"{sub['name']}-{client.get('node_name')}"
        node_host = (client.get("server_address") or "").strip() or host
        links.append(vless_link(node, client["uuid"], remark, node_host))
    return links


def build_clash_proxies(sub: dict, host: str) -> list[dict]:
    proxies: list[dict] = []
    for client in sub.get("clients", []):
        if not client.get("node_enabled") or not client.get("enabled"):
            continue
        if client.get("server_enabled") is not None and not client.get("server_enabled"):
            continue
        node = {
            "transport": client.get("transport"),
            "port": client.get("port"),
            "sni": client.get("sni"),
            "public_key": client.get("public_key"),
            "short_ids": client.get("short_ids"),
            "xhttp_path": client.get("xhttp_path"),
            "xhttp_mode": client.get("xhttp_mode"),
            "fingerprint": client.get("fingerprint"),
        }
        node_host = (client.get("server_address") or "").strip() or host
        proxies.append(clash_proxy(node, client["uuid"], f"{sub['name']}-{client.get('node_name')}", node_host))
    return proxies
