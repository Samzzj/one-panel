"""「自己偷自己」的 Nginx 回落配置生成。

链路：
    Xray REALITY :443
      └─ 未通过 REALITY 校验的连接（探针 / 浏览器）按 PROXY protocol 转发
         └─ nginx 127.0.0.1:8003 终止 TLS（使用你自己域名的真证书）
            ├─ /sub/  反代面板，提供订阅
            └─ /      回落站点：本地静态站（nav）或反代外部真实站点

两条回落路线：
    site_root 为空  —— 反代外部站点（proxy 模式，兼容旧行为）
    site_root 非空  —— 直接托管本地静态站（static 模式，推荐）
                      静态站由 deploy/nav-site.sh 部署到 /var/www/nav

为什么必须用自有域名：
    REALITY 不自己出示证书，它把未认证的 TLS 连接原样转给 dest，
    由 dest 与探针完成握手。所以 dest 的证书必须与客户端发送的 SNI 匹配，
    否则探针一眼就能看出异常。用别人的域名拿不到证书，只能用自己的。

为什么必须绑定回环：
    listen 一旦写成 0.0.0.0:8443，公网可以直接访问 https://IP:8443，
    既暴露源站证书和域名，也绕过了 REALITY 的伪装。这里在生成阶段就拒绝。
"""

from __future__ import annotations

import json
import os
import re
import ssl
from urllib.parse import urlparse

DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")
HOSTPORT_RE = re.compile(r"^(?:\[[0-9a-fA-F:]+\]|[A-Za-z0-9.-]+):\d{1,5}$")
# 静态站根目录：必须是绝对路径，且只允许安全字符（防止把 nginx 指令注入进来）
SITE_ROOT_RE = re.compile(r"^/[A-Za-z0-9._/-]{1,200}$")

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})


def valid_domain(value: str) -> bool:
    return bool(DOMAIN_RE.match((value or "").strip()))


def valid_hostport(value: str) -> bool:
    return bool(HOSTPORT_RE.match((value or "").strip()))


def valid_site_root(value: str) -> bool:
    root = (value or "").strip()
    if not root or ".." in root.split("/"):
        return False
    return bool(SITE_ROOT_RE.match(root)) and not root.endswith("/")


def _split_hostport(value: str) -> tuple[str, int]:
    host, _, port = value.rpartition(":")
    return host.strip("[]"), int(port)


def _require_loopback(listen_host: str) -> None:
    if listen_host not in LOOPBACK_HOSTS:
        raise ValueError(
            f"回落监听必须绑定回环地址（127.0.0.1 或 ::1），当前是 {listen_host}；"
            "否则公网可直接访问该端口并暴露源站证书"
        )


def _tls_block(sni: str, cert_dir: str, proxy_protocol: bool) -> str:
    cert = f"{cert_dir.rstrip('/')}/{sni}/fullchain.pem"
    key = f"{cert_dir.rstrip('/')}/{sni}/privkey.pem"
    real_ip = ""
    if proxy_protocol:
        real_ip = """
    # 只有本机 Xray 会连进来，PROXY protocol 里的源 IP 才是真实客户端
    set_real_ip_from 127.0.0.1;
    set_real_ip_from ::1;
    real_ip_header proxy_protocol;
"""
    return f"""    # ---- 本地 TLS：证书必须与客户端 SNI 完全一致 ----
    ssl_certificate     {cert};
    ssl_certificate_key {key};
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_session_cache   shared:REALITY_TLS:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
{real_ip}
    # 不暴露这是代理：隐藏常见指纹头
    server_tokens off;"""


def _sub_block(panel_addr: str) -> str:
    return f"""
    # ---- 订阅入口 ----
    # 普通 HTTPS 请求（浏览器 / 客户端拉订阅）没有 REALITY 认证数据，
    # 会被原样转到这个 server，于是同一个 443 域名也能提供订阅。
    location ^~ /sub/ {{
        proxy_pass http://{panel_addr};
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 30s;
    }}
"""


