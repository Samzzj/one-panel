"""端到端 API 测试：真实起一个 HTTP 服务，走完整业务流程。"""

from __future__ import annotations

import base64
import http.client
import json
import os
import shutil
import threading
import unittest

from app import App
from panel.httpd import build_server


class Client:
    def __init__(self, port: int):
        self.port = port
        self.cookie = ""
        self.csrf = ""

    def request(self, method: str, path: str, body: dict | None = None, csrf: bool = True, extra: dict | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        headers: dict[str, str] = dict(extra or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.cookie:
            headers["Cookie"] = self.cookie
        if csrf and self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        conn.request(method, path, body=data, headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", "replace")
        content_type = resp.getheader("Content-Type") or ""
        set_cookie = resp.getheader("Set-Cookie")
        if set_cookie:
            self.cookie = set_cookie.split(";")[0]
        conn.close()
        if "application/json" in content_type:
            return resp.status, json.loads(raw) if raw else {}, dict(resp.getheaders())
        return resp.status, raw, dict(resp.getheaders())


class ApiFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # 固定目录（不用 tempfile：受限环境下 mkdtemp 的目录可能不可访问）
        cls.data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".test-data")
        shutil.rmtree(cls.data_dir, ignore_errors=True)
        os.makedirs(cls.data_dir, exist_ok=True)
        cls.app = App(cls.data_dir)
        cls.server = build_server("127.0.0.1", 0, cls.app)
        cls.port = int(cls.server.server_address[1])
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.data_dir, ignore_errors=True)

    def test_full_flow(self) -> None:
        c = Client(self.port)
        config_path = os.path.join(self.data_dir, "xray-config.json")

        # --- 初始化 ---
        status, body, _ = c.request("GET", "/api/state")
        self.assertEqual(status, 401)

        status, body, _ = c.request("GET", "/api/bootstrap")
        self.assertEqual(status, 200)
        self.assertTrue(body["setup_required"])

        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/")
        page = conn.getresponse()
        html = page.read().decode("utf-8")
        self.assertEqual(page.status, 200)
        self.assertIn("app.js", html)
        conn.close()

        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/favicon.svg")
        icon = conn.getresponse()
        self.assertEqual(icon.status, 200)
        self.assertIn("image/svg+xml", icon.getheader("Content-Type") or "")
        icon.read()
        conn.close()

        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/assets/qrcode.js")
        qr_js = conn.getresponse()
        qr_body = qr_js.read()
        self.assertEqual(qr_js.status, 200)
        self.assertIn("javascript", qr_js.getheader("Content-Type") or "")
        self.assertGreater(len(qr_body), 50000)
        conn.close()

        status, body, _ = c.request("POST", "/api/setup", {"username": "admin", "password": "short"})
        self.assertEqual(status, 400)

        status, body, _ = c.request("POST", "/api/setup", {"username": "admin", "password": "TestPanel!2026"})
        self.assertEqual(status, 200)
        self.assertTrue(body["csrf"])
        c.csrf = body["csrf"]

        status, body, _ = c.request("POST", "/api/setup", {"username": "admin2", "password": "TestPanel!2026"})
        self.assertEqual(status, 403, "不能重复初始化")

        # --- 设置 ---
        status, body, _ = c.request(
            "POST",
            "/api/settings",
            {
                "public_host": "203.0.113.10",
                "default_sni": "node.example.com",
                "xray_config": config_path,
            },
        )
        self.assertEqual(status, 200)

        # --- CSRF ---
        status, body, _ = c.request(
            "POST",
            "/api/nodes",
            {"name": "x", "transport": "vision", "port": 444, "sni": "node.example.com", "dest": "127.0.0.1:8003"},
            csrf=False,
        )
        self.assertEqual(status, 403)

        # --- 建节点 ---
        status, body, _ = c.request(
            "POST",
            "/api/nodes",
            {
                "name": "香港 Vision",
                "transport": "vision",
                "port": 443,
                "sni": "node.example.com",
                "dest": "127.0.0.1:8003",
                "xver": 1,
                "short_ids": [],
            },
        )
        self.assertEqual(status, 200, body)
        vision = body["node"]
        self.assertEqual(len(vision["short_ids"]), 1)
        self.assertEqual(len(vision["short_ids"][0]), 16)
        self.assertEqual(len(vision["public_key"]), 43)

        status, body, _ = c.request(
            "POST",
            "/api/nodes",
            {"name": "dup", "transport": "vision", "port": 443, "sni": "node.example.com"},
        )
        self.assertEqual(status, 409)

        status, body, _ = c.request(
            "POST",
            "/api/nodes",
            {
                "name": "日本 XHTTP",
                "transport": "xhttp",
                "port": 8443,
                "sni": "node.example.com",
                "dest": "127.0.0.1:8003",
                "xver": 1,
                "xhttp_path": "/media",
                "xhttp_mode": "auto",
            },
        )
        self.assertEqual(status, 200, body)
        xhttp = body["node"]

        # --- 订阅 ---
        status, body, _ = c.request(
            "POST",
            "/api/subs",
            {
                "name": "测试用户",
                "node_ids": [vision["id"], xhttp["id"]],
                "expires_days": 30,
                "quota_gb": 100,
            },
        )
        self.assertEqual(status, 200, body)
        sub = body["sub"]
        self.assertEqual(sub["node_count"], 2)

        status, links, _ = c.request("GET", f"/api/subs/{sub['id']}/links")
        self.assertEqual(status, 200)
        self.assertEqual(len(links["links"]), 2)
        self.assertTrue(links["sub_url"].startswith("https://node.example.com/sub/"))

        token = sub["token"]

        # --- 订阅分发 ---
        status, payload, headers = c.request("GET", f"/sub/{token}", csrf=False)
        self.assertEqual(status, 200)
        decoded = base64.b64decode(payload).decode("utf-8")
        self.assertEqual(len(decoded.split("\n")), 2)
        self.assertIn("security=reality", decoded)
        self.assertIn("flow=xtls-rprx-vision", decoded)
        self.assertIn("type=xhttp", decoded)
        self.assertIn("Subscription-Userinfo", headers)

        status, yaml_text, _ = c.request("GET", f"/sub/{token}/clash", csrf=False)
        self.assertEqual(status, 200)
        self.assertIn("reality-opts:", yaml_text)
        self.assertIn("network: xhttp", yaml_text)
        self.assertIn("xhttp-opts:", yaml_text)

        status, _, _ = c.request("GET", "/sub/doesnotexistdoesnotexist", csrf=False)
        self.assertEqual(status, 404)

        # --- 自偷自 ---
        status, plan, _ = c.request("GET", f"/api/selfsteal?node_id={vision['id']}")
        self.assertEqual(status, 200)
        self.assertTrue(plan["ok"], plan.get("error"))
        self.assertIn("proxy_protocol", plan["conf"])
        self.assertIn("location ^~ /sub/", plan["conf"])

        # --- 应用配置（未安装 xray 时走 dry-run 写入） ---
        status, result, _ = c.request("POST", "/api/apply", {})
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"], result)
        self.assertTrue(os.path.exists(config_path))
        with open(config_path, "r", encoding="utf-8") as fh:
            config = json.load(fh)
        self.assertEqual(len(config["inbounds"]), 3)
        self.assertEqual({i["port"] for i in config["inbounds"]}, {10085, 443, 8443})

        # --- 订阅停用 ---
        status, _, _ = c.request("PATCH", f"/api/subs/{sub['id']}", {"enabled": False})
        self.assertEqual(status, 200)
        status, _, _ = c.request("GET", f"/sub/{token}", csrf=False)
        self.assertEqual(status, 403)
        status, _, _ = c.request("PATCH", f"/api/subs/{sub['id']}", {"enabled": True})
        self.assertEqual(status, 200)
        status, _, _ = c.request("GET", f"/sub/{token}", csrf=False)
        self.assertEqual(status, 200)

        # --- 日志/导出 ---
        status, logs, _ = c.request("GET", "/api/logs?lines=10")
        self.assertEqual(status, 200)
        self.assertIsInstance(logs["lines"], list)

        status, backup, _ = c.request("GET", "/api/export")
        self.assertEqual(status, 200)
        self.assertEqual(len(backup["nodes"]), 2)

        # --- UA 自动识别 Clash ---
        status, yaml_ua, _ = c.request(
            "GET", f"/sub/{token}", csrf=False, extra={"User-Agent": "clash-verge/v1.7.7"}
        )
        self.assertEqual(status, 200)
        self.assertIn("proxies:", yaml_ua)

        # --- 审计 ---
        status, audit, _ = c.request("GET", "/api/audit?limit=50")
        self.assertEqual(status, 200)
        actions = [item["action"] for item in audit["items"]]
        self.assertIn("创建节点", actions)
        self.assertIn("创建订阅", actions)
        self.assertIn("应用配置", actions)
        self.assertIn("初始化面板", actions)

        # --- 备份恢复（覆盖式） ---
        status, imported, _ = c.request("POST", "/api/import", backup)
        self.assertEqual(status, 200, imported)
        self.assertEqual(imported["nodes"], 2)
        self.assertEqual(imported["subs"], 1)
        status, state_after, _ = c.request("GET", "/api/state")
        self.assertEqual(len(state_after["nodes"]), 2)
        self.assertEqual(len(state_after["subs"]), 1)
        status, _, _ = c.request("GET", f"/sub/{token}", csrf=False)
        self.assertEqual(status, 200, "恢复后订阅 token 应保持不变")

        status, bad, _ = c.request("POST", "/api/import", {"nodes": "nope", "subs": []})
        self.assertEqual(status, 400)

        # --- 重置流量 ---
        new_sub_id = state_after["subs"][0]["id"]
        status, reset, _ = c.request("POST", f"/api/subs/{new_sub_id}/reset-traffic", {})
        self.assertEqual(status, 200, reset)
        self.assertEqual(reset["sub"]["used_bytes"], 0)

        # --- 退出 / 登录 ---
        status, _, _ = c.request("POST", "/api/logout", {})
        self.assertEqual(status, 200)
        status, _, _ = c.request("GET", "/api/state")
        self.assertEqual(status, 401)

        status, _, _ = c.request("POST", "/api/login", {"username": "admin", "password": "wrong"})
        self.assertEqual(status, 401)

        status, body, _ = c.request("POST", "/api/login", {"username": "admin", "password": "TestPanel!2026"})
        self.assertEqual(status, 200)
        c.csrf = body["csrf"]
        status, state, _ = c.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(state["summary"]["nodes"], 2)
        self.assertEqual(state["summary"]["subs"], 1)

        status, audit2, _ = c.request("GET", "/api/audit?limit=20")
        self.assertIn("登录成功", [item["action"] for item in audit2["items"]])


if __name__ == "__main__":
    unittest.main()
