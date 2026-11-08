"""自偷自 Nginx 配置生成测试。"""

from __future__ import annotations

import unittest

from panel.nginx import plan, render_selfsteal, valid_domain, valid_hostport

SETTINGS = {
    "nginx_upstream": "https://www.lovelive-anime.jp",
    "nginx_listen": "127.0.0.1:8003",
    "nginx_conf": "/etc/nginx/conf.d/reality-selfsteal.conf",
    "cert_dir": "/etc/letsencrypt/live",
    "panel_addr": "127.0.0.1:8080",
    "default_sni": "node.example.com",
    "xver": "1",
}


class RenderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.conf = render_selfsteal(
            "node.example.com", "https://www.lovelive-anime.jp", "127.0.0.1:8003",
            "/etc/letsencrypt/live", 1, "127.0.0.1:8080",
        )

    def test_proxy_protocol_listen(self) -> None:
        self.assertIn("listen 127.0.0.1:8003 ssl proxy_protocol http2;", self.conf)
        self.assertIn("set_real_ip_from 127.0.0.1;", self.conf)
        self.assertIn("real_ip_header proxy_protocol;", self.conf)

    def test_certificate_paths(self) -> None:
        self.assertIn("ssl_certificate     /etc/letsencrypt/live/node.example.com/fullchain.pem;", self.conf)
        self.assertIn("ssl_certificate_key /etc/letsencrypt/live/node.example.com/privkey.pem;", self.conf)
        self.assertIn("ssl_protocols       TLSv1.2 TLSv1.3;", self.conf)

    def test_upstream_reverse_proxy(self) -> None:
        self.assertIn('set $reality_upstream "www.lovelive-anime.jp";', self.conf)
        self.assertIn("proxy_pass https://$reality_upstream$request_uri;", self.conf)
        self.assertIn("proxy_ssl_server_name on;", self.conf)
        self.assertIn("sub_filter 'https://www.lovelive-anime.jp' 'https://$host';", self.conf)

    def test_subscription_route(self) -> None:
        self.assertIn("location ^~ /sub/ {", self.conf)
        self.assertIn("proxy_pass http://127.0.0.1:8080;", self.conf)
        self.assertIn("X-Forwarded-Proto https;", self.conf)

    def test_no_proxy_protocol_when_disabled(self) -> None:
        conf = render_selfsteal(
            "node.example.com", "https://example.org", "127.0.0.1:8004",
            "/etc/letsencrypt/live", 0, "127.0.0.1:8080",
        )
        self.assertNotIn("proxy_protocol", conf)
        self.assertNotIn("set_real_ip_from", conf)

    def test_invalid_domain_rejected(self) -> None:
        with self.assertRaises(ValueError):
            render_selfsteal("node example.com", "https://example.org", "127.0.0.1:8003", "/c", 1, "127.0.0.1:8080")
        with self.assertRaises(ValueError):
            render_selfsteal("127.0.0.1", "https://example.org", "127.0.0.1:8003", "/c", 1, "127.0.0.1:8080")

    def test_injection_rejected(self) -> None:
        with self.assertRaises(ValueError):
            render_selfsteal("node.example.com", "https://example.org", "127.0.0.1:8003;bad", "/c", 1, "127.0.0.1:8080")


class PlanTest(unittest.TestCase):
    def test_plan_ok(self) -> None:
        node = {"sni": "node.example.com", "dest": "127.0.0.1:8003", "xver": 1}
        result = plan(SETTINGS, node)
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(len(result["steps"]), 6)
        self.assertEqual(result["cert_path"], "/etc/letsencrypt/live/node.example.com/fullchain.pem")
        self.assertTrue(result["conf"])

    def test_plan_missing_sni(self) -> None:
        result = plan({**SETTINGS, "default_sni": ""}, None)
        self.assertFalse(result["ok"])
        self.assertIn("SNI", result["error"])

    def test_plan_dest_mismatch_warns(self) -> None:
        node = {"sni": "node.example.com", "dest": "127.0.0.1:9999", "xver": 1}
        result = plan(SETTINGS, node)
        self.assertTrue(any("dest" in warning for warning in result["warnings"]))

    def test_validators(self) -> None:
        self.assertTrue(valid_domain("node.example.com"))
        self.assertFalse(valid_domain("-bad.example.com"))
        self.assertTrue(valid_hostport("127.0.0.1:8003"))
        self.assertFalse(valid_hostport("127.0.0.1"))


if __name__ == "__main__":
    unittest.main()