def _static_location(site_root: str) -> str:
    return f"""
    # ---- 本地静态站（deploy/nav-site.sh 部署）----
    root  {site_root};
    index index.html;
    charset utf-8;

    gzip              on;
    gzip_min_length   1024;
    gzip_comp_level   4;
    gzip_types        text/plain text/css application/javascript application/json
                      image/svg+xml application/xml text/xml;

    # HTML 不缓存：改完内容立刻生效
    location = /index.html {{
        add_header Cache-Control "no-cache";
    }}

    # 用站点自己的 404 页面，避免露出 nginx 默认页
    error_page 404 /404.html;
    location = /404.html {{
        internal;
    }}

    location ~* \\.(?:css|js|mjs|jpg|jpeg|png|gif|svg|webp|avif|ico|woff2?|ttf|eot|map)$ {{
        expires 1h;
        add_header Cache-Control "public";
        access_log off;
    }}

    location / {{
        try_files $uri $uri/ =404;
    }}
"""


def _proxy_location(upstream_host: str, scheme: str, upstream_base: str, regex_host: str) -> str:
    return f"""
    # ---- 上游真实站点 ----
    resolver 223.5.5.5 119.29.29.29 1.1.1.1 ipv6=off valid=300s;
    set $reality_upstream "{upstream_host}";
    location / {{
        proxy_pass {scheme}://$reality_upstream$request_uri;
        proxy_http_version 1.1;

        # 上游也走 SNI，且证书按上游域名校验失败时不至于 502（上游本身是可信站点）
        proxy_ssl_server_name on;
        proxy_ssl_name $reality_upstream;

        proxy_set_header Host              $reality_upstream;
        proxy_set_header User-Agent        $http_user_agent;
        proxy_set_header Accept-Language   $http_accept_language;
        proxy_set_header Referer           {upstream_base}$request_uri;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header Upgrade           $http_upgrade;
        proxy_set_header Connection        $reality_connection_upgrade;

        # 关掉压缩，sub_filter 才能改写 HTML 里的绝对链接
        proxy_set_header Accept-Encoding   "";

        # 把上游的绝对地址改写成当前域名，页面资源才不会漏到真实站点
        sub_filter_once off;
        sub_filter '{upstream_base}' 'https://$host';
        proxy_redirect ~^https?://{regex_host}(/.*)?$ https://$host$1;

        proxy_buffering off;
        proxy_read_timeout 60s;
        proxy_connect_timeout 10s;
    }}
"""


def render_selfsteal(
    sni: str,
    upstream: str,
    listen_addr: str,
    cert_dir: str,
    xver: int = 1,
    panel_addr: str = "127.0.0.1:8080",
    include_sub: bool = True,
    site_root: str = "",
) -> str:
    """生成 nginx server 块。所有插值都做过白名单校验。

    site_root 非空时生成静态站点配置，否则反代 upstream。
    """
    sni = sni.strip()
    if not valid_domain(sni):
        raise ValueError("SNI 必须是合法域名（例如 node.example.com），不能是 IP 或含特殊字符")
    if not valid_hostport(listen_addr):
        raise ValueError("监听地址格式应为 127.0.0.1:8003")
    if not valid_hostport(panel_addr):
        raise ValueError("面板地址格式应为 127.0.0.1:8080")

    listen_host, listen_port = _split_hostport(listen_addr)
    _require_loopback(listen_host)

    proxy_protocol = int(xver) >= 1
    listen_target = f"[{listen_host}]:{listen_port}" if ":" in listen_host else f"{listen_host}:{listen_port}"
    listen_line = f"listen {listen_target} ssl"
    if proxy_protocol:
        listen_line += " proxy_protocol"
    # 兼容 nginx < 1.25.1：http2 写在 listen 里（新版本只给弃用警告，仍然可用）
    listen_line += " http2;"

    site_root = (site_root or "").strip()
    if site_root and not valid_site_root(site_root):
        raise ValueError("静态站点根目录必须是绝对路径，例如 /var/www/nav")

    parsed = urlparse(upstream if "://" in upstream else f"https://{upstream}")
    upstream_host = parsed.hostname or ""
    if not site_root and not upstream_host:
        raise ValueError("上游站点地址无效")
    scheme = parsed.scheme or "https"
    upstream_base = f"{scheme}://{upstream_host}" if upstream_host else ""
    regex_host = re.escape(upstream_host)

    sub_block = _sub_block(panel_addr) if include_sub else ""
    if site_root:
        body = _static_location(site_root)
        map_block = ""
        chain = f"{listen_target} -> 本地 TLS -> 静态站 {site_root}"
    else:
        body = _proxy_location(upstream_host, scheme, upstream_base, regex_host)
        map_block = """map $http_upgrade $reality_connection_upgrade {
    default upgrade;
    ''      close;
}

"""
        chain = f"{listen_target} -> 本地 TLS -> 反代 {upstream_host}"

    return f"""# ============================================================
# 由 Reality Panel 生成 —— 重新生成会覆盖本文件
# 链路: Xray REALITY -> {'PROXY protocol -> ' if proxy_protocol else ''}{chain}
# ============================================================

{map_block}server {{
    {listen_line}
    server_name {sni};

{_tls_block(sni, cert_dir, proxy_protocol)}
{sub_block}{body}}}
"""


