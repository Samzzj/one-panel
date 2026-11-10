#!/usr/bin/env bash
# ------------------------------------------------------------
# One Panel 节点 Agent 安装脚本
#
# 在【被管理的服务器】上执行（不是面板那台）：
#
#   curl -4 -fsSL --connect-timeout 10 --max-time 60 https://raw.githubusercontent.com/Samzzj/one-panel/main/deploy/agent-install.sh \
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
#   --agent-file PATH      用本地 agent.py（离线安装）
#   --xray-binary PATH     用本地 Xray 二进制或 zip（离线安装）
#   --xray-url URL         从自定义地址下载 Xray zip（GitHub 不通时用）
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
AGENT_FILE="${AGENT_FILE:-}"
XRAY_BINARY="${AGENT_XRAY_BINARY:-}"
XRAY_URL="${AGENT_XRAY_URL:-}"
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
    --agent-file) AGENT_FILE="${2:?}"; shift 2 ;;
    --xray-binary) XRAY_BINARY="${2:?}"; shift 2 ;;
    --xray-url) XRAY_URL="${2:?}"; shift 2 ;;
    --no-xray) INSTALL_XRAY=0; shift ;;
    --with-nginx) WITH_NGINX=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) die "未知参数: $1" ;;
  esac
done

[[ "${EUID}" -eq 0 ]] || die "请用 root 运行"
[[ -n "${TOKEN}" ]] || die "缺少 --token（面板「服务器」页面会生成）"

# 离线包布局：kit/agent.py + kit/deploy/agent-install.sh
if [[ -z "${AGENT_FILE}" && -n "${BASH_SOURCE[0]:-}" ]]; then
  SIBLING_AGENT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/agent.py"
  [[ -f "${SIBLING_AGENT}" ]] && AGENT_FILE="${SIBLING_AGENT}"
fi

command -v python3 >/dev/null 2>&1 || die "缺少 python3"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)' \
  || die "需要 Python 3.8+"

if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get -o Acquire::ForceIPv4=true update -qq || true
  timeout 180 apt-get -o Acquire::ForceIPv4=true install -y -qq curl ca-certificates >/dev/null || \
    warn "依赖安装失败或超时"
elif command -v dnf >/dev/null 2>&1; then
  timeout 180 dnf --setopt=ip_resolve=4 install -y -q curl ca-certificates >/dev/null || \
    warn "依赖安装失败或超时"
fi

# ------------------------------------------------------------ Xray
ensure_xray_user() {
  id -u xray >/dev/null 2>&1 || \
    useradd --system --no-create-home --shell /usr/sbin/nologin xray
}

write_xray_unit() {
  [[ -f /etc/systemd/system/xray.service ]] && return 0
  ensure_xray_user
  cat >/etc/systemd/system/xray.service <<EOF
[Unit]
Description=Xray Service
After=network.target nss-lookup.target

[Service]
User=xray
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
NoNewPrivileges=true
ExecStart=/usr/local/bin/xray run -config ${XRAY_CONFIG}
Restart=on-failure
RestartSec=3
LimitNOFILE=1000000

[Install]
WantedBy=multi-user.target
EOF
}

install_xray_payload() {
  local src="$1" tmp
  [[ -f "${src}" ]] || die "Xray 文件不存在：${src}"
  if [[ "${src}" == *.zip ]]; then
    tmp="$(mktemp -d)"
    if ! python3 -m zipfile -e "${src}" "${tmp}"; then
      rm -rf "${tmp}"
      die "解压 Xray zip 失败：${src}"
    fi
    [[ -f "${tmp}/xray" ]] || { rm -rf "${tmp}"; die "zip 里没有 xray 二进制"; }
    install -m 0755 "${tmp}/xray" /usr/local/bin/xray
    install -d -m 0755 /usr/local/share/xray
    [[ -f "${tmp}/geoip.dat" ]] && install -m 0644 "${tmp}/geoip.dat" /usr/local/share/xray/geoip.dat
    [[ -f "${tmp}/geosite.dat" ]] && install -m 0644 "${tmp}/geosite.dat" /usr/local/share/xray/geosite.dat
    rm -rf "${tmp}"
  else
    install -m 0755 "${src}" /usr/local/bin/xray
  fi
}

