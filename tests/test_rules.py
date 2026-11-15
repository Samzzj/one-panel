"""设置校验、有效期语义、YAML 标量、API 地址解析的回归测试。"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from panel.api import _drop_unchanged_expiry, _validate_settings
from panel.httpd import ApiError
from panel.links import _yaml_scalar
from panel.util import now

from tests.test_httpd import FakeApp


def request(client_ip: str = "203.0.113.9") -> SimpleNamespace:
    return SimpleNamespace(client_ip=client_ip)


class SettingsValidationTest(unittest.TestCase):
    def app(self, allowlist_loopback: str = "1") -> FakeApp:
        return FakeApp({"access_allowlist_loopback": allowlist_loopback}, None)

    def test_non_loopback_listen_rejected(self) -> None:
        with self.assertRaises(ApiError):
            _validate_settings(self.app(), request(), {"nginx_listen": "0.0.0.0:8003"})

    def test_loopback_listen_accepted(self) -> None:
        _validate_settings(self.app(), request(), {"nginx_listen": "127.0.0.1:8003"})

    def test_bad_cidr_rejected(self) -> None:
        # 非法 CIDR 进库后，每个请求都会在 parse_rules 里抛异常 -> 500
        with self.assertRaises(ApiError):
            _validate_settings(self.app(), request(), {"access_allowlist": "10.0.0.0/33"})

    def test_allowlist_self_lock_rejected(self) -> None:
        with self.assertRaises(ApiError) as ctx:
            _validate_settings(self.app(), request("198.51.100.7"), {"access_allowlist": "10.0.0.0/8"})
        self.assertIn("锁在外面", str(ctx.exception))

    def test_allowlist_containing_caller_accepted(self) -> None:
        _validate_settings(self.app(), request("198.51.100.7"), {"access_allowlist": "198.51.100.0/24"})

    def test_site_mode_checked(self) -> None:
        with self.assertRaises(ApiError):
            _validate_settings(self.app(), request(), {"site_mode": "nginx"})

    def test_bad_site_root_rejected(self) -> None:
        with self.assertRaises(ApiError):
            _validate_settings(self.app(), request(), {"site_root": "var/www/nav"})


class ExpiryRuleTest(unittest.TestCase):
    """编辑订阅时，前端回填的剩余天数不应该悄悄改到期时间。"""

    def sub(self, days: int) -> dict:
        return {"expires_at": now() + days * 86400 if days else 0}

    def test_unchanged_value_is_dropped(self) -> None:
        data = {"expires_days": 7, "note": "x"}
        out = _drop_unchanged_expiry(self.sub(7), data)
        self.assertNotIn("expires_days", out)
        self.assertEqual(out["note"], "x")

    def test_changed_value_is_kept(self) -> None:
        out = _drop_unchanged_expiry(self.sub(7), {"expires_days": 30})
        self.assertEqual(out["expires_days"], 30)

    def test_zero_on_existing_sub_is_dropped(self) -> None:
        # 已过期订阅在表单里显示 0；直接保存不该把它变成永久
        out = _drop_unchanged_expiry(self.sub(-3), {"expires_days": 0})
        self.assertNotIn("expires_days", out)

    def test_explicit_permanent_kept(self) -> None:
        out = _drop_unchanged_expiry(self.sub(7), {"expires_days": 0, "permanent": True})
        self.assertEqual(out["expires_days"], 0)
        self.assertTrue(out["permanent"])

    def test_permanent_sub_unaffected(self) -> None:
        out = _drop_unchanged_expiry({"expires_at": 0}, {"expires_days": 30})
        self.assertEqual(out["expires_days"], 30)


class YamlScalarTest(unittest.TestCase):
    def test_native_scalars_are_quoted(self) -> None:
        for text in ("true", "False", "null", "~", "123", "1.5", "yes", "on"):
            out = _yaml_scalar(text)
            self.assertTrue(out.startswith('"'), f"{text} 应加引号，实际 {out}")

    def test_normal_text_stays_plain(self) -> None:
        self.assertEqual(_yaml_scalar("香港 01"), '"香港 01"')
        self.assertEqual(_yaml_scalar("hk-01.example.com"), "hk-01.example.com")

    def test_bool_and_number_keep_types(self) -> None:
        self.assertEqual(_yaml_scalar(True), "true")
        self.assertEqual(_yaml_scalar(443), "443")


class ApiAddressTest(unittest.TestCase):
    def test_ipv6_brackets_stripped(self) -> None:
        from panel.xray import _api_address

        self.assertEqual(_api_address({"xray_api": "[::1]:10085"}), ("::1", 10085))

    def test_bad_port_falls_back(self) -> None:
        from panel.xray import _api_address

        self.assertEqual(_api_address({"xray_api": "127.0.0.1:abc"}), ("127.0.0.1", 10085))

    def test_default(self) -> None:
        from panel.xray import _api_address

        self.assertEqual(_api_address({}), ("127.0.0.1", 10085))


if __name__ == "__main__":
    unittest.main()
