"""JSON API 与订阅端点。"""

from __future__ import annotations

import json
import re
from typing import Any

from . import __version__
from .access import is_allowed, normalize
from .auth import hash_password, password_problem, verify_password
from .db import DEFAULT_SETTINGS
from .httpd import COOKIE_NAME, ApiError, Request, Response, Router
from .links import (
    FINGERPRINTS,
    XHTTP_MODES,
    build_clash_proxies,
    build_links,
    clash_config,
    subscription_payload,
)
from .nginx import plan as nginx_plan
from .nginx import valid_domain, valid_hostport
from .util import now, rand_hex, rand_token
from .xray import new_node_keys

SESSION_TTL = 7 * 86400
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
SHORT_ID_RE = re.compile(r"^[0-9a-fA-F]{0,16}$")
XHTTP_PATH_RE = re.compile(r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/-]{0,120}$")


# ---------------------------------------------------------------- 工具


def _secure(req: Request) -> bool:
    return (req.headers.get("x-forwarded-proto") or "").lower() == "https"


def _set_cookie(resp: Response, token: str, secure: bool, max_age: int = SESSION_TTL) -> None:
    parts = [f"{COOKIE_NAME}={token}", "Path=/", "HttpOnly", "SameSite=Lax", f"Max-Age={max_age}"]
    if secure:
        parts.append("Secure")
    resp.headers["Set-Cookie"] = "; ".join(parts)


def _public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "username": user["username"],
        "last_login_at": user.get("last_login_at") or 0,
    }


def _text(data: dict, key: str, label: str, *, maxlen: int = 64, default: str | None = None) -> str:
    if key not in data or data[key] is None:
        if default is None:
            raise ApiError(400, f"{label}不能为空")
        return default
    value = data[key]
    if not isinstance(value, str):
        raise ApiError(400, f"{label}必须是字符串")
    value = value.strip()
    if not value:
        if default is None:
            raise ApiError(400, f"{label}不能为空")
        return default
    if len(value) > maxlen:
        raise ApiError(400, f"{label}不能超过 {maxlen} 个字符")
    return value


def _number(data: dict, key: str, label: str, *, default: int, minimum: int, maximum: int) -> int:
    if key not in data or data[key] in (None, ""):
        return default
    try:
        value = int(data[key])
    except (TypeError, ValueError):
        raise ApiError(400, f"{label}必须是整数")
    if value < minimum or value > maximum:
        raise ApiError(400, f"{label}必须在 {minimum} 到 {maximum} 之间")
    return value


def _ids(value: Any, label: str) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ApiError(400, f"{label}必须是数组")
    result: list[int] = []
    for item in value:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            raise ApiError(400, f"{label}包含非法 ID")
    return result


def _short_ids(value: Any) -> list[str]:
    if not value:
        # 空值表示让面板生成一个随机 shortId（比留空更安全）
        return [rand_hex(8)]
    if not isinstance(value, list):
        raise ApiError(400, "shortId 必须是数组")
    cleaned: list[str] = []
    for item in value:
        item = str(item).strip()
        if not SHORT_ID_RE.match(item) or len(item) % 2 != 0:
            raise ApiError(400, "shortId 只能是最多 16 位的偶数长度十六进制串")
        cleaned.append(item)
    if len(cleaned) > 8:
        raise ApiError(400, "shortId 最多 8 个")
    return cleaned or [rand_hex(8)]