if [[ "${INSTALL_XRAY}" -eq 1 ]] && ! command -v xray >/dev/null 2>&1; then
  if [[ -n "${XRAY_BINARY}" ]]; then
    log "安装本地 Xray：${XRAY_BINARY}"
    install_xray_payload "${XRAY_BINARY}"
  elif [[ -n "${XRAY_URL}" ]]; then
    log "从自定义地址下载 Xray"
    XRAY_DIR="$(mktemp -d)"
    XRAY_TMP="${XRAY_DIR}/Xray.zip"
    if ! curl -4 -fsSL --connect-timeout 10 --max-time 180 "${XRAY_URL}" -o "${XRAY_TMP}"; then
      rm -rf "${XRAY_DIR}"
      die "下载 Xray 失败：${XRAY_URL}"
    fi
    install_xray_payload "${XRAY_TMP}"
    rm -rf "${XRAY_DIR}"
  else
    log "安装 Xray-core"
    for attempt in 1 2 3; do
      script="$(curl -4 -fsSL --connect-timeout 10 --max-time 60 https://github.com/XTLS/Xray-install/raw/main/install-release.sh || true)"
      if [[ -n "${script}" ]] && bash -c "${script}" @ install; then
        break
      fi
      warn "Xray 安装失败（第 ${attempt}/3 次，常见原因是 GitHub 504），10 秒后重试"
      sleep 10
    done
    command -v xray >/dev/null 2>&1 || warn "Xray 仍未安装成功；可用 --xray-binary 或 --xray-url 离线安装"
  fi
fi

if command -v xray >/dev/null 2>&1; then
  ensure_xray_user
  write_xray_unit
fi

# 新版 Xray 安装脚本不一定会生成 config.json；没有配置服务会直接启动失败
if command -v xray >/dev/null 2>&1 && [[ ! -f "${XRAY_CONFIG}" ]]; then
  log "生成最小 Xray 配置（面板下发后会覆盖）"
  install -d -m 0775 "$(dirname "${XRAY_CONFIG}")"
  cat > "${XRAY_CONFIG}" <<'EOF'
{
  "log": { "loglevel": "warning" },
  "inbounds": [
    {
      "listen": "127.0.0.1",
      "port": 1080,
      "protocol": "socks",
      "settings": { "auth": "noauth", "udp": false }
    }
  ],
  "outbounds": [ { "protocol": "freedom" } ]
}
EOF
  chmod 644 "${XRAY_CONFIG}"
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
install -d -m 0755 /var/lib/nginx /var/log/nginx
install -d -m 0755 /etc/letsencrypt /var/lib/letsencrypt /var/log/letsencrypt

# ------------------------------------------------------------ 安装 agent
if [[ -n "${AGENT_FILE}" ]]; then
  log "使用本地 agent.py：${AGENT_FILE}"
  [[ -f "${AGENT_FILE}" ]] || die "agent.py 不存在：${AGENT_FILE}"
  install -m 0755 "${AGENT_FILE}" "${APP_DIR}/agent.py"
else
  log "下载 agent.py"
  TMP_AGENT="$(mktemp)"
  if ! curl -4 -fsSL --connect-timeout 10 --max-time 60 "${RAW_BASE}/agent.py" -o "${TMP_AGENT}"; then
    rm -f "${TMP_AGENT}"
    die "下载 agent.py 失败；可以用 --agent-file 指定本地文件，或 --repo file:///目录"
  fi
  install -m 0755 "${TMP_AGENT}" "${APP_DIR}/agent.py"
  rm -f "${TMP_AGENT}"
fi

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
systemctl enable one-panel-agent >/dev/null 2>&1 || true
# 重装时服务可能已在运行，enable --now 不会重启，必须显式 restart
systemctl restart one-panel-agent
sleep 1
systemctl is-active --quiet one-panel-agent || warn "agent 没有启动成功，请执行：systemctl status one-panel-agent --no-pager"

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
