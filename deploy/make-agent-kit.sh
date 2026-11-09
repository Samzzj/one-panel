#!/usr/bin/env bash
# ------------------------------------------------------------
# 在面板服务器上打包「节点离线安装包」
#
#   sudo bash deploy/make-agent-kit.sh
#   sudo bash deploy/make-agent-kit.sh /tmp/agent-kit.tar.gz
#
# 产物包含：agent.py、agent-install.sh、当前机器的 xray 二进制。
# 适合在 GitHub 下载不稳定的机器上安装节点，不需要联网拉 Xray。
#
# 注意：Xray 二进制与架构绑定；在 x86_64 面板上打的包只能用于 x86_64 节点。
# ------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCH="$(uname -m)"
OUT="${1:-${ROOT}/dist/one-panel-agent-kit-${ARCH}.tar.gz}"
XRAY_BIN="${XRAY_BIN:-/usr/local/bin/xray}"

log() { printf '\033[36m[kit]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[kit]\033[0m %s\n' "$*" >&2; exit 1; }

[[ -f "${ROOT}/agent.py" ]] || die "找不到 ${ROOT}/agent.py"
[[ -f "${ROOT}/deploy/agent-install.sh" ]] || die "找不到 agent-install.sh"
[[ -f "${XRAY_BIN}" ]] || die "找不到 Xray 二进制：${XRAY_BIN}（可设置 XRAY_BIN=...）"

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

KIT="${TMP}/one-panel-agent-kit"
mkdir -p "${KIT}/deploy" "${KIT}/xray"
install -m 0755 "${ROOT}/agent.py" "${KIT}/agent.py"
install -m 0755 "${ROOT}/deploy/agent-install.sh" "${KIT}/deploy/agent-install.sh"
install -m 0755 "${XRAY_BIN}" "${KIT}/xray/xray"

cat >"${KIT}/README.txt" <<EOF
One Panel 节点离线安装包（${ARCH}）

在目标机器上执行：

  tar xzf one-panel-agent-kit-${ARCH}.tar.gz -C /root
  sudo bash /root/one-panel-agent-kit/deploy/agent-install.sh \\
    --token <面板生成的令牌> \\
    --with-nginx \\
    --xray-binary /root/one-panel-agent-kit/xray/xray

如果目标机器架构不是 ${ARCH}，这个包里的 xray 不能直接用。
EOF

mkdir -p "$(dirname "${OUT}")"
tar czf "${OUT}" -C "${TMP}" one-panel-agent-kit
log "已生成：${OUT}"
log "架构：${ARCH}"
log "大小：$(du -h "${OUT}" | awk '{print $1}')"
echo
echo "复制到节点后执行："
echo "  tar xzf $(basename "${OUT}") -C /root"
echo "  sudo bash /root/one-panel-agent-kit/deploy/agent-install.sh \\"
echo "    --token <令牌> --with-nginx \\"
echo "    --xray-binary /root/one-panel-agent-kit/xray/xray"