def _node_payload(data: dict, *, partial: bool = False) -> dict:
    payload: dict[str, Any] = {}
    if not partial or "name" in data:
        payload["name"] = _text(data, "name", "节点名称", maxlen=48)
    if not partial or "transport" in data:
        transport = _text(data, "transport", "传输方式", maxlen=16, default="vision")
        if transport not in ("vision", "xhttp"):
            raise ApiError(400, "传输方式只能是 vision 或 xhttp")
        payload["transport"] = transport
    if not partial or "port" in data:
        payload["port"] = _number(data, "port", "端口", default=443, minimum=1, maximum=65535)
    if not partial or "sni" in data:
        sni = _text(data, "sni", "SNI 域名", maxlen=253)
        if not valid_domain(sni):
            raise ApiError(400, "SNI 必须是合法域名，例如 node.example.com")
        payload["sni"] = sni
    if not partial or "dest" in data:
        dest = _text(data, "dest", "回落地址", maxlen=64, default="127.0.0.1:8003")
        if not valid_hostport(dest):
            raise ApiError(400, "回落地址格式应为 host:port，例如 127.0.0.1:8003")
        payload["dest"] = dest
    if not partial or "xver" in data:
        payload["xver"] = _number(data, "xver", "PROXY protocol 版本", default=1, minimum=0, maximum=2)
    if not partial or "short_ids" in data:
        payload["short_ids"] = _short_ids(data.get("short_ids"))
    if not partial or "xhttp_path" in data:
        default_path = "/"
        if payload.get("transport") == "xhttp" and "xhttp_path" not in data:
            # XHTTP 路径相当于一个弱口令，默认随机化，避免被按路径扫
            default_path = "/" + rand_hex(6)
        path = _text(data, "xhttp_path", "XHTTP 路径", maxlen=128, default=default_path)
        if not XHTTP_PATH_RE.match(path):
            raise ApiError(400, "XHTTP 路径必须以 / 开头，且不能包含空格")
        payload["xhttp_path"] = path
    if not partial or "xhttp_mode" in data:
        mode = _text(data, "xhttp_mode", "XHTTP 模式", maxlen=16, default="auto")
        if mode not in XHTTP_MODES:
            raise ApiError(400, f"XHTTP 模式只能是 {', '.join(XHTTP_MODES)}")
        payload["xhttp_mode"] = mode
    if not partial or "fingerprint" in data:
        fingerprint = _text(data, "fingerprint", "uTLS 指纹", maxlen=16, default="chrome")
        if fingerprint not in FINGERPRINTS:
            raise ApiError(400, "不支持的 uTLS 指纹")
        payload["fingerprint"] = fingerprint
    if not partial or "remark" in data:
        payload["remark"] = _text(data, "remark", "备注", maxlen=120, default="")
    if "enabled" in data:
        payload["enabled"] = bool(data.get("enabled"))
    elif not partial:
        payload["enabled"] = True
    return payload


def _sub_payload(data: dict, *, partial: bool = False) -> dict:
    payload: dict[str, Any] = {}
    if not partial or "name" in data:
        payload["name"] = _text(data, "name", "订阅名称", maxlen=48)
    if "enabled" in data:
        payload["enabled"] = bool(data.get("enabled"))
    elif not partial:
        payload["enabled"] = True
    if "expires_days" in data:
        days = _number(data, "expires_days", "有效期天数", default=0, minimum=0, maximum=36500)
        payload["expires_at"] = 0 if days == 0 else now() + days * 86400
    elif "expires_at" in data:
        payload["expires_at"] = _number(data, "expires_at", "到期时间", default=0, minimum=0, maximum=2**31)
    if "quota_gb" in data:
        try:
            gb = float(data["quota_gb"] or 0)
        except (TypeError, ValueError):
            raise ApiError(400, "流量额度必须是数字")
        if gb < 0 or gb > 1_000_000:
            raise ApiError(400, "流量额度不合法")
        payload["quota_bytes"] = int(gb * 1024**3)
    elif "quota_bytes" in data:
        payload["quota_bytes"] = _number(data, "quota_bytes", "流量额度", default=0, minimum=0, maximum=2**50)
    if "note" in data:
        payload["note"] = _text(data, "note", "备注", maxlen=200, default="")
    elif not partial:
        payload["note"] = ""
    return payload


