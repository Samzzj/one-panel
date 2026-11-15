#!/usr/bin/env bash
# ------------------------------------------------------------
# 9443 管理入口的网络级白名单（nftables + nginx 双层）
#
#   sudo bash deploy/panel-guard.sh sync           # 从面板设置同步
#   sudo bash deploy/panel-guard.sh add 1.2.3.4    # 永久放行
#   sudo bash deploy/panel-guard.sh add 1.2.3.0/24 --ttl 2h
#   sudo bash deploy/panel-guard.sh del 1.2.3.4
#   sudo bash deploy/panel-guard.sh list
#   sudo bash deploy/panel-guard.sh status
#
# 白名单真源在面板设置里（access_allowlist），这里只做单向落地：
#   panel.db + manual.list -> nftables 集合 + nginx geo 列表
# 面板进程本身不需要任何特权，也不需要 sudo。
#
# 语义与面板应用层一致：白名单为空 = 不限制；非空 = 只允许列表内地址。
# 回环地址永远放行（SSH 隧道走 127.0.0.1）。
#
# 为什么两层都要：nft 在 TCP 层直接丢包，扫描器看不到端口、看不到证书；
# nginx 的 geo 是防火墙规则丢失（或 OpenVZ 无 nft）时的兜底。
# ------------------------------------------------------------
set -euo pipefail

ACTION="${1:-sync}"
ARG="${2:-}"
TTL=""
if [[ "${3:-}" == "--ttl" ]]; then
  TTL="${4:-}"
fi

DATA_DIR="${DATA_DIR:-/var/lib/reality-panel}"
DB="${DB:-${DATA_DIR}/panel.db}"
NGINX_PORT="${NGINX_PORT:-9443}"
ALLOW_CONF="${ALLOW_CONF:-/etc/nginx/conf.d/panel-guard.conf}"
MANUAL_FILE="${MANUAL_FILE:-/etc/panel-guard.d/manual.list}"
NFT_TABLE="panel_guard"

log()  { printf '\033[36m[panel-guard]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[panel-guard]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m[panel-guard]\033[0m %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || die "请用 root 运行"
PY="$(command -v python3 || true)"
[[ -n "${PY}" ]] || die "缺少 python3"

PARSER="$(cat <<'PY'
import ipaddress
import os
import sqlite3
import sys
import time

db, manual = sys.argv[1], sys.argv[2]
now = int(time.time())
items = []


def push(raw):
    raw = (raw or "").strip().lower()
    if not raw or raw.startswith("#"):
        return
    try:
        items.append(str(ipaddress.ip_network(raw, strict=False)))
    except ValueError:
        return


if os.path.exists(db):
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
        row = conn.execute("SELECT value FROM meta WHERE key='access_allowlist'").fetchone()
        conn.close()
        text = row[0] if row else ""
        for line in text.replace(",", "\n").replace(";", "\n").splitlines():
            push(line)
    except sqlite3.Error:
        pass

if os.path.exists(manual):
    with open(manual, "r", encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if not parts:
                continue
            expires = 0
            for part in parts[1:]:
                if part.startswith("expires="):
                    try:
                        expires = int(part.split("=", 1)[1])
                    except ValueError:
                        expires = 0
            if expires and expires <= now:
                continue
            push(parts[0])

seen = set()
out = []
for net in items:
    if net not in seen:
        seen.add(net)
        out.append(net)
print("\n".join(out))
PY
)"

collect() {
  PYTHONIOENCODING=utf-8 "${PY}" -c "${PARSER}" "${DB}" "${MANUAL_FILE}"
}

case "${ACTION}" in
  add)
    [[ -n "${ARG}" ]] || die "用法: panel-guard.sh add <IP 或 CIDR> [--ttl 1h]"
    install -d -m 0755 "$(dirname "${MANUAL_FILE}")"
    touch "${MANUAL_FILE}"
    EXPIRES=0
    if [[ -n "${TTL}" ]]; then
      SECS="$("${PY}" -c '
import re, sys
m = re.fullmatch(r"(\d+)([smhd])", sys.argv[1].strip())
if not m:
    sys.exit(1)
n = int(m.group(1))
print(n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)])
' "${TTL}" || true)"
      [[ -n "${SECS}" ]] || die "TTL 格式应为 30m / 2h / 1d"
      EXPIRES=$(( $(date +%s) + SECS ))
    fi
    echo "${ARG} expires=${EXPIRES}" >>"${MANUAL_FILE}"
    log "已加入 ${ARG}$([[ -n "${TTL}" ]] && echo "（${TTL} 后失效）")"
    ;;
  del)
    [[ -n "${ARG}" ]] || die "用法: panel-guard.sh del <IP 或 CIDR>"
    if [[ -f "${MANUAL_FILE}" ]]; then
      PATTERN="$(printf '%s' "${ARG}" | sed 's/[.[\*^$()+?{}|]/\\&/g')"
      grep -viE "^[[:space:]]*${PATTERN}([[:space:]]|$)" "${MANUAL_FILE}" >"${MANUAL_FILE}.tmp" || true
      mv "${MANUAL_FILE}.tmp" "${MANUAL_FILE}"
    fi
    warn "手工列表已删；如果它还在面板设置里，下次同步会重新生效"
    ;;
  list)
    collect
    exit 0
    ;;
  status)
    echo "nft 规则："
    nft list table inet "${NFT_TABLE}" 2>/dev/null || echo "  （未加载）"
    echo
    echo "nginx geo 列表："
    sed -n '/geo \$panel_allowed/,/^}/p' "${ALLOW_CONF}" 2>/dev/null || echo "  （未生成）"
    exit 0
    ;;
  sync) ;;
  *) die "未知动作：${ACTION}（可用 sync/add/del/list/status）" ;;
