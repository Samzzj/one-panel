"""HTTP 层：极简路由 + 静态资源 + 会话/CSRF 校验。

只依赖标准库，目标是「扔到任何一台有 python3 的机器上就能跑」。
"""

from __future__ import annotations

import json
import re
import time
import traceback
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlsplit

MAX_BODY = 1 * 1024 * 1024
WEB_DIR = Path(__file__).parent / "web"
COOKIE_NAME = "rp_session"

ASSETS = {
    "app.js": "application/javascript; charset=utf-8",
    "theme.js": "application/javascript; charset=utf-8",
    "qrcode.js": "application/javascript; charset=utf-8",
    "style.css": "text/css; charset=utf-8",
    "favicon.svg": "image/svg+xml",
    "index.html": "text/html; charset=utf-8",
}

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    ),
}

FORBIDDEN_PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>403 · 访问受限</title></head>
<body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#080a0f;
color:#e8ecf5;font:14px/1.7 -apple-system,'Segoe UI','Microsoft YaHei',sans-serif">
<div style="max-width:520px;padding:32px">
  <div style="font-size:13px;letter-spacing:2px;color:#8a93a8">REALITY PANEL</div>
  <h1 style="font-size:22px;margin:8px 0 12px">403 · 当前 IP 不在访问白名单内</h1>
  <p style="color:#8a93a8;margin:0 0 14px">面板开启了 IP 白名单。如果你确信应该能访问，请在服务器上执行：</p>
  <pre style="background:#11151e;border:1px solid #1e2532;border-radius:10px;padding:12px 14px;