def _sub_base(app, req: Request) -> str:
    settings = app.store.settings()
    configured = (settings.get("sub_base") or "").strip().rstrip("/")
    if configured:
        return configured
    sni = (settings.get("default_sni") or "").strip()
    if sni:
        return f"https://{sni}"
    scheme = "https" if _secure(req) else "http"
    return f"{scheme}://{req.headers.get('host') or app.store.public_host()}"


def _need_user(req: Request) -> dict:
    if not req.user:
        raise ApiError(401, "请先登录")
    return req.user


def _audit(app, req: Request, action: str, target: str = "", detail: str = "", actor: str | None = None) -> None:
    who = actor or (req.user["username"] if req.user else "anonymous")
    app.store.audit(action, target, detail, who, req.client_ip)


# ---------------------------------------------------------------- 认证


def setup(app, req: Request) -> Response:
    if app.store.user_count() > 0:
        raise ApiError(403, "面板已经初始化过了")
    data = req.json()
    username = _text(data, "username", "用户名", maxlen=32)
    if not USERNAME_RE.match(username):
        raise ApiError(400, "用户名只能包含字母、数字、下划线、点、短横线，3-32 位")
    password = data.get("password")
    if not isinstance(password, str):
        raise ApiError(400, "密码不能为空")
    problem = password_problem(password)
    if problem:
        raise ApiError(400, problem)

    uid = app.store.create_user(username, hash_password(password))
    token, csrf = app.store.create_session(uid, req.client_ip)
    user = app.store.user_by_id(uid)
    _audit(app, req, "初始化面板", username, "", actor=username)
    resp = Response.json({"ok": True, "csrf": csrf, "user": _public_user(user)})
    _set_cookie(resp, token, _secure(req))
    return resp


def login(app, req: Request) -> Response:
    wait = app.limiter.blocked(req.client_ip)
    if wait:
        raise ApiError(429, f"尝试过于频繁，请 {wait} 秒后再试")
    data = req.json()
    username = _text(data, "username", "用户名", maxlen=32)
    password = data.get("password")
    if not isinstance(password, str) or not password:
        raise ApiError(400, "密码不能为空")

    user = app.store.user_by_name(username)
    if not user or not verify_password(password, user["password_hash"]):
        app.limiter.fail(req.client_ip)
        _audit(app, req, "登录失败", username, "用户名或密码错误", actor=username)
        raise ApiError(401, "用户名或密码错误")

    app.limiter.reset(req.client_ip)
    token, csrf = app.store.create_session(user["id"], req.client_ip)
    app.store.touch_login(user["id"])
    _audit(app, req, "登录成功", username, "", actor=username)
    resp = Response.json({"ok": True, "csrf": csrf, "user": _public_user(user)})
    _set_cookie(resp, token, _secure(req))
    return resp


def logout(app, req: Request) -> Response:
    if req.session:
        app.store.drop_session(req.session["token"])
    resp = Response.json({"ok": True})
    _set_cookie(resp, "", _secure(req), max_age=0)
    return resp


def change_password(app, req: Request) -> Response:
    user = _need_user(req)
    data = req.json()
    current = data.get("current")
    new_password = data.get("password")
    if not isinstance(current, str) or not verify_password(current, user["password_hash"]):
        raise ApiError(400, "当前密码不正确")
    if not isinstance(new_password, str):
        raise ApiError(400, "新密码不能为空")
    problem = password_problem(new_password)
    if problem:
        raise ApiError(400, problem)
    app.store.set_password(user["id"], hash_password(new_password))
    # 让其他会话失效，保留当前
    app.store.drop_all_sessions(user["id"])
    token, csrf = app.store.create_session(user["id"], req.client_ip)
    _audit(app, req, "修改密码")
    resp = Response.json({"ok": True, "csrf": csrf})
    _set_cookie(resp, token, _secure(req))
    return resp


