# 安全策略

## 支持范围

只维护 `main` 上的最新版本。发现漏洞请勿公开提交 issue。

## 报告方式

通过 GitHub 仓库的 **Security → Report a vulnerability**（私有安全公告）提交，附上：

- 影响版本 / commit
- 复现步骤与最小请求
- 实际影响（例如能否绕过登录、读取他人订阅、执行命令）

会在确认后尽快修复并在公告中致谢（如果你希望署名）。

## 重点关注

- 认证绕过、会话固定、CSRF
- 订阅 token 泄露或可枚举
- SQL 注入、路径穿越、模板/HTML 注入
- 面板通过 Xray 配置写入实现命令执行
- 备份恢复接口的越权或覆盖

## 部署侧要求（不属于漏洞，但会让面板变危险）

- 面板默认只监听 `127.0.0.1`，请勿在没有 TLS 与访问控制的情况下直接暴露 `8080`
- 数据目录（`panel.db`）包含 REALITY 私钥与全部 UUID，权限应保持 `700/600`
- 订阅地址等同于密码，泄露后请用「重置订阅」轮换 token 与 UUID
- 不要把 `/sub/` 暴露给不可信网络之外的人；它是无鉴权的 bearer 链接
- 定期导出备份，但备份同样是敏感文件
- Xray 配置需要 `0644`：官方 systemd 服务以 `nobody` 运行，否则读不到配置。
  单用户 VPS 可接受；多用户主机请限制 `/usr/local/etc/xray` 目录的访问

## 节点 agent

- `agent.py` 的令牌等同于那台机器的控制权（可写 Xray / Nginx 配置并重启服务），
  不要写进公开仓库、截图或聊天记录
- agent 默认监听 `0.0.0.0:8787` 且是明文 HTTP，**必须**用防火墙只放行主控 IP，
  或把 agent 放在 WireGuard / Tailscale / 内网里
- 怀疑令牌泄露：面板 → 服务器 → 重置令牌，然后用新命令重装 agent
- agent 以 root 运行（要 restart xray/nginx）；systemd 单元已加 `ProtectSystem=strict`
  与最小 `ReadWritePaths`，但仍应把节点视为可被主控完全控制的机器
