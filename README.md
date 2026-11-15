# Reality Panel

一个 **VLESS + REALITY** 管理面板，支持 Vision 和 XHTTP，内置「自己偷自己」。
一台主控面板，多台节点，节点只装一个 agent。

---

## 原理：什么叫「自己偷自己」

普通的 REALITY 是「偷别人」：回落目标填一个真实网站，比如 `www.lovelive-anime.jp`。
没有通过 REALITY 认证的 TLS 连接，会被转给那个网站，探针看到的是别人的证书和页面。

「自己偷自己」是把回落目标换成**本机的 Nginx**：

```
客户端 / 探针
  │  连接 panel.example.com:443，SNI = panel.example.com
  ▼
Xray REALITY :443
  ├─ 带 REALITY 认证  ──> 正常代理出站
  └─ 没有认证的 TLS   ──> PROXY protocol ──> Nginx 127.0.0.1:8003
                                                │ 用 panel.example.com 的证书做本地 TLS
                                                └─ 反代 https://www.lovelive-anime.jp
```

具体过程：

1. 客户端连 443，SNI 是 `panel.example.com`
2. Xray 把 TLS 握手转给 `dest`，也就是本机 nginx 的 `127.0.0.1:8003`
3. nginx 出示 `panel.example.com` 的 Let's Encrypt 证书，完成 TLS
4. 没有 REALITY 认证的连接，nginx 当成普通 HTTPS 请求，反代到上游真实网站
5. 带 REALITY 认证的客户端，Xray 识别后直接按 VLESS 代理处理，不走 nginx

所以从外面看：

- 域名是 `panel.example.com`
- 证书是 `panel.example.com` 的有效证书
- 打开页面看到的是 `www.lovelive-anime.jp` 的内容
- 没有明显代理特征，也不需要客户端先访问外部网站

为什么叫「自己偷自己」：**证书和域名都是自己的，回落目标也是自己的 nginx**，
不像传统 REALITY 那样去借别人网站的证书。

几个关键点：

- SNI 必须是 `panel.example.com`，不能填 `www.lovelive-anime.jp`；后者只是 nginx 反代的上游
- `dest` 必须是 `127.0.0.1:8003`，`xver` 选 v1（PROXY protocol）
- 回落站点有两种模式：`proxy` 反代外部站点，`static` 直接托管本机静态站（推荐，见第 2 步）
- nginx 用 `proxy_protocol` 接收 Xray 转来的连接，才能拿到真实客户端 IP
- 443 归 Xray，8003 只监听回环，公网访问不到
- 面板的 `/sub/` 也走这条回落：普通 HTTPS 请求到 `/sub/` 会被 nginx 反代到面板 8080。
  节点机器没有面板，所以节点版 nginx 配置不包含 `/sub/`

---

## 开始前准备

> 下面的 `panel.example.com` 和 `node2.example.com` 都是示例，换成你自己的域名。

1. 一台 **Ubuntu 22.04 / 24.04** 或 **Debian 12 / 13** 的 VPS（主控；节点用同样的系统也可以）
2. 一个域名，加一条 A 记录：

   ```
   panel.example.com  ->  主控服务器 IP
   ```

3. 放行端口：

   | 端口 | 用途 |
   |---|---|
   | 80 | 签证书（ACME HTTP-01，由 nginx 应答） |
   | 443 | 客户端连接 |
   | 9443 | 面板网页（建议只对白名单 IP 开放） |
   | 8003 | 回落站点，**只监听 127.0.0.1**，公网访问不到 |
   | 8787 | 节点 agent，只放行面板 IP |

4. 域名在 Cloudflare 的话，记录先设为 **DNS only（灰云）**。

---

## 第 1 步：安装面板

SSH 登录主控服务器，用 root：

```bash
apt-get update && apt-get install -y git
git clone https://github.com/Samzzj/one-panel.git ~/one-panel
cd ~/one-panel
sudo bash deploy/install.sh
```

看到 `面板已重启，运行版本 ...` 就成功了。

---

## 第 2 步：签证书 + 部署回落站点

先确认 `panel.example.com` 已经解析到这台服务器。

```bash
cd ~/one-panel

# 1) 签证书 + 生成回落配置（证书走 webroot，可自动续期）
sudo SITE_MODE=static bash deploy/selfsteal.sh panel.example.com

# 2) 部署回落站点（导航站），静态文件放 /var/www/nav
sudo bash deploy/nav-site.sh panel.example.com /opt/webstack-nav/public

# 3) 开面板 HTTPS 入口，并按白名单收紧
sudo bash deploy/panel-https.sh panel.example.com
sudo bash deploy/panel-guard.sh sync
```

