"""通用小工具：时间、随机串、原子写文件、字节/时间格式化。"""

from __future__ import annotations

import base64
import json
import os
import secrets
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------- 时间


def now() -> int:
    """当前 Unix 时间戳（秒）。"""
    return int(time.time())


def days_from_now(days: int) -> int:
    return now() + int(days) * 86400


def fmt_time(ts: int | None) -> str:
    """时间戳 -> 本地可读时间；0/None 表示永不过期。"""
    if not ts:
        return "永久"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(int(ts)))


def fmt_bytes(n: int | float | None) -> str:
    """字节数 -> 人类可读。"""
    n = float(n or 0)
    if n < 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if n < 1024 or unit == "PB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"


# ---------------------------------------------------------------- 随机


def rand_token(nbytes: int = 24) -> str:
    """URL 安全的随机 token。"""
    return secrets.token_urlsafe(nbytes)


def rand_hex(nbytes: int = 8) -> str:
    """随机十六进制串（REALITY shortId 常用 8 字节 -> 16 字符）。"""
    return secrets.token_hex(nbytes)


def new_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------- 编码


def b64url_encode(raw: bytes) -> str:
    """无填充 base64url，REALITY 密钥使用的格式。"""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64url_decode(text: str) -> bytes:
    text = (text or "").strip()
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------- 文件


def atomic_write(path: str | os.PathLike[str], text: str, mode: int = 0o600) -> None:
    """原子写文件：先写同目录临时文件，再 os.replace 覆盖。

    避免 Xray 读到写了一半的配置。
    """
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
            pass  # Windows 上 chmod 语义有限
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_text(path: str | os.PathLike[str], default: str = "") -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return default


def tail_lines(path: str | os.PathLike[str], limit: int = 200) -> list[str]:
    """读取文件末尾若干行（日志用），大文件也不会整个读入。"""
    limit = max(1, min(int(limit), 5000))
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            block = min(size, 256 * 1024)
            fh.seek(size - block)
            data = fh.read().decode("utf-8", "replace")
    except OSError:
        return []
    lines = data.splitlines()
    return lines[-limit:]
