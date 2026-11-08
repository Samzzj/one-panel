#!/usr/bin/env bash
# ------------------------------------------------------------
# 「自己偷自己」一键落地：证书 + Nginx 回落配置
#
#   sudo bash deploy/selfsteal.sh node.example.com
#   sudo bash deploy/selfsteal.sh node.example.com https://www.lovelive-anime.jp
#
# 环境变量：
#   EMAIL=you@example.com     证书通知邮箱（可省略）
#   PANEL_DIR=/opt/reality-panel
#   LISTEN=127.0.0.1:8003     Nginx 本地 TLS 监听
#   PANEL_ADDR=127.0.0.1:8080 面板地址（/sub/ 反代目标）
#   CERT_DIR=/etc/letsencrypt/live
# ------------------------------------------------------------
set -euo pipefail

DOMAIN="${1:-}"
UPSTREAM="${2:-https://www.lovelive-anime.jp}"
EMAIL="${EMAIL:-}"
PANEL_DIR="${PANEL_DIR:-/opt/reality-panel}"
LISTEN="${LISTEN:-127.0.0.1:8003}"
PANEL_ADDR="${PANEL_ADDR:-127.0.0.1:8080}"
CERT_DIR="${CERT_DIR:-/etc/letsencrypt/live}"
CONF_PATH="${CONF_PATH:-/etc/nginx/conf.d/reality-selfsteal.conf}"