overflow:auto;color:#c9d4ea">python3 app.py allow 你的公网IP</pre>
</div></body></html>
"""


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, str]
    headers: dict[str, str]
    body: bytes
    cookies: dict[str, str]
    client_ip: str
    session: dict | None = None
    user: dict | None = None

    def json(self) -> dict:
        if not self.body:
            return {}
        try:
            data = json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(400, "请求体不是合法 JSON")
        if not isinstance(data, dict):
            raise ApiError(400, "请求体必须是 JSON 对象")
        return data


@dataclass
class Response:
    status: int = 200
    body: bytes = b""
    content_type: str = "application/json; charset=utf-8"
    headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def json(cls, data: Any, status: int = 200) -> "Response":
        return cls(
            status=status,
            body=json.dumps(data, ensure_ascii=False).encode("utf-8"),
            content_type="application/json; charset=utf-8",
        )

    @classmethod
    def text(cls, text: str, status: int = 200, content_type: str = "text/plain; charset=utf-8") -> "Response":
        return cls(status=status, body=text.encode("utf-8"), content_type=content_type)


class Router:
    def __init__(self) -> None:
        self.routes: list[tuple[str, re.Pattern[str], Callable, dict]] = []

    def add(
        self,
        method: str,
        pattern: str,
        func: Callable,
        auth: bool = True,
        csrf: bool = True,
    ) -> None:
        self.routes.append((method.upper(), re.compile(f"^{pattern}$"), func, {"auth": auth, "csrf": csrf}))

    def match(self, method: str, path: str):
        for route_method, regex, func, meta in self.routes:
            if route_method != method.upper():
                continue
            found = regex.match(path)
            if found:
                return func, found.groupdict(), meta
        return None


class PanelHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], app: Any):
        super().__init__(address, Handler)
        self.app = app


class Handler(BaseHTTPRequestHandler):
    server_version = "RealityPanel"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # --------------------------------------------------------- 入口

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    def do_HEAD(self) -> None:  # noqa: N802
        self._dispatch("HEAD")

    def handle_one_request(self) -> None:
        # 客户端/探针经常在握手后直接断开，不要把 ConnectionReset 变成堆栈噪音
        try:
            super().handle_one_request()
        except (ConnectionResetError, BrokenPipeError, TimeoutError):
            self.close_connection = True

    # --------------------------------------------------------- 分发

    def _client_ip(self) -> str:
        # 默认只信任本机反代；面板建议用 SSH 隧道访问
        if self.client_address[0] in ("127.0.0.1", "::1"):
            cf = (self.headers.get("CF-Connecting-IP") or "").strip()
            if cf:
                return cf
            forwarded = self.headers.get("X-Forwarded-For", "")
            if forwarded:
                return forwarded.split(",")[0].strip()
            real = (self.headers.get("X-Real-IP") or "").strip()
            if real:
                return real
        return self.client_address[0]

    def _read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > MAX_BODY:
            raise ApiError(413, "请求体过大")
        return self.rfile.read(length) if length > 0 else b""

    def _cookies(self) -> dict[str, str]:
        raw = self.headers.get("Cookie") or ""
        jar = SimpleCookie()
        try:
            jar.load(raw)
        except Exception:  # noqa: BLE001 - 恶意 cookie 不应导致 500
            return {}
        return {key: morsel.value for key, morsel in jar.items()}

    def _dispatch(self, method: str) -> None:
        started = time.time()
        app = self.server.app  # type: ignore[attr-defined]
        try:
            parts = urlsplit(self.path)
            path = unquote(parts.path)
            if len(path) > 1:
                path = path.rstrip("/") or "/"
            query = {k: v[0] for k, v in parse_qs(parts.query).items()}

            # 白名单要在读 body / 查会话之前判断，避免被拦的请求还消耗资源
            if app.access_blocked(self._client_ip(), path):
                if path.startswith("/api/"):
                    blocked = Response.json({"error": "当前 IP 不在访问白名单内"}, 403)
                else:
                    blocked = Response.text(FORBIDDEN_PAGE, 403, "text/html; charset=utf-8")
                self._send(blocked, method)
                return

            body = self._read_body()
            cookies = self._cookies()
            request = Request(
                method=method,
                path=path,
                query=query,
                headers={k.lower(): v for k, v in self.headers.items()},
                body=body,
                cookies=cookies,
                client_ip=self._client_ip(),
            )

            token = cookies.get(COOKIE_NAME, "")
            session = app.store.session(token) if token else None
            if session:
                request.session = session
                request.user = app.store.user_by_id(session["user_id"])
                if not request.user:
                    app.store.drop_session(token)

            matched = app.router.match(method if method != "HEAD" else "GET", path)
            if not matched:
                if path.startswith("/api/"):
                    response = Response.json({"error": "接口不存在"}, 404)
                else:
                    response = self._static(path)
            else:
                func, params, meta = matched
                if meta["auth"] and not request.user:
                    raise ApiError(401, "请先登录")
                # CSRF 只对写操作生效；GET 不应要求额外头
                if meta["csrf"] and request.session and method.upper() in ("POST", "PATCH", "PUT", "DELETE"):
                    sent = request.headers.get("x-csrf-token", "")
                    if not sent or sent != request.session["csrf"]:
                        raise ApiError(403, "CSRF 校验失败，请刷新页面")
                result = func(app, request, **params)
                response = result if isinstance(result, Response) else Response.json(result)

            self._send(response, method)
        except ApiError as exc:
            self._send(Response.json({"error": exc.message}, exc.status), method)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._send(Response.json({"error": "服务器内部错误"}, 500), method)
        finally:
            app.log_request(method, self.path, getattr(self, "_last_status", 0), time.time() - started)

    def _static(self, path: str) -> Response:
        name = path.lstrip("/")
        if name in ("", "index.html"):
            key = "index.html"
        elif name == "favicon.svg":
            key = "favicon.svg"
        elif name.startswith("assets/"):
            key = name[len("assets/") :]
        else:
            # SPA 前端使用 hash 路由，未知路径回到首页
            key = "index.html" if not name.startswith("api/") else ""

        if not key or key not in ASSETS or "/" in key:
            raise ApiError(404, "资源不存在")

        file_path = WEB_DIR / key
        try:
            data = file_path.read_bytes()
        except OSError:
            raise ApiError(404, "资源不存在")
        return Response(body=data, status=200, content_type=ASSETS[key])

    def _send(self, response: Response, method: str = "GET") -> None:
        self._last_status = response.status
        body = response.body
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.end_headers()
        if method != "HEAD" and body:
            self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        # 由 app.log_request 统一记录，避免默认日志刷屏
        return

    def version_string(self) -> str:
        return "RealityPanel"


def build_server(host: str, port: int, app: Any) -> PanelHTTPServer:
    return PanelHTTPServer((host, port), app)


def serve_forever(server: PanelHTTPServer) -> None:
    print(f"[panel] 监听 http://{server.server_address[0]}:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[panel] 收到中断，退出", flush=True)
    finally:
        server.server_close()
