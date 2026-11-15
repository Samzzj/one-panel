#!/usr/bin/env bash
# ------------------------------------------------------------
# 「自己偷自己」一键落地：证书 + Nginx 回落配置
#
#   sudo bash deploy/selfsteal.sh node.example.com
#   sudo bash deploy/selfsteal.sh node.example.com https://www.lovelive-anime.jp
#   sudo SITE_MODE=static SITE_ROOT=/var/www/nav bash deploy/selfsteal.sh node.example.com
#
# 环境变量：
#   EMAIL=you@example.com     证书通知邮箱（可省略）
#   PANEL_DIR=/opt/reality-panel
#   LISTEN=127.0.0.1:8003     Nginx 本地 TLS 监听（必须是回环地址）
#   PANEL_ADDR=127.0.0.1:8080 面板地址（/sub/ 反代目标）
#   CERT_DIR=/etc/letsencrypt/live
#   ACME_WEBROOT=/var/www/acme  HTTP-01 校验文件的根目录
#   SITE_MODE=proxy|static     proxy=反代外部站点，static=托管本地静态站
#   SITE_ROOT=/var/www/nav     SITE_MODE=static 时的站点根目录
#
# 证书续期：
#   这里用 webroot 而不是 standalone —— 80 端口交给 nginx 自己应答，
#   续期时不需要停 nginx、不占端口、也不重启 Xray（REALITY 不加载证书，
#   证书由 nginx 在回落端口出示）。certbot.timer 每天自动跑一次。
# ------------------------------------------------------------
set -euo pipefail

DOMAIN="${1:-}"
UPSTREAM="${2:-https://www.lovelive-anime.jp}"
EMAIL="${EMAIL:-}"
PANEL_DIR="${PANEL_DIR:-/opt/reality-panel}"
LISTEN="${LISTEN:-127.0.0.1:8003}"
PANEL_ADDR="${PANEL_ADDR:-127.0.0.1:8080}"
CERT_DIR="${CERT_DIR:-/etc/letsencrypt/live}"
ACME_WEBROOT="${ACME_WEBROOT:-/var/www/acme}"
SITE_MODE="${SITE_MODE:-proxy}"
SITE_ROOT="${SITE_ROOT:-/var/www/nav}"
CONF_PATH="${CONF_PATH:-/etc/nginx/conf.d/reality-selfsteal.conf}"

log()  { printf '\033[36m[selfsteal]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[selfsteal]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m[selfsteal]\033[0m %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || die "请用 root 运行"
[[ -n "${DOMAIN}" ]] || die "用法: sudo bash deploy/selfsteal.sh <域名> [上游站点]"

if ! [[ "${DOMAIN}" =~ ^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$ ]]; then
  die "域名格式不正确: ${DOMAIN}"
fi

# ---- 回落端口必须绑定回环，否则公网可直接访问并暴露源站证书 ----
LISTEN_HOST="${LISTEN%:*}"
LISTEN_HOST="${LISTEN_HOST#[}"
LISTEN_HOST="${LISTEN_HOST%]}"
case "${LISTEN_HOST}" in
  127.0.0.1|::1) ;;
  *) die "LISTEN 必须绑定回环地址（127.0.0.1:<端口> 或 [::1]:<端口>），当前是 ${LISTEN}" ;;
esac

case "${SITE_MODE}" in
  proxy) ;;
  static) [[ -d "${SITE_ROOT}" ]] || warn "静态站点目录 ${SITE_ROOT} 还不存在，稍后用 deploy/nav-site.sh 部署" ;;
  *) die "SITE_MODE 只能是 proxy 或 static，当前是 ${SITE_MODE}" ;;
esac

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
PUBLIC_IP="$(curl -4 -fsSL --max-time 5 https://api.ipify.org 2>/dev/null || true)"
if [[ -z "${RESOLVED}" ]]; then
  warn "无法解析 ${DOMAIN}，证书签发大概率会失败"
elif [[ -n "${PUBLIC_IP}" && "${RESOLVED}" != "${PUBLIC_IP}" ]]; then
  warn "${DOMAIN} 解析到 ${RESOLVED}，但本机公网 IP 是 ${PUBLIC_IP}"
  warn "如果使用 CDN/代理，请确认是灰云（DNS only），否则 REALITY 无法工作"
else
  log "DNS 正常：${RESOLVED}"
fi

# ------------------------------------------------------------ 80 端口交给 nginx 应答 ACME
ACME_CONF="/etc/nginx/conf.d/acme-${DOMAIN}.conf"
install -d -m 0755 "${ACME_WEBROOT}"

TMP_ACME="$(mktemp)"
# 只有 IPv6 真的可用时才加 [::]:80。禁用了 IPv6 的机器上（sysctl
# net.ipv6.conf.all.disable_ipv6=1），这一行会让 nginx 启动直接失败：
#   socket() [::]:80 failed (97: Address family not supported by protocol)
IPV6_LISTEN=""
if [ "$(cat /proc/sys/net/ipv6/conf/all/disable_ipv6 2>/dev/null || echo 1)" != "1" ]; then
  IPV6_LISTEN="    listen [::]:80;"
