# 参与开发

## 本地运行

```bash
python3 app.py --host 127.0.0.1 --port 8080 --data-dir ./data
```

需要 Python 3.8+，没有任何第三方依赖。

## 测试

```bash
python3 -m unittest discover -s tests -v
node --check panel/web/app.js      # 改了前端时
```

测试会真的起一个 HTTP 服务跑完整流程（初始化 / CSRF / 节点 / 订阅 / 应用配置 / 备份恢复），
新增接口时请顺带补 `tests/test_api_e2e.py`。

## 约定

- **只用标准库**。这个面板的目标是扔到最小 VPS 上也能 `python3 app.py` 直接跑。
- 前端不引入构建步骤；需要第三方 JS 时选 MIT/BSD 许可、把许可证一起放进文件头。
- 数据库改动写进 `panel/db.py` 的 `SCHEMA`，并考虑已有数据（不要写破坏性迁移）。
- 改 Xray 配置生成时，同步更新 `tests/test_xray_config.py`；改 Nginx 模板时更新 `tests/test_nginx.py`。
- 所有 HTML 插值必须经过 `esc()`，后端所有 SQL 必须参数化。

## 提交

- 一个 PR 做一件事，说明动机、验证方式和可能影响现有配置的地方。
- 安全相关问题请先看 [SECURITY.md](SECURITY.md)，不要公开提交利用细节。
