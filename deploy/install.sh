#!/usr/bin/env bash
# ------------------------------------------------------------
# Reality Panel 安装脚本
#
#   sudo bash deploy/install.sh                  # 默认 8080 端口，安装/更新面板
#   sudo bash deploy/install.sh --no-xray        # 不安装 Xray
#   sudo bash deploy/install.sh --uninstall      # 卸载（保留数据目录）
#
# 做的事：装依赖 -> 建系统用户 -> 复制程序 -> 写 systemd/sudoers -> 启动
# ------------------------------------------------------------
set -euo pipefail

APP_DIR="/opt/reality-panel"
DATA_DIR="/var/lib/reality-panel"
SERVICE_USER="reality-panel"
SERVICE_NAME="reality-panel"
PANEL_PORT="8080"
XRAY_SERVICE="xray"
INSTALL_XRAY=1
UNINSTALL=0

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log()  { printf '\033[36m[panel]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[panel]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m[panel]\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,9p' "$0"
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PANEL_PORT="${2:?}"; shift 2 ;;
    --dir) APP_DIR="${2:?}"; shift 2 ;;
    --xray-service) XRAY_SERVICE="${2:?}"; shift 2 ;;
    --no-xray) INSTALL_XRAY=0; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help) usage ;;
    *) die "未知参数: $1" ;;
  esac
done

[[ "${EUID}" -eq 0 ]] || die "请用 root 运行：sudo bash deploy/install.sh"

# ------------------------------------------------------------ 卸载
if [[ "${UNINSTALL}" -eq 1 ]]; then
  log "停止并移除 ${SERVICE_NAME}"
  systemctl disable --now "${SERVICE_NAME}" 2>/dev/null || true
  systemctl disable --now "${SERVICE_NAME}-sweep.timer" 2>/dev/null || true
  rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
  rm -f "/etc/systemd/system/${SERVICE_NAME}-sweep.service"
  rm -f "/etc/systemd/system/${SERVICE_NAME}-sweep.timer"
  rm -f "/etc/sudoers.d/${SERVICE_NAME}"
  systemctl daemon-reload || true
  log "已卸载。数据仍保留在 ${DATA_DIR}（确认无用后可手动删除）"
  exit 0
fi

# ------------------------------------------------------------ 包管理
missing=0
for cmd in python3 curl nginx sudo openssl; do
  command -v "${cmd}" >/dev/null 2>&1 || missing=1
done

if [[ "${missing}" -eq 0 ]]; then
  log "依赖已齐全，跳过 apt/dnf"
else
  log "安装缺失的系统依赖"
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get -o Acquire::ForceIPv4=true update -qq || warn "apt-get update 未完成（常见原因是 unattended-upgrades 占用锁），继续"
    if ! timeout 240 apt-get -o Acquire::ForceIPv4=true install -y -qq python3 curl ca-certificates openssl nginx sudo >/dev/null; then
      warn "apt 被其他进程占用或超时，10 秒后重试一次"
      sleep 10
      timeout 240 apt-get -o Acquire::ForceIPv4=true install -y -qq python3 curl ca-certificates openssl nginx sudo >/dev/null || \
        warn "依赖安装未完成；如果面板能正常启动可以忽略"
    fi
  elif command -v dnf >/dev/null 2>&1; then
    timeout 240 dnf --setopt=ip_resolve=4 install -y -q python3 curl ca-certificates openssl nginx sudo >/dev/null || \
      warn "依赖安装未完成；如果面板能正常启动可以忽略"
  elif command -v yum >/dev/null 2>&1; then
    timeout 240 yum install -y -q python3 curl ca-certificates openssl nginx sudo >/dev/null || \
      warn "依赖安装未完成；如果面板能正常启动可以忽略"
  else
    warn "未识别的包管理器，请自行确保 python3 >= 3.8 与 sudo 已安装"
  fi
fi

command -v python3 >/dev/null 2>&1 || die "缺少 python3"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)' \
  || die "需要 Python 3.8 及以上版本"

# ------------------------------------------------------------ 用户与目录
if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  log "创建系统用户 ${SERVICE_USER}"
  useradd --system --home-dir "${DATA_DIR}" --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

install -d -m 0755 "${APP_DIR}"
install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 0700 "${DATA_DIR}"

