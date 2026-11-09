# Reality Panel

一个自用的 **VLESS + REALITY** 管理面板，支持 **Vision** 和 **XHTTP**，内置「自己偷自己」：
客户端连 REALITY，未通过认证的流量回落到本机 Nginx，再反代到真实网站。

- 一台主控面板 + 多台节点，节点只装一个单文件 agent
- 添加服务器、节点、订阅都在网页完成
- 修改后约 2 秒自动下发配置，不需要手动点「应用配置」
- 支持 v2rayN / v2rayNG（Base64 订阅）和 Clash / mihomo（YAML）
- 纯 Python 标准库，无 Docker、无外部数据库

---

## 准备工作

一台 Ubuntu 22.04 / 24.04 的 VPS，以及：

1. 一个域名，准备两条 A 记录：

   | 用途 | 示例 | 指向 |
   |---|---|---|
   | 面板 / 本机节点 | `lisa.example.com` | 面板服务器 IP |
   | 第二台节点（可选） | `ay.example.com` | 第二台 IP |

2. 放行端口：

   - `80`：签证书用
   - `443`：客户端连接
   - `9443`：面板 HTTPS（只给自己访问）
   - `8787`：agent 管理端口，**只放行面板服务器 IP**

3. Cloudflare 的域名请把这两条记录设为 **DNS only（灰云）**，不要开橙云。

---

## 一、安装面板

SSH 登录服务器，用 root：

```bash
apt-get update && apt-get install -y git
git clone https://github.com/Samzzj/one-panel.git ~/one-panel
cd ~/one-panel
sudo bash deploy/install.sh
```

脚本会安装依赖、创建系统用户、写入 systemd，并启动面板。

检查：

```bash
systemctl status reality-panel --no-pager
```

### 打开面板

面板默认只监听 `127.0.0.1:8080`，两种打开方式。

**方式 A：SSH 隧道（临时用）**

在**你自己的电脑**上执行：

```bash
ssh -L 8080:127.0.0.1:8080 root@服务器IP
```

然后浏览器打开 `http://127.0.0.1:8080`。

**方式 B：HTTPS 入口（推荐）**

先按下面「二、给本机配自偷自」签好证书，再执行：

```bash
cd ~/one-panel
sudo bash deploy/panel-https.sh lisa.example.com
```

之后浏览器直接打开：

```
https://lisa.example.com:9443
```

443 仍然归 Xray，面板走 9443，互不影响。

---

## 二、给本机配自偷自

先把 `lisa.example.com` 解析到这台服务器，并确认 80 端口可从公网访问。

```bash
cd ~/one-panel
sudo bash deploy/selfsteal.sh lisa.example.com
```

这个脚本会：

- 用 certbot 签 `lisa.example.com` 的证书
- 写 `/etc/nginx/conf.d/reality-selfsteal.conf`
- 让 Nginx 在 `127.0.0.1:8003` 提供本地 TLS，并反代到 `www.lovelive-anime.jp`

验证：

```bash
nginx -t
systemctl is-active nginx
ss -ltnp | grep ':8003'
ls /etc/letsencrypt/live/lisa.example.com/
```

然后给面板加 HTTPS：

```bash
sudo bash deploy/panel-https.sh lisa.example.com
```

---

## 三、初始化面板

浏览器打开面板，第一次会要求创建管理员账号。

登录后到 **设置**：

- **公网地址**：填 `lisa.example.com`（订阅链接里会用它）
- 其它保持默认即可

设置页的 **自动化** 默认是开的：

> 修改节点 / 订阅 / 服务器后自动应用配置，约 2 秒后下发并重启 Xray。

不想自动应用就取消勾选，之后手动点右上角「应用配置」。

---

## 四、创建第一个节点

1. 打开 **节点 → 新建节点**
2. 填写：

   | 字段 | 值 |
   |---|---|
   | 名称 | 随便，例如 `本机 Vision` |
   | 所属服务器 | 本机 |
   | 传输 | Vision |
   | 端口 | `443` |
   | SNI | `lisa.example.com` |
   | 回落地址 | `127.0.0.1:8003` |
   | PROXY protocol | v1 |