def healthz(app, req: Request) -> dict:
    return {"ok": True, "name": "reality-panel", "version": __version__}


def bootstrap(app, req: Request) -> dict:
    """登录前也能访问的元信息：是否需要初始化、面板名称。"""
    settings = app.store.settings()
    return {
        "setup_required": app.store.user_count() == 0,
        "panel_name": settings.get("panel_name") or "Reality Panel",
        "version": __version__,
        "public_host": app.store.public_host(),
    }


# ---------------------------------------------------------------- 状态


def state(app, req: Request) -> dict:
    user = _need_user(req)
    store = app.store
    settings = store.settings()
    nodes = store.nodes()
    subs = store.subs()
    clients = store.clients()

    counts: dict[int, int] = {}
    for client in clients:
        counts[client["node_id"]] = counts.get(client["node_id"], 0) + 1
    for node in nodes:
        node["client_count"] = counts.get(node["id"], 0)

    last_apply_raw = store.meta("last_apply", "")
    last_apply = None
    if last_apply_raw:
        try:
            last_apply = json.loads(last_apply_raw)
        except json.JSONDecodeError:
            last_apply = None

    return {
        "csrf": req.session["csrf"] if req.session else "",
        "user": _public_user(user),
        "now": now(),
        "version": __version__,
        "client_ip": req.client_ip,
        "public_host": store.public_host(),
        "sub_base": _sub_base(app, req),
        "settings": settings,
        "nodes": nodes,
        "subs": subs,
        "clients": clients,
        "summary": store.summary(),
        "xray": app.xray.status(),
        "dirty": store.meta("dirty", "0") == "1",
        "last_apply": last_apply,
        "meta": {
            "fingerprints": FINGERPRINTS,
            "xhttp_modes": XHTTP_MODES,
        },
    }


# ---------------------------------------------------------------- 节点


def create_node(app, req: Request) -> dict:
    data = req.json()
    payload = _node_payload(data)
    if app.store.node_by_port(payload["port"]):
        raise ApiError(409, f"端口 {payload['port']} 已被其他节点占用")
    private_key, public_key = new_node_keys()
    payload["private_key"] = private_key
    payload["public_key"] = public_key
    node = app.store.create_node(payload)
    app.mark_dirty()
    _audit(app, req, "创建节点", node["name"], f"{node['transport']} :{node['port']}")
    return {"ok": True, "node": node}


def update_node(app, req: Request, node_id: str) -> dict:
    nid = int(node_id)
    node = app.store.node(nid)
    if not node:
        raise ApiError(404, "节点不存在")
    data = req.json()
    payload = _node_payload(data, partial=True)
    if "port" in payload:
        conflict = app.store.node_by_port(payload["port"], exclude_id=nid)
        if conflict:
            raise ApiError(409, f"端口 {payload['port']} 已被节点「{conflict['name']}」占用")
    if "transport" in payload and payload["transport"] == "xhttp" and "xhttp_path" not in payload:
        if node["xhttp_path"] in ("", "/"):
            payload["xhttp_path"] = "/" + rand_hex(6)
    updated = app.store.update_node(nid, payload)
    app.mark_dirty()
    _audit(app, req, "修改节点", updated["name"] if updated else str(nid), ", ".join(payload))
    return {"ok": True, "node": updated}


def delete_node(app, req: Request, node_id: str) -> dict:
    nid = int(node_id)
    node = app.store.node(nid)
    if not node:
        raise ApiError(404, "节点不存在")
    app.store.delete_node(nid)
    app.mark_dirty()
    _audit(app, req, "删除节点", node["name"], f"{node['transport']} :{node['port']}")
    return {"ok": True}


def rotate_node_keys(app, req: Request, node_id: str) -> dict:
    nid = int(node_id)
    node = app.store.node(nid)
    if not node:
        raise ApiError(404, "节点不存在")
    private_key, public_key = new_node_keys()
    updated = app.store.update_node(nid, {"private_key": private_key, "public_key": public_key})
    app.mark_dirty()
    _audit(app, req, "更换 REALITY 密钥", node["name"], "")
    return {"ok": True, "node": updated}


