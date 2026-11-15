"""主控到节点 agent 的 HTTP / HTTPS 客户端。

HTTPS 走证书指纹固定（pinning）：节点用的是自签证书，面板不靠 CA 链，
而是把第一次连接拿到的证书 SHA256 记在 servers.agent_cert 里，
之后每次连接都要求指纹完全一致——中间人换证书会直接握手失败。
"""

from __future__ import annotations

import hashlib
import http.client
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request


def fingerprint_of(cert_der: bytes) -> str:
    """证书 DER 的 SHA256（小写 hex），和 `openssl x509 -fingerprint -sha256` 对应。"""
    return hashlib.sha256(cert_der or b"").hexdigest()


def _split_url(base: str) -> tuple[str, str, int, bool]:
    parsed = urllib.parse.urlsplit(base)
    scheme = (parsed.scheme or "http").lower()
    host = parsed.hostname or ""
    port = parsed.port or (8787 if scheme == "http" else 8787)
    return scheme, host, port, scheme == "https"


class _PinnedConnection(http.client.HTTPSConnection):
    """握手后校验证书指纹，不一致直接断开。"""

    def __init__(self, *args, pin: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self._pin = pin

    def connect(self) -> None:
        super().connect()
        der = self.sock.getpeercert(binary_form=True) if self.sock else b""
        got = fingerprint_of(der or b"")
        if not self._pin:
            self.close()
            raise ssl.SSLError("节点要求 HTTPS，但面板还没有记录它的证书指纹，请先点「测试」")
        if got != self._pin:
            self.close()
            raise ssl.SSLError(
                f"节点证书指纹不匹配（期望 {self._pin[:16]}…，实际 {got[:16]}…）；"
                "如果确实重装过 agent，请在服务器上点「测试」重新信任"
            )


class _PinnedHandler(urllib.request.HTTPSHandler):
    def __init__(self, pin: str):
        super().__init__(context=_unverified_context())
        self._pin = pin

    def https_open(self, req):  # noqa: N802
        return self.do_open(lambda *a, **kw: _PinnedConnection(*a, pin=self._pin, **kw), req)


def _unverified_context() -> ssl.SSLContext:
    # 刻意不做 CA 校验：节点是自签证书，安全性来自指纹固定而不是 CA
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


class AgentClient:
    def __init__(self, server: dict):
        self.base = (server.get("agent_url") or "").rstrip("/")
        self.token = server.get("token") or ""
        self.pin = (server.get("agent_cert") or "").strip().lower()
        self.scheme, self.host, self.port, self.tls = _split_url(self.base) if self.base else ("http", "", 0, False)

    # ------------------------------------------------------------ 证书

    def probe_fingerprint(self, timeout: int = 10) -> str:
        """连一次拿节点证书的 SHA256；连不上抛 OSError。"""
        if not self.tls or not self.host:
            return ""
        context = _unverified_context()
        with socket_create(self.host, self.port, timeout) as raw:
            with context.wrap_socket(raw, server_hostname=None) as tls:
                return fingerprint_of(tls.getpeercert(binary_form=True) or b"")

    # ------------------------------------------------------------ 请求

    def _opener(self):
        if self.tls:
            return urllib.request.build_opener(_PinnedHandler(self.pin))
        return urllib.request.build_opener()

    def _call(self, method: str, path: str, payload: dict | None = None, timeout: int = 30) -> dict:
        if not self.base:
            return {"ok": False, "error": "该服务器还没有配置 agent 地址"}
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={
                "X-Agent-Token": self.token,
                "Content-Type": "application/json",
                "User-Agent": "one-panel-master",
            },
        )
        try:
            with self._opener().open(request, timeout=timeout) as response:
                raw = response.read()
                result = json.loads(raw or b"{}")
                if isinstance(result, dict):
                    result.setdefault("ok", True)
                    return result
                return {"ok": False, "error": "节点返回了非对象 JSON"}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                body = {}
            return {
                "ok": False,
                "error": body.get("error") or f"节点返回 HTTP {exc.code}",
                "status": exc.code,
            }
        except ssl.SSLError as exc:
            return {"ok": False, "error": f"TLS 校验失败：{exc}"}
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, ssl.SSLError):
                return {"ok": False, "error": f"TLS 校验失败：{reason}"}
            return {"ok": False, "error": f"连接节点失败：{exc}"}

    def health(self) -> dict:
        return self._call("GET", "/health", timeout=10)

    def apply(self, config: dict) -> dict:
        return self._call("POST", "/apply", {"config": config}, timeout=60)

    def stats(self) -> dict:
        return self._call("GET", "/stats", timeout=20)

    def nginx(self, conf: str, path: str) -> dict:
        return self._call("POST", "/nginx", {"conf": conf, "path": path}, timeout=40)

    def selfsteal(self, domain: str, conf: str, path: str, cert_dir: str, email: str = "") -> dict:
        return self._call(
            "POST",
            "/selfsteal",
            {"domain": domain, "conf": conf, "path": path, "cert_dir": cert_dir, "email": email},
            timeout=300,
        )


def socket_create(host: str, port: int, timeout: int):
    import socket

    return socket.create_connection((host, port), timeout=timeout)