然后浏览器打开：

```
https://panel.example.com:9443
```

第一次会让你创建管理员账号。

> 打不开就先检查：`systemctl status reality-panel` 和 `ss -ltnp | grep 9443`

### 证书自动续期

`selfsteal.sh` 用的是 **webroot** 模式：80 端口由 nginx 自己应答 ACME 校验文件，
续期时不需要停 nginx、不占端口、也不重启 Xray（REALITY 不加载证书，证书由 nginx 在回落端口出示）。

```bash
certbot renew --dry-run              # 必须通过
systemctl list-timers | grep certbot # 定时器在跑
```

以下几点会让续期失败，务必确认：

- 80 端口必须长期对外开放（安全组 + 防火墙都放行）
- 域名必须是 **灰云（DNS only）**；上了 Cloudflare 橙云的域名不仅续期失败，REALITY 本身也用不了
- 80 被封的话改用 DNS-01：`acme.sh --issue --dns dns_cf -d <域名> --reloadcmd 'systemctl reload nginx'`

### 回落站点（导航站）

`deploy/nav-site.sh` 做四件事：落版本目录 → 原子切换 `/var/www/nav` 软链 →
用 static 模式重新生成 nginx 配置 → 自检端口只绑回环、本机 SNI 访问返回 200。

```bash
sudo bash deploy/nav-site.sh panel.example.com /opt/webstack-nav/public
sudo bash deploy/nav-site.sh --rollback   # 回滚到上一个版本
```

改完内容重新上传，再跑一次脚本即可；HTML 设了 no-cache，不用清浏览器缓存。

### 9443 白名单（网络级）

白名单真源是面板设置里的「访问白名单」，`panel-guard.sh` 每 30 秒单向同步到
nftables 集合和 nginx 的 `geo` 列表：

- 白名单外：nftables 在 TCP 层直接 DROP，**端口扫描看不到，浏览器表现为连接超时**
- 兜底层：nginx 里 `if ($panel_allowed = 0) { return 444; }`，防火墙规则丢失时也不会放行

```bash
sudo deploy/panel-guard.sh status                 # 看实际生效情况
sudo deploy/panel-guard.sh add 1.2.3.4 --ttl 2h   # 换 IP 被锁时临时放行
```

> 白名单为空 = 不限制（与面板应用层语义一致）。`install.sh` 首次安装会把当前
> SSH 来源 IP 自动写进去，避免刚开 9443 就被自己挡在门外。

---

## 第 3 步：填面板地址

登录后进 **设置**：

- **公网地址**：`panel.example.com`
- 其它保持默认

保存。

---

## 第 4 步：创建第一个节点

打开 **节点 → 新建节点**，按下面填：

| 字段 | 填什么 |
|---|---|
| 名称 | 本机 Vision |
| 所属服务器 | 本机 |
| 传输 | Vision |
| 端口 | 443 |
| SNI | `panel.example.com` |
| 回落地址 | `127.0.0.1:8003` |
| PROXY protocol | v1 |

保存。

默认会自动应用配置，等右上角提示「配置已自动应用」。

检查：

```bash
systemctl is-active xray
ss -ltnp | grep ':443'
```

---

## 第 5 步：创建订阅

1. 打开 **订阅用户 → 新建订阅**
2. 勾选刚才的节点
3. 保存
4. 复制链接

链接有两种：

**v2rayN / v2rayNG**（Base64）：

```
https://panel.example.com/sub/xxxxxxxx
```

**Clash / FlClash / mihomo**（YAML）：

```
https://panel.example.com/sub/xxxxxxxx/clash
```

注意：订阅地址是**面板域名**，不是节点域名，也不是服务器 IP。

客户端里删除旧配置，重新导入。

---

## 第 6 步：加第二台服务器（可选）

第二台只装 agent，不装面板。

### 1. 加 DNS

```
node2.example.com  ->  第二台服务器 IP
```

第二台放行 80、443；8787 只放行面板 IP。

### 2. 面板添加服务器

**服务器 → 添加服务器**：

| 字段 | 填什么 |
|---|---|
| 名称 | 节点 2 |
| 公网地址 | `node2.example.com` |
| 节点域名 | `node2.example.com` |
| Agent 地址 | 输入公网地址后自动生成 |
| Agent 令牌 | 留空自动生成 |

保存后，复制弹窗里的命令，到**第二台**执行：

```bash
curl -4 -fsSL https://raw.githubusercontent.com/Samzzj/one-panel/main/deploy/agent-install.sh \
  | sudo bash -s -- --token <令牌> --with-nginx --allow <面板公网IP>/32
```