# ---------------------------------------------------------------- preflight


def _load_xray_reality(config_path: str) -> dict | None:
    """读本机 Xray 配置，返回第一个 reality inbound 的 (serverNames, dest)。"""
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    inbounds = data.get("inbounds") or []
    for inbound in inbounds:
        stream = inbound.get("streamSettings") or {}
        if stream.get("security") != "reality":
            continue
        settings = stream.get("realitySettings") or {}
        return {
            "port": inbound.get("port"),
            "server_names": [str(x) for x in (settings.get("serverNames") or [])],
            "dest": str(settings.get("dest") or ""),
            "xver": settings.get("xver"),
        }
    return None


def certificate_dns_names(cert_path: str) -> list[str] | None:
    """读证书里的 DNS 名称（含 CN），读不到返回 None。"""
    try:
        decoded = ssl._ssl._test_decode_cert(cert_path)  # type: ignore[attr-defined]
    except (OSError, ValueError, AttributeError):
        return None
    names = [value for key, value in decoded.get("subjectAltName", ()) if key == "DNS"]
    for group in decoded.get("subject", ()):
        for key, value in group:
            if key == "commonName" and value not in names:
                names.append(value)
    return names


def _check(checks: list[dict], level: str, ident: str, message: str) -> None:
    checks.append({"id": ident, "level": level, "message": message})


def preflight(
    settings: dict[str, str],
    sni: str,
    listen_addr: str,
    cert_dir: str,
    dest: str,
    site_root: str = "",
    local: bool = True,
) -> list[dict]:
    """一致性自检：SNI、dest、nginx 监听、证书、站点目录。

    level=error 会阻止生成/下发，warn 只提示。
    远程节点不读本机文件（local=False），只做结构校验。
    """
    checks: list[dict] = []

    if dest and dest.strip() != listen_addr.strip():
        _check(
            checks,
            "error",
            "dest-mismatch",
            f"节点 dest 是 {dest}，nginx 监听的是 {listen_addr}；"
            "两者必须完全一致，否则 REALITY 握手会失败",
        )

    if not local:
        return checks

    config_path = settings.get("xray_config") or "/usr/local/etc/xray/config.json"
    reality = _load_xray_reality(config_path)
    if reality is None:
        _check(checks, "warn", "xray-config", f"读不到 {config_path} 里的 reality 入站，跳过 SNI 比对")
    else:
        names = reality["server_names"]
        if names and sni not in names:
            _check(
                checks,
                "error",
                "servernames",
                f"realitySettings.serverNames 是 {names}，不包含 SNI {sni}；"
                "客户端握手会被拒绝",
            )
        if reality["dest"] and reality["dest"] != listen_addr:
            _check(
                checks,
                "error",
                "reality-dest",
                f"realitySettings.dest 是 {reality['dest']}，与 nginx 监听的 {listen_addr} 不一致",
            )

    cert = f"{cert_dir.rstrip('/')}/{sni}/fullchain.pem"
    names = certificate_dns_names(cert)
    if names is None:
        _check(checks, "warn", "cert", f"读不到证书 {cert}（可能还没签发，或面板无读权限）")
    elif sni not in names:
        _check(
            checks,
            "error",
            "cert-sni",
            f"证书 {cert} 的域名是 {names}，与 SNI {sni} 不匹配，探针会看到证书告警",
        )

    if site_root:
        index_path = f"{site_root.rstrip('/')}/index.html"
        if not os.path.isfile(index_path):
            _check(
                checks,
                "warn",
                "site-root",
                f"静态站点还没部署：找不到 {index_path}，执行 deploy/nav-site.sh 后才会生效",
            )

    return checks


