"""访问白名单：IP / CIDR 解析与匹配。

只依赖标准库 ipaddress。支持单 IP、IPv4/IPv6 CIDR，
一行一个（也接受逗号、分号分隔）。
"""

from __future__ import annotations

import ipaddress
import re
from functools import lru_cache

_SPLIT = re.compile(r"[\s,;]+")
_LINE_SPLIT = re.compile(r"[\n\r,;]+")


@lru_cache(maxsize=32)
def parse_rules(text: str) -> tuple:
    """把白名单文本解析成网络对象；非法条目抛 ValueError。"""
    rules = []
    for raw in _SPLIT.split(text or ""):
        raw = raw.strip()
        if not raw:
            continue
        rules.append(ipaddress.ip_network(raw, strict=False))
    return tuple(rules)


def normalize(text: str) -> str:
    """校验并整理白名单文本（去重、去空行）。

    非法条目会抛 ValueError，消息里带具体内容，方便前端直接展示。
    """
    seen: set[str] = set()
    lines: list[str] = []
    for raw in _LINE_SPLIT.split(text or ""):
        raw = raw.strip()
        if not raw or raw in seen:
            continue
        ipaddress.ip_network(raw, strict=False)  # 校验，失败直接抛
        seen.add(raw)
        lines.append(raw)
    return "\n".join(lines)


def is_allowed(ip: str, text: str, include_loopback: bool = True) -> bool:
    """判断 ip 是否命中白名单；白名单为空时视为不限制。"""
    rules = parse_rules(text or "")
    if not rules:
        return True
    try:
        addr = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return False
    if include_loopback and addr.is_loopback:
        return True
    return any(addr in network for network in rules if network.version == addr.version)
