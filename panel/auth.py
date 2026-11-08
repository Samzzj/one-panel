"""认证：密码哈希、登录限流。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time

ALGO = "pbkdf2_sha256"
ITERATIONS = 260_000
SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return "$".join(
        [
            ALGO,
            str(ITERATIONS),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_b64, digest_b64 = stored.split("$")
        if algo != ALGO:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def password_problem(password: str) -> str:
    """返回不满足要求的原因，空字符串表示通过。"""
    if len(password) < 10:
        return "密码至少 10 位"
    if password.isdigit():
        return "密码不能全是数字"
    return ""


class LoginLimiter:
    """按来源 IP 限制登录失败次数，纯内存即可（单进程部署）。"""

    def __init__(self, limit: int = 6, window: int = 300):
        self.limit = limit
        self.window = window
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now_ts: float) -> list[float]:
        hits = [t for t in self._hits.get(key, []) if now_ts - t < self.window]
        if hits:
            self._hits[key] = hits
        else:
            self._hits.pop(key, None)
        return hits

    def blocked(self, key: str) -> int:
        """返回剩余封禁秒数，0 表示未封禁。"""
        with self._lock:
            hits = self._prune(key, time.time())
            if len(hits) >= self.limit:
                return max(1, int(self.window - (time.time() - hits[0])))
            return 0

    def fail(self, key: str) -> None:
        with self._lock:
            now_ts = time.time()
            hits = self._prune(key, now_ts)
            hits.append(now_ts)
            self._hits[key] = hits

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)