# ---------------------------------------------------------------- 订阅用户


def create_sub(app, req: Request) -> dict:
    data = req.json()
    payload = _sub_payload(data)
    node_ids = _ids(data.get("node_ids"), "节点列表")
    known = {n["id"] for n in app.store.nodes()}
    node_ids = [n for n in node_ids if n in known]
    if not node_ids:
        raise ApiError(400, "至少选择一个节点")
    sub = app.store.create_sub(payload, node_ids)
    app.mark_dirty()
    _audit(app, req, "创建订阅", sub["name"], f"{len(node_ids)} 个节点")
    return {"ok": True, "sub": sub}


def update_sub(app, req: Request, sub_id: str) -> dict:
    sid = int(sub_id)
    if not app.store.sub(sid):
        raise ApiError(404, "订阅不存在")
    payload = _sub_payload(req.json(), partial=True)
    sub = app.store.update_sub(sid, payload)
    app.mark_dirty()
    _audit(app, req, "修改订阅", sub["name"] if sub else str(sid), ", ".join(payload))
    return {"ok": True, "sub": sub}


def delete_sub(app, req: Request, sub_id: str) -> dict:
    sid = int(sub_id)
    sub = app.store.sub(sid)
    if not sub:
        raise ApiError(404, "订阅不存在")
    app.store.delete_sub(sid)
    app.mark_dirty()
    _audit(app, req, "删除订阅", sub["name"], "")
    return {"ok": True}


def set_sub_nodes(app, req: Request, sub_id: str) -> dict:
    sid = int(sub_id)
    if not app.store.sub(sid):
        raise ApiError(404, "订阅不存在")
    node_ids = _ids(req.json().get("node_ids"), "节点列表")
    known = {n["id"] for n in app.store.nodes()}
    sub = app.store.set_sub_nodes(sid, [n for n in node_ids if n in known])
    app.mark_dirty()
    _audit(app, req, "调整订阅节点", sub["name"] if sub else str(sid), f"{len(node_ids)} 个节点")
    return {"ok": True, "sub": sub}


def rotate_sub(app, req: Request, sub_id: str) -> dict:
    sid = int(sub_id)
    sub = app.store.sub(sid)
    if not sub:
        raise ApiError(404, "订阅不存在")
    updated = app.store.rotate_sub(sid)
    _audit(app, req, "重置订阅", sub["name"], "token 与 UUID 全部更新")
    return {"ok": True, "sub": updated}


def reset_sub_traffic(app, req: Request, sub_id: str) -> dict:
    sid = int(sub_id)
    sub = app.store.sub(sid)
    if not sub:
        raise ApiError(404, "订阅不存在")
    app.store.reset_sub_traffic(sid)
    _audit(app, req, "重置流量", sub["name"], "")
    return {"ok": True, "sub": app.store.sub(sid)}


def sub_links(app, req: Request, sub_id: str) -> dict:
    sid = int(sub_id)
    sub = app.store.sub(sid)
    if not sub:
        raise ApiError(404, "订阅不存在")
    full = app.store.sub_by_token(sub["token"])
    assert full is not None
    host = app.store.public_host()
    base = _sub_base(app, req)
    return {
        "ok": True,
        "links": build_links(full, host),
        "sub_url": f"{base}/sub/{sub['token']}",
        "clash_url": f"{base}/sub/{sub['token']}/clash",
    }


# ---------------------------------------------------------------- 订阅分发