3. 保存

保存后不用点「应用配置」，约 2 秒会自动下发。右上角短暂出现「有未应用的更改」是正常的，自动应用完成后会显示「配置已自动应用」。

验证：

```bash
systemctl is-active xray
ls -l /usr/local/etc/xray/config.json    # 应该是 644
ss -ltnp | grep ':443'
```

---

## 五、创建订阅并导入客户端

1. 打开 **订阅用户 → 新建订阅**
2. 选择要包含的节点，设置流量 / 到期时间（可留空）
3. 保存后点订阅的链接 / 二维码
4. 客户端导入：

   - **v2rayN / v2rayNG**：复制 Base64 订阅地址，粘贴到「从剪贴板导入」
   - **Clash / mihomo**：复制 YAML 订阅地址，添加到配置

订阅地址形如：

```
https://lisa.example.com/sub/xxxxxxxx
```

这个地址走 443，由自偷自的 Nginx 反代到面板，不需要额外端口。

---

## 六、添加第二台服务器（可选）

第二台机器只装 agent，不装面板。

### 1. 加 DNS 和放行端口

`ay.example.com` 指向第二台 IP。第二台放行：

- `80`、`443`
- `8787` 只放行面板服务器 IP

### 2. 面板里添加服务器

**服务器 → 添加服务器**：

| 字段 | 填什么 |
|---|---|
| 名称 | GGB1（随意） |
| 公网地址 | `ay.example.com` |
| 节点域名 | `ay.example.com` |
| Agent 地址 | 输入公网地址后自动变成 `http://IP:8787` |
| Agent 令牌 | 留空自动生成 |

保存后复制弹窗里的安装命令，在**第二台**执行：

```bash
curl -fsSL https://raw.githubusercontent.com/Samzzj/one-panel/main/deploy/agent-install.sh \
  | sudo bash -s -- --token <令牌> --with-nginx
```

### 3. 一键初始化

回面板点「测试」，在线后点这行的**链条图标**「初始化自偷自」。

agent 会自动签 `ay.example.com` 的证书、写 Nginx、reload；弹窗会显示结果。

### 4. 建节点

节点 → 新建，所属服务器选第二台，SNI 会自动填 `ay.example.com`，端口 `443`，dest `127.0.0.1:8003`，xver v1。

保存后自动下发，订阅里会同时出现两台机器的节点。

---

## 七、更新

```bash
cd ~/one-panel
git pull
sudo bash deploy/install.sh
```

然后浏览器 `Ctrl+F5`。

- 只更新面板：上面两步就够
- 更新了 agent：到服务器列表点终端图标，用新命令在节点上重装一次

---

## 八、卸载

```bash
cd ~/one-panel
sudo bash deploy/install.sh --uninstall
```

数据目录 `/var/lib/reality-panel` 会保留，需要彻底删除时手动 `rm -rf`。

---

## 九、常见问题

### 安装时提示 `Could not get lock /var/lib/dpkg/lock-frontend`

`unattended-upgrades` 正在占用 apt。v0.5.2 之后的安装脚本在依赖齐全时会跳过 apt，不会再提示。

如果确实缺依赖，等一两分钟再执行，或：

```bash
systemctl stop unattended-upgrades
```

### 面板打不开

- 面板只监听 `127.0.0.1:8080`，必须用 SSH 隧道或 9443 的 HTTPS 入口
- 检查服务：`systemctl status reality-panel --no-pager`
- 检查 9443：`ss -ltnp | grep ':9443'`

### `443 已被占用`

这是面板数据库里的端口冲突：**同一台服务器**一个端口只能有一个节点。

- 新建时确认「所属服务器」选对了
- 节点列表里看哪台服务器已有 443 节点，删掉或换端口
- Vision 用 443，XHTTP 用 8443

### 签证书失败

