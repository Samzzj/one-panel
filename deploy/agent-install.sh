#!/usr/bin/env bash
# ------------------------------------------------------------
# One Panel 节点 Agent 安装脚本
#
# 在【被管理的服务器】上执行（不是面板那台）：
#
#   curl -fsSL https://raw.githubusercontent.com/Samzzj/one-panel/main/deploy/agent-install.sh \
#     | sudo bash -s -- --token <面板生成的令牌>
#
# 可选参数：
#   --port 8787            监听端口
#   --bind 0.0.0.0         监听地址（建议配合防火墙只放行面板 IP）
#   --xray-config PATH     默认 /usr/local/etc/xray/config.json
#   --nginx-dir PATH       默认 /etc/nginx/conf.d
#   --no-xray              不自动安装 Xray
#   --with-nginx           顺便安装 nginx（自偷自需要）
#   --repo URL             agent.py 的下载地址前缀
# ------------------------------------------------------------
set -euo pipefail

TOKEN="${AGENT_TOKEN:-}"
PORT="${AGENT_PORT:-8787}"
BIND="${AGENT_BIND:-0.0.0.0}"
XRAY_CONFIG="${AGENT_XRAY_CONFIG:-/usr/local/etc/xray/config.json}"
NGINX_DIR="${AGENT_NGINX_DIR:-/etc/nginx/conf.d}"
INSTALL_XRAY=1
WITH_NGINX=0
RAW_BASE="${RAW_BASE:-https://raw.githubusercontent.com/Samzzj/one-panel/main}"
APP_DIR="/opt/one-panel-agent"
ENV_FILE="/etc/one-panel-agent.env"
UNIT="/etc/systemd/system/one-panel-agent.service"

log()  { printf '\033[36m[agent]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[agent]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m[agent]\033[0m %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --token) TOKEN="${2:?}"; shift 2 ;;
    --port) PORT="${2:?}"; shift 2 ;;
    --bind) BIND="${2:?}"; shift 2 ;;
    --xray-config) XRAY_CONFIG="${2:?}"; shift 2 ;;
    --nginx-dir) NGINX_DIR="${2:?}"; shift 2 ;;
    --repo) RAW_BASE="${2%/}"; shift 2 ;;
    --no-xray) INSTALL_XRAY=0; shift ;;
    --with-nginx) WITH_NGINX=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) die "未知参数: $1" ;;
  esac
done

[[ "${EUID}" -eq 0 ]] || die "请用 root 运行"
[[ -n "${TOKEN}" ]] || die "缺少 --token（面板「服务器」页面会生成）"

command -v python3 >/dev/null 2>&1 || die "缺少 python3"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)' \
  || die "需要 Python 3.8+"

if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq || true
  apt-get install -y -qq curl ca-certificates >/dev/null || warn "依赖安装失败"
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y -q curl ca-certificates >/dev/null || warn "依赖安装失败"
fi

# ------------------------------------------------------------ Xray
if [[ "${INSTALL_XRAY}" -eq 1 ]] && ! command -v xray >/dev/null 2>&1; then
  log "安装 Xray-core"
  bash -c "$(curl -fsSL https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install || \
    warn "Xray 安装失败，可稍后手动安装"
fi
systemctl enable --now xray 2>/dev/null || warn "无法启动 xray 服务"

if [[ "${WITH_NGINX}" -eq 1 ]] && ! command -v nginx >/dev/null 2>&1; then
  log "安装 nginx"
  if command -v apt-get >/dev/null 2>&1; then
    apt-get install -y -qq nginx >/dev/null || warn "nginx 安装失败"
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y -q nginx >/dev/null || warn "nginx 安装失败"
  fi
  systemctl enable --now nginx 2>/dev/null || true
fi

if [[ "${WITH_NGINX}" -eq 1 ]] && ! command -v certbot >/dev/null 2>&1; then
  log "安装 certbot（节点一键签证书用）"
  if command -v apt-get >/dev/null 2>&1; then
    apt-get install -y -qq certbot >/dev/null || warn "certbot 安装失败，可稍后手动安装"
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y -q certbot >/dev/null || warn "certbot 安装失败，可稍后手动安装"
  fi
fi

install -d -m 0755 "${APP_DIR}"
install -d -m 0775 "$(dirname "${XRAY_CONFIG}")"
install -d -m 0755 "${NGINX_DIR}"
install -d -m 0755 /var/log/xray
install -d -m 0755 /etc/letsencrypt /var/lib/letsencrypt /var/log/letsencrypt

# ------------------------------------------------------------ 下载 agent
log "下载 agent.py"
TMP_AGENT="$(mktemp)"
if ! curl -fsSL --max-time 60 "${RAW_BASE}/agent.py" -o "${TMP_AGENT}"; then
  rm -f "${TMP_AGENT}"
  die "下载 agent.py 失败；可以手动 scp agent.py 到 ${APP_DIR}/agent.py 后重试"
fi
install -m 0755 "${TMP_AGENT}" "${APP_DIR}/agent.py"
rm -f "${TMP_AGENT}"

# ------------------------------------------------------------ 配置
umask 077
cat >"${ENV_FILE}" <<EOF
AGENT_TOKEN=${TOKEN}
AGENT_BIND=${BIND}
AGENT_PORT=${PORT}
AGENT_XRAY_CONFIG=${XRAY_CONFIG}
AGENT_NGINX_DIR=${NGINX_DIR}
EOF
chmod 600 "${ENV_FILE}"

cat >"${UNIT}" <<EOF
[Unit]
Description=One Panel Node Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
EnvironmentFile=${ENV_FILE}
ExecStart=/usr/bin/env python3 ${APP_DIR}/agent.py
Restart=always
RestartSec=3

ProtectSystem=strict
PrivateTmp=true
ReadWritePaths=${APP_DIR} ${NGINX_DIR} $(dirname "${XRAY_CONFIG}") /var/lib/nginx /var/log/nginx /var/log/xray /etc/letsencrypt /var/lib/letsencrypt /var/log/letsencrypt /run

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now one-panel-agent
sleep 1

if systemctl is-active --quiet one-panel-agent; then
  log "Agent 已启动，监听 ${BIND}:${PORT}"
else
  warn "Agent 启动失败，请查看：journalctl -u one-panel-agent -n 50 --no-pager"
fi

cat <<EOF

============================================================
 节点 Agent 安装完成
============================================================
 端口        ${PORT}
 Xray 配置   ${XRAY_CONFIG}
 Nginx 目录  ${NGINX_DIR}

 回到面板「服务器」页面，点「测试连接」。
 建议用防火墙把 ${PORT} 只放行面板所在服务器的 IP，例如：
   ufw allow from <面板IP> to any port ${PORT} proto tcp

 常用命令：
   systemctl status one-panel-agent
   journalctl -u one-panel-agent -f
============================================================
EOF