def subscription(app, req: Request, token: str, clash: str = "") -> Response:
    sub = app.store.sub_by_token(token)
    if not sub:
        raise ApiError(404, "订阅不存在")
    if not sub["enabled"]:
        raise ApiError(403, "订阅已被停用")
    if sub["expires_at"] and sub["expires_at"] < now():
        raise ApiError(403, "订阅已到期")

    host = app.store.public_host()
    want_clash = (
        bool(clash)
        or req.query.get("format") == "clash"
        # 部分客户端不认路径，只带 UA；顺手按 UA 自动返回 YAML
        or any(mark in (req.headers.get("user-agent") or "").lower() for mark in ("clash", "mihomo", "stash"))
    )

    up = sum(int(c.get("up_bytes") or 0) for c in sub["clients"])
    down = sum(int(c.get("down_bytes") or 0) for c in sub["clients"])
    settings = app.store.settings()
    headers = {
        "Profile-Update-Interval": settings.get("sub_interval_hours") or "12",
        "Subscription-Userinfo": (
            f"upload={up}; download={down}; total={sub['quota_bytes']}; expire={sub['expires_at']}"
        ),
        "Cache-Control": "no-store",
    }

    if want_clash:
        proxies = build_clash_proxies(sub, host)
        body = clash_config(proxies, settings.get("panel_name") or "Reality Panel")
        return Response(
            body=body.encode("utf-8"),
            content_type="text/yaml; charset=utf-8",
            headers=headers,
        )

    links = build_links(sub, host)
    payload = subscription_payload(links)
    return Response(
        body=payload.encode("ascii"),
        content_type="text/plain; charset=utf-8",
        headers=headers,
    )


# ---------------------------------------------------------------- 配置/运维


def apply_config(app, req: Request) -> dict:
    result = app.xray.apply()
    result.pop("config", None)
    stamp = now()
    if result.get("ok"):
        app.store.set_meta("dirty", "0")
    app.store.set_meta(
        "last_apply",
        json.dumps(
            {
                "at": stamp,
                "ok": bool(result.get("ok")),
                "warnings": result.get("warnings") or [],
            },
            ensure_ascii=False,
        ),
    )
    _audit(app, req, "应用配置", "", "成功" if result.get("ok") else "失败")
    return result


def config_preview(app, req: Request) -> dict:
    _, text = app.xray.render()
    return {"ok": True, "text": text, "path": app.store.setting("xray_config")}


def collect_stats(app, req: Request) -> dict:
    updated = app.xray.collect_stats()
    return {"ok": True, "updated": updated, "summary": app.store.summary()}


def sweep_subs(app, req: Request) -> dict:
    changed = app.store.sweep()
    if changed:
        app.mark_dirty()
    return {"ok": True, "changed": changed}


def logs(app, req: Request) -> dict:
    try:
        lines = max(1, min(int(req.query.get("lines") or 200), 2000))
    except ValueError:
        lines = 200
    return {"ok": True, "lines": app.xray.log_tail(lines), "path": app.store.setting("xray_log")}


def selfsteal(app, req: Request) -> dict:
    settings = app.store.settings()
    node = None
    node_id = req.query.get("node_id")
    if node_id:
        try:
            node = app.store.node(int(node_id))
        except ValueError:
            node = None
    if node is None:
        nodes = app.store.nodes()
        node = nodes[0] if nodes else None
    return nginx_plan(settings, node)