esac

# ------------------------------------------------------------------ 同步
ALLOWED="$(collect || true)"
COUNT=0
if [[ -n "${ALLOWED}" ]]; then
  COUNT="$(printf '%s\n' "${ALLOWED}" | grep -c . || true)"
fi

# ---- nginx geo ----
TMP="$(mktemp)"
{
  echo "# 由 deploy/panel-guard.sh 生成 —— 请勿手改"
  echo "# 真源：面板设置 -> 访问白名单（access_allowlist）"
  if [[ "${COUNT}" -eq 0 ]]; then
    echo "# 白名单为空：不限制（与面板应用层语义一致）"
    echo 'geo $panel_allowed {'
    echo '    default 1;'
  else
    echo 'geo $panel_allowed {'
    echo '    default 0;'
    echo '    127.0.0.1 1;'
    echo '    ::1 1;'
    while read -r cidr; do
      if [[ -n "${cidr}" ]]; then
        echo "    ${cidr} 1;"
      fi
    done <<<"${ALLOWED}"
  fi
  echo '}'
} >"${TMP}"

CHANGED=0
if [[ ! -f "${ALLOW_CONF}" ]] || ! cmp -s "${TMP}" "${ALLOW_CONF}"; then
  CHANGED=1
fi

if [[ "${CHANGED}" -eq 1 ]]; then
  install -D -m 0644 "${TMP}" "${ALLOW_CONF}"
  if ! nginx -t >/dev/null 2>&1; then
    rm -f "${ALLOW_CONF}"
    rm -f "${TMP}"
    die "写入 ${ALLOW_CONF} 后 nginx -t 未通过，已移除该文件"
  fi
  if systemctl is-active --quiet nginx 2>/dev/null; then
    systemctl reload nginx 2>/dev/null || warn "nginx reload 失败"
  fi
else
  rm -f "${TMP}"
fi

# ---- nftables ----
if command -v nft >/dev/null 2>&1 && nft list ruleset >/dev/null 2>&1; then
  ELEMS4="127.0.0.1"
  ELEMS6="::1"
  if [[ "${COUNT}" -gt 0 ]]; then
    while read -r cidr; do
      if [[ -z "${cidr}" ]]; then continue; fi
      if [[ "${cidr}" == *:* ]]; then
        ELEMS6="${ELEMS6}, ${cidr}"
      else
        ELEMS4="${ELEMS4}, ${cidr}"
      fi
    done <<<"${ALLOWED}"
  fi

  NFT_FILE="$(mktemp)"
  {
    echo "destroy table inet ${NFT_TABLE}"
    echo "table inet ${NFT_TABLE} {"
    echo "    set allow4 {"
    echo "        type ipv4_addr"
    echo "        flags interval"
    echo "        elements = { ${ELEMS4} }"
    echo "    }"
    echo "    set allow6 {"
    echo "        type ipv6_addr"
    echo "        flags interval"
    echo "        elements = { ${ELEMS6} }"
    echo "    }"
    echo "    chain input {"
    echo "        type filter hook input priority -5; policy accept;"
    if [[ "${COUNT}" -gt 0 ]]; then
      echo "        tcp dport ${NGINX_PORT} ip  saddr @allow4 accept"
      echo "        tcp dport ${NGINX_PORT} ip6 saddr @allow6 accept"
      echo "        tcp dport ${NGINX_PORT} drop"
    fi
    echo "    }"
    echo "}"
  } >"${NFT_FILE}"

  LAST_NFT="/etc/panel-guard.d/last.nft"
  if [[ -f "${LAST_NFT}" ]] && cmp -s "${NFT_FILE}" "${LAST_NFT}"; then
    if [[ "${COUNT}" -eq 0 ]]; then
      log "nft：白名单为空，未启用丢包规则"
    else
      log "nft：规则无变化（${COUNT} 条白名单）"
    fi
    rm -f "${NFT_FILE}"
  else
    APPLIED=0
    if nft -f "${NFT_FILE}" 2>/dev/null; then
      APPLIED=1
    else
      # 老版本 nft 不认识 destroy，退化成先删后建
      nft delete table inet "${NFT_TABLE}" 2>/dev/null || true
      if nft -f "${NFT_FILE}" 2>/dev/null; then
        APPLIED=1
      fi
    fi

    if [[ "${APPLIED}" -eq 1 ]]; then
      install -D -m 0644 "${NFT_FILE}" "${LAST_NFT}"
      if [[ "${COUNT}" -eq 0 ]]; then
        log "nft：白名单为空，未启用丢包规则"
      else
        log "nft：${NGINX_PORT} 仅放行 ${COUNT} 条白名单 + 回环，其余 DROP"
      fi
    else
      warn "nft 应用失败（OpenVZ/LXC 常见），仅保留 nginx 层拦截"
    fi
    rm -f "${NFT_FILE}"
  fi
else
  warn "本机没有可用的 nftables，仅保留 nginx 层拦截（端口可见，但拿不到响应）"
fi

log "同步完成：白名单 ${COUNT} 条"
