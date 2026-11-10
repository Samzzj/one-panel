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
   | 80 | 签证书 |
   | 443 | 客户端连接 |
   | 9443 | 面板网页 |
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

## 第 2 步：给面板开 HTTPS

先确认 `panel.example.com` 已经解析到这台服务器。

```bash
cd ~/one-panel
sudo bash deploy/selfsteal.sh panel.example.com
sudo bash deploy/panel-https.sh panel.example.com
```

然后浏览器打开：

```
https://panel.example.com:9443
```

第一次会让你创建管理员账号。

> 打不开就先检查：`systemctl status reality-panel` 和 `ss -ltnp | grep 9443`

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
  | sudo bash -s -- --token <令牌> --with-nginx
```

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