def update_settings(app, req: Request) -> dict:
    data = req.json()
    payload: dict[str, str] = {}
    for key, value in data.items():
        if key in DEFAULT_SETTINGS and value is not None:
            payload[key] = str(value).strip()

    if "default_sni" in payload and payload["default_sni"] and not valid_domain(payload["default_sni"]):
        raise ApiError(400, "默认 SNI 必须是合法域名")
    if "nginx_listen" in payload and not valid_hostport(payload["nginx_listen"]):
        raise ApiError(400, "nginx 监听地址格式应为 host:port")
    if "nginx_upstream" in payload:
        upstream = payload["nginx_upstream"]
        if not upstream.startswith(("http://", "https://")):
            raise ApiError(400, "上游站点必须以 http:// 或 https:// 开头")
    if "xver" in payload and payload["xver"] not in ("0", "1", "2"):
        raise ApiError(400, "PROXY protocol 版本只能是 0/1/2")
    if "sub_base" in payload and payload["sub_base"]:
        if not payload["sub_base"].startswith(("http://", "https://")):
            raise ApiError(400, "订阅域名必须以 http:// 或 https:// 开头")

    for key in ("access_allowlist_loopback", "access_allowlist_sub"):
        if key in payload:
            payload[key] = "1" if payload[key].lower() in ("1", "true", "on", "yes") else "0"

    if "access_allowlist" in payload:
        if len(payload["access_allowlist"]) > 4000:
            raise ApiError(400, "白名单条目过多")
        try:
            payload["access_allowlist"] = normalize(payload["access_allowlist"])
        except ValueError as exc:
            raise ApiError(400, f"白名单格式不正确：{exc}")
        if payload["access_allowlist"]:
            include_loopback = (
                payload.get("access_allowlist_loopback", app.store.setting("access_allowlist_loopback")) == "1"
            )
            if not is_allowed(req.client_ip, payload["access_allowlist"], include_loopback):
                raise ApiError(
                    400,
                    "当前 IP 不在白名单里，保存后会把你自己锁在外面；请先把当前 IP 加进去",
                )

    settings = app.store.save_settings(payload)
    _audit(app, req, "修改设置", "", ", ".join(sorted(payload)))
    return {"ok": True, "settings": settings}