# ------------------------------------------------------------ 复制程序
if [[ "$(readlink -f "${SRC_DIR}")" != "$(readlink -f "${APP_DIR}")" ]]; then
  log "复制程序到 ${APP_DIR}"
  rm -rf "${APP_DIR}/panel" "${APP_DIR}/app.py" "${APP_DIR}/deploy"
  cp -a "${SRC_DIR}/app.py" "${SRC_DIR}/agent.py" "${SRC_DIR}/panel" "${SRC_DIR}/deploy" "${APP_DIR}/"
  [[ -f "${SRC_DIR}/README.md" ]] && cp -a "${SRC_DIR}/README.md" "${APP_DIR}/" || true
  [[ -f "${SRC_DIR}/LICENSE" ]] && cp -a "${SRC_DIR}/LICENSE" "${APP_DIR}/" || true
fi
chmod -R go-w "${APP_DIR}"
chmod +x "${APP_DIR}/app.py" "${APP_DIR}"/deploy/*.sh 2>/dev/null || true

# ------------------------------------------------------------ Xray
if [[ "${INSTALL_XRAY}" -eq 1 ]]; then
  if command -v xray >/dev/null 2>&1; then
    log "已安装 Xray: $(xray version 2>/dev/null | head -n1)"
  else
    log "安装 Xray-core（官方脚本，失败自动重试 3 次）"
    xray_installed=0
    for attempt in 1 2 3; do
      script="$(curl -4 -fsSL --connect-timeout 10 --max-time 60 https://github.com/XTLS/Xray-install/raw/main/install-release.sh || true)"
      if [[ -n "${script}" ]] && bash -c "${script}" @ install; then
        xray_installed=1
        break
      fi
      warn "Xray 安装失败（第 ${attempt}/3 次），10 秒后重试"
      sleep 10
    done
    if [[ "${xray_installed}" -eq 1 ]]; then
      log "Xray 安装完成"
    else
      warn "Xray 安装失败，可稍后手动安装；面板仍可启动并生成配置"
    fi
  fi

  # 新版 Xray 安装脚本不一定生成 config.json，没有配置服务会直接启动失败
  if command -v xray >/dev/null 2>&1 && [[ ! -f /usr/local/etc/xray/config.json ]]; then
    log "生成最小 Xray 配置（面板下发后会覆盖）"
    install -d -m 0775 /usr/local/etc/xray
    cat >/usr/local/etc/xray/config.json <<'EOF'
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
    chmod 644 /usr/local/etc/xray/config.json
  fi

  # 有些机器只有 xray 二进制，没有 systemd 服务；补一个，否则永远启动不了
  if command -v xray >/dev/null 2>&1; then
    getent group xray >/dev/null 2>&1 || groupadd --system xray 2>/dev/null || true
    id -u xray >/dev/null 2>&1 || \
      useradd --system --gid xray --no-create-home --shell /usr/sbin/nologin xray 2>/dev/null || true

    if ! systemctl cat "${XRAY_SERVICE}.service" >/dev/null 2>&1; then
      log "写入 Xray systemd 服务"
      XRAY_BIN="$(command -v xray)"
      cat >"/etc/systemd/system/${XRAY_SERVICE}.service" <<EOF
[Unit]
Description=Xray Service
Documentation=https://xtls.github.io/
After=network.target nss-lookup.target

[Service]
User=xray
Group=xray
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_RAW
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_RAW
NoNewPrivileges=yes
ExecStart=${XRAY_BIN} run -config /usr/local/etc/xray/config.json
Restart=on-failure
RestartPreventExitStatus=23
LimitNPROC=10000
LimitNOFILE=1000000
RuntimeDirectory=xray
RuntimeDirectoryMode=0755

[Install]
WantedBy=multi-user.target
EOF
      systemctl daemon-reload
    fi
  fi

  systemctl enable --now "${XRAY_SERVICE}" 2>/dev/null || \
    warn "无法启动 ${XRAY_SERVICE} 服务，请稍后手动检查"
fi

# 面板需要写入 Xray 配置目录
install -d -m 0775 "/usr/local/etc/xray"
chgrp "${SERVICE_USER}" "/usr/local/etc/xray" 2>/dev/null || true
chmod 0775 "/usr/local/etc/xray" 2>/dev/null || true

# ------------------------------------------------------------ sudoers
SYSTEMCTL="$(command -v systemctl || echo /usr/bin/systemctl)"
SUDO_FILE="/etc/sudoers.d/${SERVICE_NAME}"
cat >"${SUDO_FILE}" <<EOF
# 允许面板重启 Xray（只这一条命令）
Defaults:${SERVICE_USER} !requiretty
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL} restart ${XRAY_SERVICE}
EOF
chmod 0440 "${SUDO_FILE}"
visudo -cf "${SUDO_FILE}" >/dev/null || die "sudoers 校验失败"

# ------------------------------------------------------------ systemd
log "写入 systemd 服务"
cat >"/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Reality Panel (VLESS + REALITY)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
Environment=REALITY_PANEL_DATA=${DATA_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONUTF8=1
ExecStart=/usr/bin/env python3 ${APP_DIR}/app.py --host 127.0.0.1 --port ${PANEL_PORT}
Restart=on-failure
RestartSec=3

# 只允许写数据目录与 Xray 配置目录
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=${DATA_DIR} /usr/local/etc/xray

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}" >/dev/null 2>&1 || true
# enable --now 对已在运行的服务不会重启，必须显式 restart 才能加载新代码
systemctl restart "${SERVICE_NAME}" || warn "面板重启失败"
sleep 1

if ! systemctl is-active --quiet "${SERVICE_NAME}"; then
  warn "面板没有启动成功，请执行：systemctl status ${SERVICE_NAME} --no-pager"
else
  RUN_VERSION=""
  for _ in 1 2 3 4 5; do
    RUN_VERSION="$(curl -s --max-time 3 "http://127.0.0.1:${PANEL_PORT}/api/bootstrap" 2>/dev/null \
      | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version",""))' 2>/dev/null || true)"
    [[ -n "${RUN_VERSION}" ]] && break
    sleep 1
  done
  if [[ -n "${RUN_VERSION}" ]]; then
    log "面板已重启，运行版本 ${RUN_VERSION}"
  else
    warn "面板进程已启动，但读取运行版本失败；请检查 127.0.0.1:${PANEL_PORT}"
  fi
fi

# 每 10 分钟检查一次过期 / 超额订阅；有变化才重启 Xray
cat >"/etc/systemd/system/${SERVICE_NAME}-sweep.service" <<EOF
[Unit]
Description=Reality Panel - disable expired or over-quota subscriptions
After=network.target

[Service]
Type=oneshot
User=${SERVICE_USER}
Group=${SERVICE_USER}
Environment=REALITY_PANEL_DATA=${DATA_DIR}
Environment=PYTHONUTF8=1
ExecStart=/usr/bin/env python3 ${APP_DIR}/app.py sweep
EOF

cat >"/etc/systemd/system/${SERVICE_NAME}-sweep.timer" <<EOF
[Unit]
Description=Run Reality Panel sweep every 10 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=10min
AccuracySec=1min

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}-sweep.timer" 2>/dev/null || \
  warn "定时 sweep 未启用，可手动执行 python3 ${APP_DIR}/app.py sweep"

sleep 1

if systemctl is-active --quiet "${SERVICE_NAME}"; then
  log "面板已启动"
else
  warn "面板启动失败，请查看：journalctl -u ${SERVICE_NAME} -n 50 --no-pager"
fi

IP="$(curl -4 -fsSL --max-time 5 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')"
cat <<EOF

============================================================
 Reality Panel 安装完成
============================================================
 本机地址   http://127.0.0.1:${PANEL_PORT}
 公网地址   http://${IP}:${PANEL_PORT}   (默认只监听回环，公网访问请用隧道)

 推荐用 SSH 隧道打开面板：
   ssh -L ${PANEL_PORT}:127.0.0.1:${PANEL_PORT} root@${IP}
 然后浏览器访问 http://127.0.0.1:${PANEL_PORT}

 不想用隧道？给面板加一个 HTTPS 入口（需要域名证书）：
   sudo bash ${APP_DIR}/deploy/panel-https.sh 你的域名
   然后浏览器打开 https://你的域名:9443

 接下来：
   1. 打开面板，创建管理员账号
   2. 在「设置」填写域名、Xray 配置路径等
   3. 申请证书并生成自偷自配置：
        sudo bash ${APP_DIR}/deploy/selfsteal.sh 你的域名 www.lovelive-anime.jp
      （若程序目录没有 deploy，可从仓库重新获取该脚本）
   4. 在「节点」创建 Vision / XHTTP 节点，再到「订阅用户」生成订阅

 常用命令：
   systemctl status ${SERVICE_NAME}
   journalctl -u ${SERVICE_NAME} -f
   systemctl list-timers | grep ${SERVICE_NAME}   # 过期订阅自动清理
   python3 ${APP_DIR}/app.py sweep                # 手动清理一次
============================================================
EOF
