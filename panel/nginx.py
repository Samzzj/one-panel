"""「自己偷自己」的 Nginx 回落配置生成。

链路：
    Xray REALITY :443
      └─ 未通过 REALITY 校验的连接（探针 / 浏览器）按 PROXY protocol 转发
         └─ nginx 127.0.0.1:8003 终止 TLS（使用你自己域名的真证书）
            └─ 反代真实站点，返回真实内容

为什么必须用自有域名：
    REALITY 不自己出示证书，它把未认证的 TLS 连接原样转给 dest，
    由 dest 与探针完成握手。所以 dest 的证书必须与客户端发送的 SNI 匹配，
    否则探针一眼就能看出异常。用别人的域名拿不到证书，只能用自己的。
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")
HOSTPORT_RE = re.compile(r"^(?:\[[0-9a-fA-F:]+\]|[A-Za-z0-9.-]+):\d{1,5}$")


def valid_domain(value: str) -> bool:
    return bool(DOMAIN_RE.match((value or "").strip()))


def valid_hostport(value: str) -> bool:
    return bool(HOSTPORT_RE.match((value or "").strip()))


def _split_hostport(value: str) -> tuple[str, int]:
    host, _, port = value.rpartition(":")
    return host.strip("[]"), int(port)


def render_selfsteal(
    sni: str,
    upstream: str,
    listen_addr: str,
    cert_dir: str,
    xver: int = 1,
    panel_addr: str = "127.0.0.1:8080",
    include_sub: bool = True,
) -> str:
    """生成 nginx server 块。所有插值都做过白名单校验。"""
    sni = sni.strip()
    if not valid_domain(sni):
        raise ValueError("SNI 必须是合法域名（例如 node.example.com），不能是 IP 或含特殊字符")
    if not valid_hostport(listen_addr):
        raise ValueError("监听地址格式应为 127.0.0.1:8003")
    if not valid_hostport(panel_addr):
        raise ValueError("面板地址格式应为 127.0.0.1:8080")

    parsed = urlparse(upstream if "://" in upstream else f"https://{upstream}")
    upstream_host = parsed.hostname or ""
    if not upstream_host:
        raise ValueError("上游站点地址无效")
    scheme = parsed.scheme or "https"
    upstream_base = f"{scheme}://{upstream_host}"
    regex_host = re.escape(upstream_host)

    listen_host, listen_port = _split_hostport(listen_addr)
    proxy_protocol = int(xver) >= 1
    listen_line = f"listen {listen_host}:{listen_port} ssl"
    if proxy_protocol:
        listen_line += " proxy_protocol"
    # 兼容 nginx < 1.25.1：http2 写在 listen 里（新版本会给弃用警告，但可用）
    listen_line += " http2;"

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

    # 节点服务器上没有面板，不需要 /sub/ 反代；只有面板本机才加
    sub_block = ""
    if include_sub:
        sub_block = f"""
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

    return f"""# ============================================================
# 由 Reality Panel 生成 —— 重新生成会覆盖本文件
# 链路: Xray REALITY -> PROXY protocol -> {listen_host}:{listen_port} -> 本地 TLS -> 反代 {upstream_host}
# ============================================================

map $http_upgrade $reality_connection_upgrade {{
    default upgrade;
    ''      close;
}}

server {{
    {listen_line}
    server_name {sni};

    # ---- 本地 TLS：证书必须与客户端 SNI 完全一致 ----
    ssl_certificate     {cert};
    ssl_certificate_key {key};
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_session_cache   shared:REALITY_TLS:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
{real_ip}
    # 不暴露这是代理：隐藏常见指纹头
    server_tokens off;
    proxy_hide_header Alt-Svc;
    proxy_hide_header Content-Security-Policy;
    proxy_hide_header X-Frame-Options;
    proxy_hide_header Strict-Transport-Security;

    # ---- 上游真实站点 ----
    resolver 223.5.5.5 119.29.29.29 1.1.1.1 ipv6=off valid=300s;
    set $reality_upstream "{upstream_host}";
{sub_block}
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
}}
"""