def export_data(app, req: Request) -> Response:
    store = app.store
    payload = {
        "version": __version__,
        "exported_at": now(),
        "settings": store.settings(),
        "nodes": store.nodes(),
        "subs": [s for s in store.subs()],
        "clients": store.clients(),
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    _audit(app, req, "导出备份", "", "")
    return Response(
        body=body.encode("utf-8"),
        content_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="reality-panel-backup.json"'},
    )


def import_data(app, req: Request) -> dict:
    """用导出的 JSON 覆盖节点 / 订阅 / 凭据。破坏性操作，前端会二次确认。"""
    data = req.json()
    if not isinstance(data.get("nodes"), list) or not isinstance(data.get("subs"), list):
        raise ApiError(400, "备份格式不正确：缺少 nodes / subs 数组")
    raw_nodes = data["nodes"]
    raw_subs = data["subs"]
    raw_clients = data.get("clients") or []
    if not isinstance(raw_clients, list):
        raise ApiError(400, "备份格式不正确：clients 必须是数组")
    if len(raw_nodes) > 200 or len(raw_subs) > 2000 or len(raw_clients) > 20000:
        raise ApiError(400, "备份内容超出限制")

    try:
        nodes: list[dict] = []
        for raw in raw_nodes:
            if not isinstance(raw, dict):
                raise ValueError("节点条目不是对象")
            payload = _node_payload(raw)
            payload["private_key"] = str(raw.get("private_key") or "")
            payload["public_key"] = str(raw.get("public_key") or "")
            if not payload["private_key"] or not payload["public_key"]:
                raise ValueError(f"节点「{payload['name']}」缺少 REALITY 密钥")
            payload["id"] = int(raw.get("id") or 0)
            payload["created_at"] = int(raw.get("created_at") or 0)
            nodes.append(payload)

        subs: list[dict] = []
        used_tokens: set[str] = set()
        for raw in raw_subs:
            if not isinstance(raw, dict):
                raise ValueError("订阅条目不是对象")
            payload = _sub_payload(raw)
            token = str(raw.get("token") or "")
            if not token or token in used_tokens:
                token = rand_token(24)
            used_tokens.add(token)
            payload["token"] = token
            payload["id"] = int(raw.get("id") or 0)
            payload["created_at"] = int(raw.get("created_at") or 0)
            subs.append(payload)

        clients: list[dict] = []
        for raw in raw_clients:
            if not isinstance(raw, dict):
                continue
            clients.append(
                {
                    "sub_id": int(raw.get("sub_id") or 0),
                    "node_id": int(raw.get("node_id") or 0),
                    "uuid": str(raw.get("uuid") or ""),
                    "enabled": bool(raw.get("enabled", True)),
                    "up_bytes": int(raw.get("up_bytes") or 0),
                    "down_bytes": int(raw.get("down_bytes") or 0),
                    "last_seen_at": int(raw.get("last_seen_at") or 0),
                    "created_at": int(raw.get("created_at") or 0),
                }
            )
    except (TypeError, ValueError) as exc:
        raise ApiError(400, f"备份内容不合法：{exc}")

    stats = app.store.import_backup({"nodes": nodes, "subs": subs, "clients": clients})

    settings = data.get("settings")
    if isinstance(settings, dict):
        clean = {
            key: str(value)
            for key, value in settings.items()
            if key in DEFAULT_SETTINGS and isinstance(value, (str, int, float, bool))
        }
        if clean:
            app.store.save_settings(clean)

    app.mark_dirty()
    _audit(app, req, "恢复备份", "", f"{stats['nodes']} 节点 / {stats['subs']} 订阅")
    return {"ok": True, **stats}


def audit_list(app, req: Request) -> dict:
    try:
        limit = int(req.query.get("limit") or 200)
    except ValueError:
        limit = 200
    return {"ok": True, "items": app.store.audit_log(limit)}


# ---------------------------------------------------------------- 路由


def build_router() -> Router:
    router = Router()
    router.add("GET", r"/healthz", healthz, auth=False, csrf=False)
    router.add("GET", r"/api/bootstrap", bootstrap, auth=False, csrf=False)
    router.add("POST", r"/api/setup", setup, auth=False, csrf=False)
    router.add("POST", r"/api/login", login, auth=False, csrf=False)
    router.add("POST", r"/api/logout", logout)
    router.add("GET", r"/api/state", state)
    router.add("POST", r"/api/password", change_password)

    router.add("POST", r"/api/nodes", create_node)
    router.add("PATCH", r"/api/nodes/(?P<node_id>\d+)", update_node)
    router.add("DELETE", r"/api/nodes/(?P<node_id>\d+)", delete_node)
    router.add("POST", r"/api/nodes/(?P<node_id>\d+)/keys", rotate_node_keys)

    router.add("POST", r"/api/subs", create_sub)
    router.add("PATCH", r"/api/subs/(?P<sub_id>\d+)", update_sub)
    router.add("DELETE", r"/api/subs/(?P<sub_id>\d+)", delete_sub)
    router.add("POST", r"/api/subs/(?P<sub_id>\d+)/nodes", set_sub_nodes)
    router.add("POST", r"/api/subs/(?P<sub_id>\d+)/rotate", rotate_sub)
    router.add("POST", r"/api/subs/(?P<sub_id>\d+)/reset-traffic", reset_sub_traffic)
    router.add("GET", r"/api/subs/(?P<sub_id>\d+)/links", sub_links)

    router.add("POST", r"/api/apply", apply_config)
    router.add("GET", r"/api/config", config_preview)
    router.add("POST", r"/api/collect", collect_stats)
    router.add("POST", r"/api/sweep", sweep_subs)
    router.add("GET", r"/api/logs", logs)
    router.add("GET", r"/api/selfsteal", selfsteal)
    router.add("POST", r"/api/settings", update_settings)
    router.add("GET", r"/api/export", export_data)
    router.add("POST", r"/api/import", import_data)
    router.add("GET", r"/api/audit", audit_list)

    router.add(
        "GET",
        r"/sub/(?P<token>[A-Za-z0-9_-]{8,64})(?P<clash>/clash)?",
        subscription,
        auth=False,
        csrf=False,
    )
    return router
