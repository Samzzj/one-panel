# Reality Panel

**零依赖的 VLESS + REALITY 管理面板**，内置「自己偷自己」部署向导。

一个 Python 文件起步的后台，不装框架、不装数据库服务、不编译前端：
`python3 app.py` 就能跑，配置全部写在 SQLite 里。支持 **VLESS + REALITY + Vision** 与
**VLESS + REALITY + XHTTP** 两种入站，一个订阅同时下发两种节点，输出
v2rayN / v2rayNG 的 Base64 订阅和 Clash / mihomo 的 YAML。

[![tests](https://github.com/Samzzj/one-panel/actions/workflows/ci.yml/badge.svg)](https://github.com/Samzzj/one-panel/actions/workflows/ci.yml)

```
客户端 (v2rayN / mihomo)
   │  ClientHello: SNI=node.example.com + REALITY 认证数据
   ▼
Xray :443 ── REALITY 校验通过 ──→ VLESS + Vision / XHTTP
   │
   │ 未通过校验（探针 / 浏览器）
   │ PROXY protocol v1
   ▼
Nginx 127.0.0.1:8003   ← 自有域名证书，本地 TLS
   ├── /sub/<token>  → 反代面板，提供订阅
   └── /             → 反代 https://www.lovelive-anime.jp（真实站点内容）
```

---

## 为什么是「自己偷自己」

REALITY 的特点是**自己不持有证书**：对没有通过认证的连接，它把 TLS 原样转交给
`dest`，由 `dest` 和对方完成握手。也就是说，探针看到的证书来自 `dest`。

- 偷别人的站点：证书是别人的，随时可能换站、封禁、上 CDN，你的节点跟着一起出问题；
  而且你的服务器会变成对方站点的端口转发器，可能被人白嫖流量。
- 偷自己：用自己的域名申请真证书，让本机 Nginx 持有；REALITY 的 `dest` 指向它，
  证书、TLS 版本、HTTP 响应都由你控制，探针看到的则是一个正常的网站。

所以链路必须是 **Xray → PROXY protocol → 本机 Nginx（本地 TLS + 证书）→ 反代真实站点**。
这也是本项目向导帮你生成的东西。

> 前提：你需要一个自己的域名，并能给它签发公网可信证书（Let's Encrypt 即可）。
> `www.lovelive-anime.jp` 只是「伪装内容」的上游，不需要拥有它。

---

## 功能

- **两种传输**：Vision（TCP + XTLS，低延迟）与 XHTTP（HTTP 传输，抗干扰 / 可挂 CDN），共用同一套 REALITY 回落链路
- **一个订阅多节点**：同一订阅可同时包含 Vision 与 XHTTP，客户端自动列成可选节点
- **分享链接 / 订阅**：标准 `vless://`、Base64 订阅、Clash(mihomo) YAML；按路径或 UA 自动识别客户端
- **二维码**：订阅地址一键出码，手机客户端扫码即导入
- **REALITY 密钥**：内置纯 Python X25519（已用 RFC 7748 官方向量验证），不依赖 xray 二进制
- **自偷自向导**：选择节点即可生成 Nginx 配置、证书命令、验证步骤
- **订阅入口复用 443**：Nginx 把 `/sub/` 反代回面板，客户端用同一个域名拉订阅
- **流量统计**：Xray Stats API 读取每用户上下行，按增量累计；timer 每 10 分钟自动采样
- **到期 / 额度**：采样 → 判断 → 停用 → 重载一条龙，不需要人工点
- **备份与审计**：JSON 导出 / 覆盖恢复，关键操作写入审计日志（自动保留 2000 条）
- **安全**：PBKDF2 密码、HttpOnly 会话、CSRF、登录限流、CSP、参数化 SQL
- **零依赖**：Python 3.8+ 标准库；前端原生 JS，无构建步骤

---

## 快速开始

### 环境

- 一台 VPS（Debian 12 / Ubuntu 22.04+ 最省事），1 核 512MB 足够
- 一个域名，例如 `node.example.com`，A 记录指向 VPS
- 开放 443（Xray）与 80（仅签发证书时用）

### 一键安装

```bash
git clone https://github.com/Samzzj/one-panel.git
cd one-panel

# 安装面板 + Xray + systemd 服务（不会动你的 nginx 配置）
sudo bash deploy/install.sh

# 签发证书 + 生成 Nginx 自偷自配置 + reload
sudo bash deploy/selfsteal.sh node.example.com
```

> 想给证书填通知邮箱：`sudo bash -c 'EMAIL=you@example.com bash deploy/selfsteal.sh node.example.com'`

然后按终端提示用 SSH 隧道打开面板：

```bash
ssh -L 8080:127.0.0.1:8080 root@你的服务器
# 浏览器访问 http://127.0.0.1:8080
```

首次打开会要求创建管理员账号（至少 10 位密码）。

### 面板里的四步

1. **设置** → 填写 `默认 SNI`（就是 `node.example.com`）、确认 `Xray 配置路径` 与 `面板内网地址`
2. **节点** → 新建一个 Vision 节点（端口 443）和一个 XHTTP 节点（端口 8443），SNI 都填同一个域名，回落 `127.0.0.1:8003`，PROXY protocol 选 v1
3. **订阅用户** → 新建订阅，勾选两个节点，设置有效期 / 流量
4. 右上角 **应用配置** → 面板写入 `config.json`、`xray -test`、重启 Xray

订阅地址形如：

```
https://node.example.com/sub/<token>          # v2rayN / v2rayNG
https://node.example.com/sub/<token>/clash    # Clash / mihomo
```

---

## 从源码运行（开发）

```bash
python3 app.py --host 127.0.0.1 --port 8080 --data-dir ./data
# 浏览器打开 http://127.0.0.1:8080
```

生产环境请用 `deploy/install.sh`：它会创建 `reality-panel` 系统用户、写好
systemd 与 sudoers，并把面板限制在回环地址上。

需要手动装 Xray 时用官方脚本：

```bash
bash -c "$(curl -fsSL https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
```

面板默认只监听 `127.0.0.1`，这是有意的：443 被 Xray 占用，面板没有多余端口做公网 HTTPS。
需要远程访问就用 SSH 隧道，或者用 Cloudflare Tunnel / Tailscale 之类的东西套一层。

---

## 两种传输怎么选

| | Vision | XHTTP |
|---|---|---|
| 传输层 | TCP + XTLS Vision | HTTP（h2/h1.1） |
| 延迟 | 最低 | 略高 |
| 抗干扰 | 强（TLS 内嵌） | 更强，可挂 CDN |
| 客户端要求 | Xray 1.8+ 都行 | Xray ≥ 24.9.30，建议 25.x |
| Clash 支持 | mihomo 支持 | 需较新的 mihomo |
| 建议 | 主力 | 备用 / 特殊网络 |

两者可以同时开：Vision 走 443，XHTTP 走 8443，互不影响，订阅里会同时出现。

> XHTTP 不能使用 `xtls-rprx-vision` flow，这是协议限制，面板会自动处理。

---

## 客户端兼容

| 客户端 | Vision | XHTTP | 订阅格式 |
|---|---|---|---|
| v2rayN 7.x | ✅ | ✅ | Base64 |
| v2rayNG 1.9+ | ✅ | ✅ | Base64 |
| NekoBox | ✅ | ⚠️ 取决于内核 | Base64 |
| mihomo / Clash Verge Rev | ✅ | ⚠️ 需较新内核 | YAML |
| 原版 Clash | ❌ 不支持 REALITY | ❌ | — |
| sing-box | ✅ | ❌ 不支持 XHTTP | — |

「原版 Clash 不支持 REALITY」是内核限制，不是配置问题。

---

## 和参考项目比，缺什么

这些项目面向不同场景，功能多不等于都需要。本项目只做「单机 + VLESS REALITY + 自己偷自己」，
下表里打 ✗ 的是**有意不做**，不是漏掉：

| 能力 | 本项目 | 参考项目 | 取舍原因 |
|---|:---:|---|---|
| 多服务器 / agent 纳管 | ✗ | Mistgate、Milk、FLYX | 自己偷自己只需一台机器，多节点会引入节点通信与凭据分发 |
| 多协议（Hysteria2 / Trojan / SS / TUIC…） | ✗ | Mistgate、Zefira、FLYX | 目标就是 REALITY，加协议会让面板与配置复杂度翻倍 |
| 中转 / 链式代理 / 端口转发 | ✗ | FLYX、SublinkPro | 属于另一类产品 |
| 机场订阅导入、测速、解锁检测 | ✗ | SublinkPro | 个人面板不需要 |
| 用户自助页面（浏览器看用量） | ✗ | Zefira、Mistgate | 订阅链接已够用，少一个对外页面 |
| 设备数限制 / 首连计时 | ✗ | Zefira | 需要连接级追踪，Xray 原生不提供 |
| Telegram 机器人 / 通知 | ✗ | 多数 | 个人使用没必要 |
| 多管理员 / API Token | ✗ | Zefira、SublinkPro | 单管理员模型更简单 |
| Docker 部署 | ✗ | SublinkPro、FLYX | 零依赖直接跑更轻 |
| 面板内一键升级 | ✗ | Zefira、FLYX | 升级就是替换目录 + 重启，不想让面板改自己的代码 |
| 二维码 | ✓ | 都有 | 已补 |
| 操作审计 | ✓ | Zefira、SublinkPro | 已补 |
| 备份导出 / 恢复 | ✓ | 多数 | 已补 |
| 流量自动采样 | ✓ | 多数 | 已补（否则额度不会自动生效） |

对照之后补上的还有 GitHub Actions CI、`SECURITY.md`、`CONTRIBUTING.md`。

---

## 面板结构

```
reality-panel/
├── app.py                  # 入口：HTTP 服务 + CLI（serve / sweep / status）
├── panel/
│   ├── api.py              # JSON API 与订阅端点
│   ├── auth.py             # PBKDF2 密码、登录限流
│   ├── db.py               # SQLite 建表与数据访问
│   ├── httpd.py            # 极简路由、静态资源、会话/CSRF
│   ├── links.py            # vless:// / Base64 / Clash YAML
│   ├── nginx.py            # 自偷自 Nginx 配置生成
│   ├── util.py             # 时间、随机、原子写文件
│   ├── x25519.py           # RFC 7748 X25519
│   ├── xray.py             # Xray 配置生成 / 测试 / 重启 / 流量
│   └── web/                # 前端（index.html / app.js / style.css / qrcode.js）
├── deploy/
│   ├── install.sh          # 安装面板 + Xray + systemd + sudoers
│   ├── selfsteal.sh        # 证书 + Nginx 回落配置
│   └── nginx-selfsteal.conf.example
├── tests/                  # 38 个单元 / 端到端测试
├── .github/workflows/ci.yml
├── SECURITY.md
├── CONTRIBUTING.md
└── README.md
```

数据默认在 `data/panel.db`（生产环境是 `/var/lib/reality-panel/panel.db`），
内含 REALITY 私钥与用户 UUID，**权限请保持 600**。

---

## 常用运维

```bash
systemctl status reality-panel
journalctl -u reality-panel -f

# 过期 / 超额订阅由 timer 每 10 分钟自动处理（先采样流量，再判断）
systemctl list-timers | grep reality-panel

# 手动清理一次
sudo -u reality-panel env REALITY_PANEL_DATA=/var/lib/reality-panel \
  python3 /opt/reality-panel/app.py sweep

# 查看概览
python3 app.py status --data-dir /var/lib/reality-panel

# 备份（数据库 + 配置）
tar czf panel-backup.tgz /var/lib/reality-panel /usr/local/etc/xray/config.json
```

证书自动续期由 certbot 的 timer 负责：

```bash
systemctl list-timers | grep certbot
certbot renew --dry-run
```

---

## 常见问题

**客户端一直握手失败**

按顺序检查：SNI 是否等于证书域名 → 服务端 `privateKey` 与客户端 `pbk` 是否配对 →
`shortId` 是否在服务端列表里 → 服务器时间是否准确。面板「更换密钥」后必须让客户端重新拉订阅。

**用浏览器直接访问 443，看到什么？**

应该看到上游真实站点的内容（比如 lovelive 的页面），证书是你的域名。
如果看到 502 / 证书错误 / 连接被重置，先看 `nginx -t` 与 `journalctl -u nginx`。

**nginx 报 `unknown directive "sub_filter"`**

说明当前 nginx 没编译 `http_sub_module`。Debian/Ubuntu 安装 `nginx-extras`，
或者把生成配置里的 `sub_filter` 两行删掉（只影响页面链接改写，不影响 REALITY）。

**XHTTP 节点连不上**

确认 Xray ≥ 24.9.30；确认客户端走的是 xhttp 且路径与面板一致；
Clash 侧需要较新的 mihomo，老内核会直接忽略该节点。

**订阅地址打不开**

订阅走的是 `https://域名/sub/<token>`，依赖 Nginx 的 `location ^~ /sub/`
反代到面板（默认 `127.0.0.1:8080`）。如果改过面板端口，记得在「设置 → 面板内网地址」同步。

**流量一直是 0**

面板通过 `xray api statsquery` 读取统计。确认 Xray 正在运行、`xray_api` 地址
（默认 `127.0.0.1:10085`）没被占用，并且配置里的 `policy` 统计项没有被你手动删掉。

**PROXY protocol 相关报错**

`xver` 与 Nginx 的 `listen ... proxy_protocol` 必须同时开或同时关。
本项目的向导默认两边都开（v1）。

---

## 开发与测试

```bash
python3 app.py --port 8080 --data-dir ./data      # 本地跑
python3 -m unittest discover -s tests -v          # 38 项测试
```

测试覆盖：X25519 官方向量、链接与订阅编码、Clash YAML、Xray 配置结构、
Nginx 配置生成与注入防护、密码哈希与限流、完整 API 流程（初始化 / CSRF / 订阅 / 应用配置）。

没有第三方依赖，所以也不需要 `requirements.txt`。

---

## 设计参考

写这个面板时参考了这些项目的思路（不是 fork，代码独立实现）：

1. [Samzzj/mistgate-](https://github.com/Samzzj/mistgate-) — 面板与节点分离的结构
2. [ZeroDeng01/sublinkPro](https://github.com/ZeroDeng01/sublinkPro/blob/main/README.zh-CN.md) — 订阅编排与客户端兼容
3. [Milk-WX/MILK-PANEL](https://github.com/Milk-WX/MILK-PANEL) — 安装器与运维体验
4. [mrlurix/zefira-panel](https://github.com/mrlurix/zefira-panel) — 单机 SQLite 面板的取舍
5. [jollyroger.top/sites/223.html](https://jollyroger.top/sites/223.html) — REALITY 部署细节
6. [kure29/flyx](https://github.com/kure29/flyx) — 轻量面板的信息架构

REALITY 与 self-steal 的协议细节以 [XTLS 官方文档](https://xtls.github.io/config/transports/reality.html)
和 [Xray-examples](https://github.com/XTLS/Xray-examples) 为准。

---

## 免责声明

本项目仅用于学习网络协议、管理**自己拥有或已获授权**的服务器。
请遵守你所在国家 / 地区的法律法规以及服务商条款，不要用于任何未经授权的用途。
因使用本项目产生的一切后果由使用者自行承担。

## License

MIT