log()  { printf '\033[36m[selfsteal]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[selfsteal]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m[selfsteal]\033[0m %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || die "请用 root 运行"
[[ -n "${DOMAIN}" ]] || die "用法: sudo bash deploy/selfsteal.sh <域名> [上游站点]"

if ! [[ "${DOMAIN}" =~ ^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$ ]]; then
  die "域名格式不正确: ${DOMAIN}"
fi

command -v python3 >/dev/null 2>&1 || die "缺少 python3"
[[ -f "${PANEL_DIR}/panel/nginx.py" ]] || die "找不到面板程序：${PANEL_DIR}（可用 PANEL_DIR 指定）"

if ! command -v nginx >/dev/null 2>&1; then
  log "安装 nginx"
  if command -v apt-get >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get update -qq && apt-get install -y -qq nginx
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y -q nginx
  else
    die "请先安装 nginx"
  fi
fi

# ------------------------------------------------------------ DNS 检查
log "检查 ${DOMAIN} 的解析"
RESOLVED="$(getent ahostsv4 "${DOMAIN}" 2>/dev/null | awk 'NR==1{print $1}' || true)"
PUBLIC_IP="$(curl -fsSL --max-time 5 https://api.ipify.org 2>/dev/null || true)"
if [[ -z "${RESOLVED}" ]]; then
  warn "无法解析 ${DOMAIN}，证书签发大概率会失败"
elif [[ -n "${PUBLIC_IP}" && "${RESOLVED}" != "${PUBLIC_IP}" ]]; then
  warn "${DOMAIN} 解析到 ${RESOLVED}，但本机公网 IP 是 ${PUBLIC_IP}"
  warn "如果使用 CDN/代理，请确认回源指向本机"
else
  log "DNS 正常：${RESOLVED}"
fi

# ------------------------------------------------------------ 证书
CERT_FILE="${CERT_DIR}/${DOMAIN}/fullchain.pem"
KEY_FILE="${CERT_DIR}/${DOMAIN}/privkey.pem"

if [[ -f "${CERT_FILE}" && -f "${KEY_FILE}" ]]; then
  log "已存在证书，跳过申请"
else
  command -v certbot >/dev/null 2>&1 || {
    log "安装 certbot"
    if command -v apt-get >/dev/null 2>&1; then
      DEBIAN_FRONTEND=noninteractive apt-get install -y -qq certbot
    elif command -v dnf >/dev/null 2>&1; then
      dnf install -y -q certbot
    else
      die "请先安装 certbot"
    fi
  }

  # standalone 模式需要 80 端口；如果被 nginx 占用，临时停一下
  NGINX_WAS_RUNNING=0
  if systemctl is-active --quiet nginx 2>/dev/null; then
    NGINX_WAS_RUNNING=1
    log "临时停止 nginx 以释放 80 端口"
    systemctl stop nginx
  fi

  log "向 Let's Encrypt 申请证书（HTTP-01）"
  CERTBOT_ARGS=(certonly --standalone -d "${DOMAIN}" --non-interactive --agree-tos
    --keep-until-expiring --deploy-hook "systemctl reload nginx || true")
  if [[ -n "${EMAIL}" ]]; then
    CERTBOT_ARGS+=(-m "${EMAIL}")
  else
    CERTBOT_ARGS+=(--register-unsafely-without-email)
  fi

  if ! certbot "${CERTBOT_ARGS[@]}"; then
    [[ "${NGINX_WAS_RUNNING}" -eq 1 ]] && systemctl start nginx
    die "证书申请失败。请确认 ${DOMAIN} 已解析到本机、80 端口可从公网访问，然后重试。"
  fi

  [[ "${NGINX_WAS_RUNNING}" -eq 1 ]] && systemctl start nginx

  # certbot 默认路径可能不同，做一次软链接兼容
  if [[ ! -f "${CERT_FILE}" && -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
    CERT_FILE="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
    KEY_FILE="/etc/letsencrypt/live/${DOMAIN}/privkey.pem"
  fi
  [[ -f "${CERT_FILE}" ]] || die "证书签发后仍找不到 ${CERT_FILE}"
fi

# ------------------------------------------------------------ 生成配置
TMP_CONF="$(mktemp)"
BACKUP=""
if [[ -f "${CONF_PATH}" ]]; then
  BACKUP="$(mktemp)"
  cp -a "${CONF_PATH}" "${BACKUP}"
fi

PANEL_DIR="${PANEL_DIR}" python3 - "${DOMAIN}" "${UPSTREAM}" "${LISTEN}" "${CERT_DIR}" "${PANEL_ADDR}" >"${TMP_CONF}" <<'PY'
import os
import sys

sys.path.insert(0, os.environ["PANEL_DIR"])
from panel.nginx import render_selfsteal  # noqa: E402

domain, upstream, listen, cert_dir, panel_addr = sys.argv[1:6]
sys.stdout.write(render_selfsteal(domain, upstream, listen, cert_dir, 1, panel_addr))
PY

install -D -m 0644 "${TMP_CONF}" "${CONF_PATH}"
rm -f "${TMP_CONF}"

if ! nginx -t; then
  if [[ -n "${BACKUP}" ]]; then
    cp -a "${BACKUP}" "${CONF_PATH}"
    rm -f "${BACKUP}"
    warn "配置校验失败，已恢复原配置"
  else
    rm -f "${CONF_PATH}"
  fi
  die "nginx -t 未通过"
fi
[[ -n "${BACKUP}" ]] && rm -f "${BACKUP}"

systemctl reload nginx 2>/dev/null || systemctl restart nginx

cat <<EOF

============================================================
 自偷自配置完成
============================================================
 域名      ${DOMAIN}
 证书      ${CERT_FILE}
 回落      ${LISTEN} -> ${UPSTREAM}
 配置文件  ${CONF_PATH}

 现在到面板创建节点：
   SNI            ${DOMAIN}
   回落 dest      ${LISTEN}
   PROXY protocol v1（与 Nginx 的 proxy_protocol 对应）

 本机验证（应该看到上游站点的内容）：
   curl -vk --resolve ${DOMAIN}:443:127.0.0.1 https://${DOMAIN}/ -o /dev/null

 订阅地址（由同一个 443 端口提供）：
   https://${DOMAIN}/sub/<token>
============================================================
EOF