def plan(settings: dict[str, str], node: dict | None = None) -> dict:
    """返回自偷自部署方案（配置文本 + 步骤 + 校验警告）。"""
    sni = (node or {}).get("sni") or settings.get("default_sni") or ""
    upstream = settings.get("nginx_upstream") or "https://www.lovelive-anime.jp"
    listen_addr = settings.get("nginx_listen") or "127.0.0.1:8003"
    cert_dir = settings.get("cert_dir") or "/etc/letsencrypt/live"
    panel_addr = settings.get("panel_addr") or "127.0.0.1:8080"
    xver = int((node or {}).get("xver") or settings.get("xver") or 1)

    warnings: list[str] = []
    conf = ""
    error = ""
    try:
        if not sni:
            raise ValueError("还没有设置 SNI 域名")
        conf = render_selfsteal(sni, upstream, listen_addr, cert_dir, xver, panel_addr)
    except ValueError as exc:
        error = str(exc)

    if sni and not valid_domain(sni):
        warnings.append("SNI 不是合法域名，REALITY 探针会看到不匹配的证书。")
    if node and node.get("dest") and node["dest"] != listen_addr:
        warnings.append(
            f"节点 dest 是 {node['dest']}，但 nginx 监听的是 {listen_addr}，两者必须一致。"
        )

    upstream_host = urlparse(upstream if "://" in upstream else f"https://{upstream}").hostname or ""
    steps = [
        {
            "title": "1. 解析域名",
            "detail": f"在 DNS 把 {sni or '<你的域名>'} 的 A 记录指向本机公网 IP。"
            "证书签发需要它，客户端连接不需要。",
            "command": f"dig +short {sni or 'node.example.com'}",
        },
        {
            "title": "2. 申请证书",
            "detail": "推荐 acme.sh 的 DNS-01，80 端口被封也能签；也可以 certbot standalone。",
            "command": (
                f"curl https://get.acme.sh | sh -s email=you@example.com\n"
                f"~/.acme.sh/acme.sh --issue --standalone -d {sni or 'node.example.com'}\n"
                f"~/.acme.sh/acme.sh --install-cert -d {sni or 'node.example.com'} "
                f"--key-file /etc/letsencrypt/live/{sni or 'node.example.com'}/privkey.pem "
                f"--fullchain-file /etc/letsencrypt/live/{sni or 'node.example.com'}/fullchain.pem "
                f"--reloadcmd 'systemctl reload nginx'"
            ),
        },
        {
            "title": "3. 写入 nginx 配置",
            "detail": f"保存到 {settings.get('nginx_conf')}，然后 nginx -t 并 reload。",
            "command": "nginx -t && systemctl reload nginx",
        },
        {
            "title": "4. 建节点",
            "detail": "传输选 Vision 或 XHTTP，SNI 填同一个域名，dest 指向 nginx 监听地址，"
            "PROXY protocol 选 v1。",
            "command": None,
        },
        {
            "title": "5. 订阅",
            "detail": f"订阅地址会自动走 https://{sni or '<域名>'}/sub/<token>，"
            f"由 nginx 反代到面板 {panel_addr}。确保面板以该地址启动（默认 127.0.0.1:8080）。",
            "command": None,
        },
        {
            "title": "6. 验证",
            "detail": "用浏览器直接访问 443 应该看到真实站点内容；"
            "再用客户端导入订阅测试连通。",
            "command": f"curl -vk --resolve {sni or 'node.example.com'}:443:127.0.0.1 https://{sni or 'node.example.com'}/ -o /dev/null",
        },
    ]

    if upstream_host:
        warnings.append(
            f"上游 {upstream_host} 的页面里若有大量第三方绝对地址，改写可能不完整；"
            "这不影响 REALITY 握手，只影响探针看到的页面完整度。"
        )

    return {
        "ok": not error,
        "error": error,
        "sni": sni,
        "upstream": upstream,
        "upstream_host": upstream_host,
        "listen": listen_addr,
        "panel_addr": panel_addr,
        "config_path": settings.get("nginx_conf"),
        "cert_path": f"{cert_dir.rstrip('/')}/{sni}/fullchain.pem" if sni else "",
        "key_path": f"{cert_dir.rstrip('/')}/{sni}/privkey.pem" if sni else "",
        "xver": xver,
        "conf": conf,
        "steps": steps,
        "warnings": warnings,
    }
