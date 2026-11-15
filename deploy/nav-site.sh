#!/usr/bin/env bash
# ------------------------------------------------------------
# 部署回落静态站（导航站）并重新下发 nginx 配置
#
#   sudo bash deploy/nav-site.sh nav.example.com
#   sudo bash deploy/nav-site.sh nav.example.com /opt/webstack-nav/public
#   sudo bash deploy/nav-site.sh --rollback
#
# 做的事：
#   1. 把构建产物拷到 /var/www/nav-releases/<时间戳>
#   2. 原子切换软链 /var/www/nav -> 新版本
#   3. 用 static 模式重新生成回落配置（只监听回环）
#   4. nginx -t 失败自动回滚（软链和配置都回滚）
#   5. 自检：端口只绑回环 + 本机 SNI 访问返回 200
#
# 环境变量：
#   SITE_DIR=/var/www/nav          对外暴露的软链
#   RELEASES=/var/www/nav-releases 版本目录
#   KEEP=5                         保留多少个历史版本
#   LISTEN=127.0.0.1:8003          回落监听（必须是回环）
#   PANEL_DIR=/opt/reality-panel
#   CERT_DIR=/etc/letsencrypt/live
#   CONF_PATH=/etc/nginx/conf.d/reality-selfsteal.conf
# ------------------------------------------------------------
set -euo pipefail

DOMAIN="${1:-}"
SOURCE="${2:-/opt/webstack-nav/public}"
PANEL_DIR="${PANEL_DIR:-/opt/reality-panel}"
SITE_DIR="${SITE_DIR:-/var/www/nav}"
RELEASES="${RELEASES:-/var/www/nav-releases}"
KEEP="${KEEP:-5}"
LISTEN="${LISTEN:-127.0.0.1:8003}"
PANEL_ADDR="${PANEL_ADDR:-127.0.0.1:8080}"
CERT_DIR="${CERT_DIR:-/etc/letsencrypt/live}"
CONF_PATH="${CONF_PATH:-/etc/nginx/conf.d/reality-selfsteal.conf}"

log()  { printf '\033[36m[nav-site]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[nav-site]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m[nav-site]\033[0m %s\n' "$*" >&2; exit 1; }

# 把 SITE_DIR 指到某个版本目录。
# 注意：如果 SITE_DIR 已经是个普通目录，`ln -sfn` 会把软链建到目录**里面**，
# 结果 root 指向一个空目录、首页 403。所以先把旧目录删掉，再用 -T 强制替换。
link_site() {
  local target="$1"
  if [ -d "${SITE_DIR}" ] && [ ! -L "${SITE_DIR}" ]; then
    rm -rf "${SITE_DIR}"
  fi
  ln -sfnT "${target}" "${SITE_DIR}" 2>/dev/null || ln -sfn "${target}" "${SITE_DIR}"
}

[[ "${EUID}" -eq 0 ]] || die "请用 root 运行"

# ------------------------------------------------------------ 回滚
if [[ "${DOMAIN}" == "--rollback" ]]; then
  PREV="$(ls -1dt "${RELEASES}"/*/ 2>/dev/null | sed -n 2p || true)"
  [[ -n "${PREV}" ]] || die "没有可回滚的历史版本"
  link_site "${PREV%/}"
  systemctl reload nginx 2>/dev/null || true
  log "已回滚到 ${PREV%/}"
  exit 0
fi

[[ -n "${DOMAIN}" ]] || die "用法: sudo bash deploy/nav-site.sh <域名> [构建产物目录]"
if ! [[ "${DOMAIN}" =~ ^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$ ]]; then
  die "域名格式不正确: ${DOMAIN}"
fi

LISTEN_HOST="${LISTEN%:*}"
LISTEN_HOST="${LISTEN_HOST#[}"
LISTEN_HOST="${LISTEN_HOST%]}"
case "${LISTEN_HOST}" in
  127.0.0.1|::1) ;;
  *) die "LISTEN 必须绑定回环地址，当前是 ${LISTEN}" ;;
esac

[[ -d "${SOURCE}" ]] || die "找不到构建产物目录：${SOURCE}"
[[ -f "${SOURCE}/index.html" ]] || die "${SOURCE} 里没有 index.html，先构建站点（hugo）"
[[ -f "${CONF_PATH}" ]] || die "还没有回落配置：先执行 deploy/selfsteal.sh ${DOMAIN}"

command -v python3 >/dev/null 2>&1 || die "缺少 python3"
[[ -f "${PANEL_DIR}/panel/nginx.py" ]] || die "找不到面板程序：${PANEL_DIR}"