def plan(settings: dict[str, str], node: dict | None = None, local: bool = True) -> dict:
    """返回自偷自部署方案（配置文本 + 步骤 + 校验结论）。"""
    sni = (node or {}).get("sni") or settings.get("default_sni") or ""
    mode = (settings.get("site_mode") or "proxy").strip().lower()
    # 静态模式下上游站点根本不参与渲染，不要把它带进返回值和界面上，
    # 否则面板里会一直显示一个跟实际行为无关的域名。
    if mode == "static":
        upstream = ""
    else:
        upstream = settings.get("nginx_upstream") or "https://www.lovelive-anime.jp"
    listen_addr = settings.get("nginx_listen") or "127.0.0.1:8003"
    cert_dir = settings.get("cert_dir") or "/etc/letsencrypt/live"
    panel_addr = settings.get("panel_addr") or "127.0.0.1:8080"
    site_root = (settings.get("site_root") or "/var/www/nav").strip() if mode == "static" else ""
    xver = int((node or {}).get("xver") if (node or {}).get("xver") is not None else (settings.get("xver") or 1))

    conf = ""
    error = ""
    checks: list[dict] = []
    try:
        if not sni:
            raise ValueError("还没有设置 SNI 域名")
        conf = render_selfsteal(
            sni, upstream, listen_addr, cert_dir, xver, panel_addr, site_root=site_root
        )
    except ValueError as exc:
        error = str(exc)

    if conf:
        checks = preflight(
            settings,
            sni,
            listen_addr,
            cert_dir,
            (node or {}).get("dest") or "",
            site_root=site_root,
            local=local,
        )
        blocking = [c for c in checks if c["level"] == "error"]
        if blocking:
            error = blocking[0]["message"]

    warnings = [c["message"] for c in checks if c["level"] == "warn"]

    upstream_host = urlparse(upstream if "://" in upstream else f"https://{upstream}").hostname or ""
    target = site_root or upstream_host
    steps = [
        {
            "title": "1. 解析域名",
            "detail": f"在 DNS 把 {sni or '<你的域名>'} 的 A 记录指向本机公网 IP，"
            "并保持 Cloudflare 灰云（DNS only），否则 REALITY 无法工作。",
            "command": f"dig +short {sni or 'node.example.com'}",
        },
        {
            "title": "2. 申请证书（webroot，可自动续期）",
            "detail": "80 端口由 nginx 自己应答 ACME，续期不需要停服务、不需要重启 Xray。",
            "command": (
                f"sudo SITE_MODE={'static' if site_root else 'proxy'} "
                f"bash deploy/selfsteal.sh {sni or 'node.example.com'}"
            ),
        },
        {
            "title": "3. 部署回落站点",
            "detail": (
                f"静态站放到 {site_root}，然后执行 deploy/nav-site.sh 重新下发 nginx 配置。"
                if site_root
                else f"确认上游 {upstream_host} 可访问；nginx 会反代它并改写绝对链接。"
            ),
            "command": "sudo bash deploy/nav-site.sh" if site_root else None,
        },
        {
            "title": "4. 建节点",
            "detail": f"传输选 Vision 或 XHTTP，SNI 填 {sni or '<域名>'}，"
            f"dest 填 {listen_addr}，PROXY protocol 选 v1。",
            "command": None,
        },
        {
            "title": "5. 订阅",
            "detail": f"订阅地址走 https://{sni or '<域名>'}/sub/<token>，由 nginx 反代到面板 {panel_addr}。",
            "command": None,
        },
        {
            "title": "6. 验证握手与隔离",
            "detail": "本机用 SNI 访问 443 应看到回落站点；同时确认 8443 只监听回环。",
            "command": (
                f"curl -4 -vk --resolve {sni or 'node.example.com'}:443:127.0.0.1 "
                f"https://{sni or 'node.example.com'}/ -o /dev/null\n"
                f"ss -lntp | grep {listen_addr.rsplit(':', 1)[-1]}"
            ),
        },
    ]

    if site_root and upstream_host:
        warnings.append(
            f"静态模式会忽略上游 {upstream_host}；想回到反代模式把「回落模式」改回 proxy。"
        )

    return {
        "ok": not error,
        "error": error,
        "sni": sni,
        "mode": mode,
        "upstream": upstream,
        "upstream_host": upstream_host,
        "site_root": site_root,
        "target": target,
        "listen": listen_addr,
        "panel_addr": panel_addr,
        "config_path": settings.get("nginx_conf"),
        "cert_path": f"{cert_dir.rstrip('/')}/{sni}/fullchain.pem" if sni else "",
        "key_path": f"{cert_dir.rstrip('/')}/{sni}/privkey.pem" if sni else "",
        "xver": xver,
        "conf": conf,
        "checks": checks,
        "steps": steps,
        "warnings": warnings,
    }
