"""纯 Python 的 X25519（RFC 7748）。

REALITY 的 privateKey / publicKey 就是 32 字节 X25519 标量与公钥的
base64url（无填充）编码。这里自带实现，面板无需安装 cryptography，
也不需要先有 xray 二进制就能生成密钥对。
"""

from __future__ import annotations

import secrets

from .util import b64url_decode, b64url_encode

P = 2**255 - 19
A24 = 121665
_BASE_POINT = (9).to_bytes(32, "little")


def _clamp(raw: bytes) -> int:
    if len(raw) != 32:
        raise ValueError("X25519 私钥必须是 32 字节")
    buf = bytearray(raw)
    buf[0] &= 248
    buf[31] &= 127
    buf[31] |= 64
    return int.from_bytes(bytes(buf), "little")


def x25519(private: bytes, public: bytes) -> bytes:
    """RFC 7748 的 X25519(k, u)，返回 32 字节共享值。"""
    k = _clamp(private)
    u = int.from_bytes(public, "little") & ((1 << 255) - 1)

    x1 = u
    x2, z2 = 1, 0
    x3, z3 = u, 1
    swap = 0

    for t in range(254, -1, -1):
        kt = (k >> t) & 1
        swap ^= kt
        if swap:
            x2, x3 = x3, x2
            z2, z3 = z3, z2
        swap = kt

        a = (x2 + z2) % P
        aa = a * a % P
        b = (x2 - z2) % P
        bb = b * b % P
        e = (aa - bb) % P
        c = (x3 + z3) % P
        d = (x3 - z3) % P
        da = d * a % P
        cb = c * b % P
        x3 = pow(da + cb, 2, P)
        z3 = x1 * pow(da - cb, 2, P) % P
        x2 = aa * bb % P
        z2 = e * (aa + A24 * e) % P

    if swap:
        x2, x3 = x3, x2
        z2, z3 = z3, z2

    return (x2 * pow(z2, P - 2, P) % P).to_bytes(32, "little")


def public_from_private(private: bytes) -> bytes:
    return x25519(private, _BASE_POINT)


def generate_keypair() -> tuple[str, str]:
    """返回 (privateKey, publicKey)，均为 base64url 无填充字符串。"""
    raw = secrets.token_bytes(32)
    pub = public_from_private(raw)
    return b64url_encode(raw), b64url_encode(pub)


def public_from_private_b64(private_b64: str) -> str:
    """由已保存的私钥重新推导公钥（用于校验/修复数据）。"""
    return b64url_encode(public_from_private(b64url_decode(private_b64)))