fi
cat >"${TMP_ACME}" <<EOF
# 由 Reality Panel 生成：HTTP-01 校验文件由 nginx 直接应答
# 续期只需要 reload nginx，不需要停服务、不占用 443
server {
    listen 80;
${IPV6_LISTEN}
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ {
        root ${ACME_WEBROOT};
        default_type text/plain;
        try_files \$uri =404;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}
EOF
install -D -m 0644 "${TMP_ACME}" "${ACME_CONF}"
rm -f "${TMP_ACME}"

if ! nginx -t >/dev/null 2>&1; then
  rm -f "${ACME_CONF}"
  die "写入 ${ACME_CONF} 后 nginx -t 未通过，已移除该文件"
fi
systemctl reload nginx 2>/dev/null || systemctl restart nginx

# ------------------------------------------------------------ 证书（webroot）
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

  log "向 Let's Encrypt 申请证书（HTTP-01 / webroot）"
  CERTBOT_ARGS=(certonly --webroot -w "${ACME_WEBROOT}" -d "${DOMAIN}"
    --non-interactive --agree-tos --keep-until-expiring
    --deploy-hook "systemctl reload nginx || true")
  if [[ -n "${EMAIL}" ]]; then
    CERTBOT_ARGS+=(-m "${EMAIL}")
  else
    CERTBOT_ARGS+=(--register-unsafely-without-email)
  fi

  if ! certbot "${CERTBOT_ARGS[@]}"; then
    die "证书申请失败。请确认 ${DOMAIN} 已解析到本机、80 端口可从公网访问；如果 80 被封，改用 DNS-01：
  ~/.acme.sh/acme.sh --issue --dns dns_cf -d ${DOMAIN} --reloadcmd 'systemctl reload nginx'"
  fi

  [[ -f "${CERT_FILE}" ]] || die "证书签发后仍找不到 ${CERT_FILE}"
fi

# ------------------------------------------------------------ 续期自检
if command -v certbot >/dev/null 2>&1; then
  if certbot renew --dry-run >/tmp/certbot-dryrun.log 2>&1; then
    log "续期自检通过（certbot renew --dry-run）"
  else
    warn "续期自检失败，请查看 /tmp/certbot-dryrun.log："
    tail -n 5 /tmp/certbot-dryrun.log >&2 || true
  fi
fi
if command -v systemctl >/dev/null 2>&1; then
  if systemctl list-timers 2>/dev/null | grep -q certbot; then
    log "certbot 定时续期已启用"
  else
    warn "没有检测到 certbot.timer；执行 systemctl enable --now certbot.timer"
  fi
fi

# ------------------------------------------------------------ 生成回落配置
TMP_CONF="$(mktemp)"
BACKUP=""
if [[ -f "${CONF_PATH}" ]]; then
  BACKUP="$(mktemp)"
  cp -a "${CONF_PATH}" "${BACKUP}"
fi

PANEL_DIR="${PANEL_DIR}" \
SITE_MODE="${SITE_MODE}" \
SITE_ROOT="${SITE_ROOT}" \
python3 - "${DOMAIN}" "${UPSTREAM}" "${LISTEN}" "${CERT_DIR}" "${PANEL_ADDR}" >"${TMP_CONF}" <<'PY'
import os
import sys

sys.path.insert(0, os.environ["PANEL_DIR"])
from panel.nginx import render_selfsteal  # noqa: E402

domain, upstream, listen, cert_dir, panel_addr = sys.argv[1:6]
site_root = os.environ.get("SITE_ROOT", "") if os.environ.get("SITE_MODE") == "static" else ""
sys.stdout.write(
    render_selfsteal(domain, upstream, listen, cert_dir, 1, panel_addr, site_root=site_root)
)
PY

# 生成结果自检：回落到公网就是灾难，宁可不写
if ! grep -qE "^[[:space:]]*listen[[:space:]]+(127\.0\.0\.1|\[::1\]):" "${TMP_CONF}"; then
  rm -f "${TMP_CONF}"
  die "生成的配置没有绑定回环地址，已中止。请检查 nginx_listen 设置"
fi

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
if [[ -n "${BACKUP}" ]]; then rm -f "${BACKUP}"; fi

systemctl reload nginx 2>/dev/null || systemctl restart nginx

# ------------------------------------------------------------ 端口隔离自检
LISTEN_PORT="${LISTEN##*:}"
if command -v ss >/dev/null 2>&1; then
  BOUND="$(ss -lntH "sport = :${LISTEN_PORT}" 2>/dev/null || true)"
  if [[ -n "${BOUND}" ]]; then
    if echo "${BOUND}" | grep -qvE "127\.0\.0\.1:${LISTEN_PORT}|\[::1\]:${LISTEN_PORT}"; then
      warn "端口 ${LISTEN_PORT} 上出现了非回环监听，请立刻检查："
      echo "${BOUND}" >&2
    else
      log "端口隔离正常：${LISTEN_PORT} 只监听回环"
    fi
  fi
fi

TARGET="${SITE_ROOT}"
[[ "${SITE_MODE}" == "static" ]] || TARGET="${UPSTREAM}"

cat <<EOF

============================================================
 自偷自配置完成
============================================================
 域名      ${DOMAIN}
 证书      ${CERT_FILE}
 回落      ${LISTEN} -> ${TARGET}（模式 ${SITE_MODE}）
 配置文件  ${CONF_PATH}
 ACME      80 端口由 ${ACME_CONF} 应答（自动续期，无需停 nginx）

 现在到面板创建节点：
   SNI            ${DOMAIN}
   回落 dest      ${LISTEN}
   PROXY protocol v1（与 Nginx 的 proxy_protocol 对应）

 本机验证（应该看到回落站点的内容）：
   curl -4 -vk --resolve ${DOMAIN}:443:127.0.0.1 https://${DOMAIN}/ -o /dev/null

 公网验证端口隔离（应该连不上）：
   curl -4 -k --max-time 3 https://${PUBLIC_IP:-<你的IP>}:${LISTEN_PORT}/

 订阅地址（由同一个 443 端口提供）：
   https://${DOMAIN}/sub/<token>
============================================================
EOF
