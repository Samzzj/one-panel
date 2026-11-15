"""HTTP 层与端口校验的回归测试。

覆盖两个曾经能把安全承诺架空的点：
1. 客户端 IP 取错 —— 伪造 CF-Connecting-IP / X-Forwarded-For 就能让
   登录限流和 IP 白名单失效。
2. 节点端口只跟数据库里的节点比，不跟本机系统端口比 —— 选到 8003/8080/10085
   会等到重启 Xray 才失败。
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from panel.api import _check_reserved_port, _reserved_ports
from panel.httpd import ApiError, Handler
from panel.xray import _restore, _snapshot

SETTINGS = {
    "nginx_listen": "127.0.0.1:8003",
    "panel_addr": "127.0.0.1:8080",
    "xray_api": "127.0.0.1:10085",
}


class FakeStore:
    def __init__(self, settings: dict, server: dict | None) -> None:
        self._settings = settings
        self._server = server

    def settings(self) -> dict:
        return dict(self._settings)

    def setting(self, key: str, default: str = "") -> str:
        return self._settings.get(key, default)

    def server(self, _sid: int) -> dict | None:
        return self._server


class FakeApp:
    def __init__(self, settings: dict, server: dict | None) -> None:
        self.store = FakeStore(settings, server)


def client_ip(headers: dict, peer: str = "127.0.0.1") -> str:
    fake_self = SimpleNamespace(client_address=(peer, 51234), headers=headers)
    return Handler._client_ip(fake_self)


class ClientIpTest(unittest.TestCase):
    def test_x_real_ip_wins(self) -> None:
        headers = {"X-Real-IP": "203.0.113.9", "X-Forwarded-For": "198.51.100.7, 203.0.113.9"}
        self.assertEqual(client_ip(headers), "203.0.113.9")

    def test_cloudflare_header_no_longer_trusted(self) -> None:
        # 曾经优先取 CF-Connecting-IP，客户端自带就能冒充白名单 IP
        headers = {"CF-Connecting-IP": "1.2.3.4", "X-Real-IP": "203.0.113.9"}
        self.assertEqual(client_ip(headers), "203.0.113.9")

    def test_forwarded_for_uses_last_hop(self) -> None:
        # nginx 用 $proxy_add_x_forwarded_for 追加真实地址，前面的都是客户端编的
        headers = {"X-Forwarded-For": "1.2.3.4, 203.0.113.9"}
        self.assertEqual(client_ip(headers), "203.0.113.9")

    def test_forwarded_for_spoof_without_real_ip(self) -> None:
        headers = {"X-Forwarded-For": "127.0.0.1, 198.51.100.7"}
        self.assertEqual(client_ip(headers), "198.51.100.7")

    def test_direct_peer_ignores_headers(self) -> None:
        headers = {"X-Real-IP": "1.2.3.4", "X-Forwarded-For": "1.2.3.4"}
        self.assertEqual(client_ip(headers, peer="192.0.2.55"), "192.0.2.55")

    def test_loopback_without_headers(self) -> None:
        self.assertEqual(client_ip({}), "127.0.0.1")


class ReservedPortTest(unittest.TestCase):
    def test_collects_system_ports(self) -> None:
        labels = _reserved_ports(FakeApp(SETTINGS, None))
        self.assertEqual(labels[8003], "nginx 回落监听")
        self.assertEqual(labels[8080], "面板自身")
        self.assertEqual(labels[10085], "Xray API")

    def test_local_node_rejects_reserved_port(self) -> None:
        app = FakeApp(SETTINGS, {"kind": "local"})
        for port in (8003, 8080, 10085):
            with self.assertRaises(ApiError) as ctx:
                _check_reserved_port(app, port, 1)
            self.assertIn(str(port), str(ctx.exception))

    def test_local_node_allows_normal_port(self) -> None:
        app = FakeApp(SETTINGS, {"kind": "local"})
        _check_reserved_port(app, 443, 1)

    def test_remote_node_not_checked(self) -> None:
        # 远程节点上本机的 8003/8080 与它无关
        app = FakeApp(SETTINGS, {"kind": "agent"})
        _check_reserved_port(app, 8003, 2)


class ConfigSnapshotTest(unittest.TestCase):
    def _file(self):
        from pathlib import Path

        # 直接放在 tests/ 下：某些沙箱不允许往新建的子目录里写
        path = Path(__file__).with_name("_snapshot_test.json")
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        self.addCleanup(lambda: Path(str(path) + ".panel-bak").unlink(missing_ok=True))
        return path

    def test_snapshot_and_restore(self) -> None:
        path = self._file()
        path.write_text('{"old": true}\n', encoding="utf-8")
        backup = _snapshot(str(path))
        self.assertIsNotNone(backup)
        path.write_text('{"new": true}\n', encoding="utf-8")
        self.assertTrue(_restore(str(path), backup))
        self.assertEqual(path.read_text(encoding="utf-8"), '{"old": true}\n')

    def test_snapshot_missing_file(self) -> None:
        missing = self._file()
        self.assertIsNone(_snapshot(str(missing)))
        self.assertFalse(_restore(str(missing), None))


if __name__ == "__main__":
    unittest.main()