> `--allow` 是来源 IP 白名单：agent 端口只接受面板来连，别人扫到 8787 也拿不到响应。
> 面板有固定公网 IP 时，安装命令会自动带上它。

### 3. 一键初始化

回面板：

1. 点第二台的「测试」，显示在线
2. 点这一行的链条图标「初始化自偷自」
3. 等它签证书、写 nginx

### 4. 建节点

节点 → 新建：

- 所属服务器：选第二台
- SNI：会自动填 `node2.example.com`
- 端口 443，回落 `127.0.0.1:8003`，xver v1

保存后自动下发。订阅里会同时出现两台机器的节点。

### 如果节点下载 Xray 失败

GitHub 不通时，用离线包。在面板上：

```bash
cd ~/one-panel
sudo bash deploy/make-agent-kit.sh
scp dist/one-panel-agent-kit-*.tar.gz root@第二台IP:/tmp/
```

在第二台上：

```bash
tar xzf /tmp/one-panel-agent-kit-*.tar.gz -C /root
sudo bash /root/one-panel-agent-kit/deploy/agent-install.sh \
  --token <令牌> --with-nginx \
  --xray-binary /root/one-panel-agent-kit/xray/xray
```

---

## 第 7 步：更新面板

```bash
cd ~/one-panel
git pull
sudo bash deploy/install.sh
```

浏览器 `Ctrl+F5`。

更新了 agent 的版本时，到服务器列表重新复制安装命令，在节点上重装一次。

---

## 常见问题

### 新节点提示 443 已被占用

同一台服务器一个端口只能有一个节点。

- 确认「所属服务器」选的是正确的那台
- 节点列表里看哪台服务器已有 443 节点，删掉或换端口

### 签证书失败

- 域名 A 记录必须指向这台机器
- 80 端口必须能从公网访问
- 失败多次等一小时再试（Let's Encrypt 有限制）

### FlClash 报 `REALITY authentication failed`

面板更新到最新版，删除旧订阅重新导入。

Xray 26.9+ 需要订阅里带：

```yaml
support-x25519mlkem768: true
```

新版面板会自动生成；旧 FlClash 需要升级。

### 节点机器 `/sub/` 返回 502

正常。`/sub/` 只在面板本机有效。订阅用面板域名。

### 面板打不开

```bash
systemctl status reality-panel --no-pager
ss -ltnp | grep ':9443'
```

面板只监听 `127.0.0.1:8080`，必须通过 9443 的 HTTPS 入口访问。

### 9443 换了 IP 打不开

白名单生效后，非白名单来源会在 TCP 层被丢弃（浏览器表现为连接超时，`curl` 也不会报证书错误）。
SSH 进服务器临时放行：

```bash
sudo /opt/reality-panel/deploy/panel-guard.sh add <你的新IP> --ttl 2h
```

长期地址写进面板「设置 → 访问白名单」，30 秒内自动同步。

### 回落站点 404 / 白屏

```bash
ls -l /var/www/nav            # 应该是软链，指向 /var/www/nav-releases/<时间戳>
ss -ltnp | grep 8003          # 必须只有 127.0.0.1
curl -k --resolve <域名>:443:127.0.0.1 https://<域名>/ -o /dev/null -w '%{http_code}\n'
```

自检 200 但浏览器打不开，通常是没走 443（比如直接访问了 IP:8003，本来就该连不上）。

---

## 安全提醒

- agent 令牌等于那台机器的控制权，不要发给别人；泄露后在服务器列表重置
- 8787 只放行面板 IP，不要对全网开放
- 备份文件包含私钥和所有用户 UUID，妥善保管
- 面板用强密码，必要时开启访问白名单

---

## 常用命令

```bash
systemctl status reality-panel
systemctl status xray
systemctl status one-panel-agent

journalctl -u reality-panel -n 50
journalctl -u xray -n 50

nginx -t
systemctl reload nginx

# 回落站点
sudo bash deploy/nav-site.sh <域名> /opt/webstack-nav/public
sudo bash deploy/nav-site.sh --rollback
ss -ltnp | grep 8003                       # 只应出现 127.0.0.1

# 证书
certbot certificates
certbot renew --dry-run

# 9443 白名单
sudo deploy/panel-guard.sh status
sudo deploy/panel-guard.sh add <IP> --ttl 2h

# 查看面板实际运行版本
curl -s http://127.0.0.1:8080/api/bootstrap
```

---

## 开发

```bash
python3 app.py --host 127.0.0.1 --port 8080 --data-dir ./data
python3 -m unittest discover -s tests -v
```

要求 Python 3.8+，无第三方依赖。
