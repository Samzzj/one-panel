#!/usr/bin/env bash
# ------------------------------------------------------------
# 给面板加一个公网 HTTPS 入口（不用 SSH 隧道）
#
#   sudo bash deploy/panel-https.sh lisa.example.com
#   sudo bash deploy/panel-https.sh lisa.example.com 9443
#   sudo bash deploy/panel-https.sh --remove
#
# 原理：nginx 监听 9443（TLS，用你已有的 Let's Encrypt 证书），
# 反代到 127.0.0.1:8080 的面板。443 仍然归 Xray REALITY，互不影响。
# ------------------------------------------------------------
set -euo pipefail

DOMAIN="${1:-}"
PORT="${2:-9443}"
PANEL_ADDR="${PANEL_ADDR:-127.0.0.1:8080}"
CONF="/etc/nginx/conf.d/one-panel-admin.conf"
CERT_DIR="${CERT_DIR:-/etc/letsencrypt/live}"

log()  { printf '\033[36m[panel-https]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[panel-https]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m[panel-https]\033[0m %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || die "请用 root 运行"

if [[ "${DOMAIN}" == "--remove" ]]; then
  rm -f "${CONF}"
  nginx -t && systemctl reload nginx
  log "已移除面板 HTTPS 入口（${CONF}）"
  exit 0
fi

[[ -n "${DOMAIN}" ]] || die "用法: sudo bash deploy/panel-https.sh <域名> [端口]"
[[ "${DOMAIN}" =~ ^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$ ]] \
  || die "域名格式不正确: ${DOMAIN}"
[[ "${PORT}" =~ ^[0-9]+$ ]] || die "端口必须是数字"
[[ "${PORT}" -ge 1 && "${PORT}" -le 65535 ]] || die "端口超出范围"
[[ "${PORT}" != "443" ]] || die "443 被 Xray REALITY 占用，请换一个端口（默认 9443）"

CERT="${CERT_DIR}/${DOMAIN}/fullchain.pem"
KEY="${CERT_DIR}/${DOMAIN}/privkey.pem"
[[ -f "${CERT}" && -f "${KEY}" ]] || \
  die "找不到证书 ${CERT}；先执行 deploy/selfsteal.sh ${DOMAIN} 或 certbot 签发"

command -v nginx >/dev/null 2>&1 || die "缺少 nginx"

BACKUP=""
if [[ -f "${CONF}" ]]; then
  BACKUP="$(mktemp)"
  cp -a "${CONF}" "${BACKUP}"
fi

cat >"${CONF}" <<EOF
# 由 One Panel 生成：面板公网 HTTPS 入口
# 443 仍然归 Xray REALITY，这里只反代面板本身
server {
    listen ${PORT} ssl http2;
    server_name ${DOMAIN};

    ssl_certificate     ${CERT};
    ssl_certificate_key ${KEY};
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_session_cache   shared:PANEL_TLS:10m;

    server_tokens off;
    client_max_body_size 2m;

    location / {
        proxy_pass http://${PANEL_ADDR};
        proxy_http_version 1.1;
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 60s;
    }
}
EOF
chmod 0644 "${CONF}"

if ! nginx -t; then
  if [[ -n "${BACKUP}" ]]; then
    cp -a "${BACKUP}" "${CONF}"
    rm -f "${BACKUP}"
    warn "配置校验失败，已恢复原配置"
  else
    rm -f "${CONF}"
  fi
  die "nginx -t 未通过"
fi
[[ -n "${BACKUP}" ]] && rm -f "${BACKUP}"

systemctl reload nginx 2>/dev/null || systemctl restart nginx

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow "${PORT}/tcp" >/dev/null 2>&1 || true
  log "已在 ufw 放行 ${PORT}/tcp"
fi

cat <<EOF

============================================================
 面板 HTTPS 入口已就绪
============================================================
 地址    https://${DOMAIN}:${PORT}
 反代    ${PANEL_ADDR}
 配置    ${CONF}

 还需要：
   1. 云厂商安全组放行 TCP ${PORT}
   2. 服务器防火墙放行（脚本已尝试 ufw）
   3. 浏览器打开上面的地址，用面板账号登录

 安全建议：
   - 面板现在公网可达，务必用强密码
   - 「设置 → 访问白名单」可以只允许你的 IP
   - 不想暴露时执行：
       sudo bash deploy/panel-https.sh --remove
============================================================
EOF