# ------------------------------------------------------------ 落版本
STAMP="$(date +%Y%m%d-%H%M%S)"
RELEASE="${RELEASES}/${STAMP}"
install -d -m 0755 "${RELEASES}"
install -d -m 0755 "${RELEASE}"
# 点文件也要带上（.well-known 之类），先删再拷，避免残留旧文件
cp -aT "${SOURCE}" "${RELEASE}"
chown -R root:root "${RELEASE}"
chmod -R a+rX,go-w "${RELEASE}"

OLD_TARGET="$(readlink -f "${SITE_DIR}" 2>/dev/null || true)"
OLD_CONF="$(mktemp)"
cp -a "${CONF_PATH}" "${OLD_CONF}"

link_site "${RELEASE}"
log "已切换到 ${RELEASE}"

# ------------------------------------------------------------ 生成配置
TMP_CONF="$(mktemp)"
PANEL_DIR="${PANEL_DIR}" python3 - "${DOMAIN}" "${LISTEN}" "${CERT_DIR}" "${PANEL_ADDR}" "${SITE_DIR}" >"${TMP_CONF}" <<'PY'
import os
import sys

sys.path.insert(0, os.environ["PANEL_DIR"])
from panel.nginx import render_selfsteal  # noqa: E402

domain, listen, cert_dir, panel_addr, site_root = sys.argv[1:6]
sys.stdout.write(
    render_selfsteal(
        domain,
        "https://www.lovelive-anime.jp",  # static 模式下不使用
        listen,
        cert_dir,
        1,
        panel_addr,
        site_root=site_root,
    )
)
PY

if ! grep -qE "^[[:space:]]*listen[[:space:]]+(127\.0\.0\.1|\[::1\]):" "${TMP_CONF}"; then
  rm -f "${TMP_CONF}"
  if [[ -n "${OLD_TARGET}" ]]; then link_site "${OLD_TARGET}"; fi
  die "生成的配置没有绑定回环地址，已回滚"
fi

install -D -m 0644 "${TMP_CONF}" "${CONF_PATH}"
rm -f "${TMP_CONF}"

if ! nginx -t; then
  cp -a "${OLD_CONF}" "${CONF_PATH}"
  if [[ -n "${OLD_TARGET}" ]]; then link_site "${OLD_TARGET}"; fi
  rm -f "${OLD_CONF}"
  die "nginx -t 未通过，配置与站点目录都已回滚"
fi
rm -f "${OLD_CONF}"

systemctl reload nginx 2>/dev/null || systemctl restart nginx

# ------------------------------------------------------------ 自检
LISTEN_PORT="${LISTEN##*:}"
if command -v ss >/dev/null 2>&1; then
  BOUND="$(ss -lntH "sport = :${LISTEN_PORT}" 2>/dev/null || true)"
  if [[ -n "${BOUND}" ]] && echo "${BOUND}" | grep -qvE "127\.0\.0\.1:${LISTEN_PORT}|\[::1\]:${LISTEN_PORT}"; then
    warn "端口 ${LISTEN_PORT} 上出现了非回环监听："
    echo "${BOUND}" >&2
  else
    log "端口隔离正常：${LISTEN_PORT} 只监听回环"
  fi
fi

CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 -k \
  --resolve "${DOMAIN}:443:127.0.0.1" "https://${DOMAIN}/" 2>/dev/null || true)"
if [[ "${CODE}" == "200" ]]; then
  log "本机访问 https://${DOMAIN}/ 返回 200"
else
  warn "本机访问 https://${DOMAIN}/ 返回 ${CODE:-失败}；检查 systemctl status xray 与 nginx 日志"
fi

# ------------------------------------------------------------ 清理旧版本
COUNT="$(ls -1d "${RELEASES}"/*/ 2>/dev/null | wc -l || echo 0)"
if [[ "${COUNT}" -gt "${KEEP}" ]]; then
  ls -1dt "${RELEASES}"/*/ | tail -n +"$((KEEP + 1))" | while read -r old; do
    rm -rf "${old}"
  done
  log "已清理旧版本，保留最近 ${KEEP} 个"
fi

cat <<EOF

============================================================
 回落站点已部署
============================================================
 域名      ${DOMAIN}
 根目录    ${SITE_DIR} -> ${RELEASE}
 监听      ${LISTEN}（仅回环）
 配置      ${CONF_PATH}

 改完内容重新上传后，再跑一次本脚本即可；回滚：
   sudo bash deploy/nav-site.sh --rollback
============================================================
EOF