- 域名 A 记录必须已经指向这台机器：`getent ahostsv4 ay.example.com`
- 80 端口必须能从公网访问
- Let's Encrypt 有频率限制，失败多次后等一小时
- 看 agent 弹窗里的 certbot 输出

### `open() "/run/nginx.pid" failed (30: Read-only file system)`

agent 的 systemd 沙箱权限问题，v0.5.3 已修复。更新 agent 后重试，或手动加 drop-in：

```bash
mkdir -p /etc/systemd/system/one-panel-agent.service.d
cat >/etc/systemd/system/one-panel-agent.service.d/override.conf <<'EOF'
[Service]
ReadWritePaths=/opt/one-panel-agent /etc/nginx/conf.d /usr/local/etc/xray /var/lib/nginx /var/log/nginx /var/log/xray /etc/letsencrypt /var/lib/letsencrypt /var/log/letsencrypt /run
EOF
systemctl daemon-reload && systemctl restart one-panel-agent
```

`Hook 'deploy-hook' ran with error output: nginx.service is not active` 是正常的，签证书时 nginx 被临时停掉了。

### `xray` 启动失败，提示找不到 `config.json`

面板第一次「应用配置」之前 Xray 可能没有配置。先在面板建节点，等自动应用完成，再检查：

```bash
systemctl status xray --no-pager
journalctl -u xray -n 30 --no-pager
```

### `permission denied` 读取 Xray 配置

Xray 以 `xray` 用户运行，配置必须是 644：

```bash
chmod 644 /usr/local/etc/xray/config.json
systemctl restart xray
```

v0.4.2 之后面板和 agent 都会自动写成 644。

### 节点 / 订阅改了但客户端没变

- 确认「设置 → 自动化」是开的，或手动点「应用配置」
- 客户端重新更新订阅

### 节点机器的 `/sub/` 返回 502

正常。`/sub/` 只在面板本机有意义，节点版 Nginx 配置不包含它。订阅仍然用面板域名的 `/sub/`。

---

## 十、安全建议

- **agent 令牌 = 那台机器的控制权**，不要发群里；泄露后在服务器列表重置
- `8787` 只放行面板 IP，不要对全网开放
- 面板用 9443 + 强密码；也可以用「访问白名单」限制来源 IP
- 备份包含 REALITY 私钥和所有 UUID，等同于服务器控制权，妥善保管
- Xray 配置是 644（Xray 以非 root 用户运行），同机其他用户可读；介意的话给 Xray 单独的受限用户

---

## 十一、常用命令

```bash
# 面板
systemctl status reality-panel
journalctl -u reality-panel -f
systemctl restart reality-panel

# Xray
systemctl status xray
journalctl -u xray -n 50

# Nginx
nginx -t
systemctl reload nginx

# 订阅清理（systemd timer 也会自动跑）
python3 /opt/reality-panel/app.py sweep

# 面板 IP 白名单（把自己锁死时用）
python3 /opt/reality-panel/app.py allow 你的IP
```

---

## 架构

```
客户端
  │  VLESS + REALITY (443)
  ▼
Xray ──认证通过──> 代理出站
  │
  └──未通过认证──> PROXY protocol ──> Nginx 127.0.0.1:8003
                                        │  本地 TLS（自己的证书）
                                        └──> 反代 www.lovelive-anime.jp
```

- 主控：面板 + 本机 Xray，存 SQLite、生成配置、下发、收流量、提供订阅
- 节点：单文件 `agent.py` + Xray，执行 `apply` / `stats` / `nginx` / `selfsteal`

目录：

```
app.py                    面板入口
agent.py                  节点 agent
panel/                    面板代码
  web/                    前端
deploy/                   安装 / 证书 / 面板 HTTPS 脚本
tests/                    50 项单元与端到端测试
```

---

## 开发

```bash
python3 app.py --host 127.0.0.1 --port 8080 --data-dir ./data
python3 -m unittest discover -s tests -v
```

要求 Python 3.8+，无第三方依赖。
