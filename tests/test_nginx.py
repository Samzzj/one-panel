"""自偷自 Nginx 配置生成测试。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from panel.nginx import plan, render_selfsteal, valid_domain, valid_hostport

SETTINGS = {
    "nginx_upstream": "https://www.lovelive-anime.jp",
    "nginx_listen": "127.0.0.1:8003",
    "nginx_conf": "/etc/nginx/conf.d/reality-selfsteal.conf",
    "cert_dir": "/etc/letsencrypt/live",
    "panel_addr": "127.0.0.1:8080",
    "default_sni": "node.example.com",
    "xver": "1",
    # 指到一个不存在的路径：preflight 读不到配置只会警告，
    # 否则在真的装了面板的机器上，测试会读到线上 config.json 而误报
    "xray_config": "/nonexistent/xray-config.json",
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

    def test_no_sub_block_for_nodes(self) -> None:
        conf = render_selfsteal(
            "node.example.com", "https://example.org", "127.0.0.1:8003",
            "/etc/letsencrypt/live", 1, "127.0.0.1:8080", include_sub=False,
        )
        self.assertNotIn("location ^~ /sub/", conf)
        self.assertIn("proxy_pass https://$reality_upstream$request_uri;", conf)

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

    def test_plan_dest_mismatch_fails(self) -> None:
        node = {"sni": "node.example.com", "dest": "127.0.0.1:9999", "xver": 1}
        result = plan(SETTINGS, node)
        self.assertFalse(result["ok"])
        self.assertIn("dest", result["error"])
        self.assertTrue(any(c["id"] == "dest-mismatch" for c in result["checks"]))

    def test_plan_static_mode(self) -> None:
        settings = {**SETTINGS, "site_mode": "static", "site_root": "/var/www/nav"}
        node = {"sni": "node.example.com", "dest": "127.0.0.1:8003", "xver": 1}
        result = plan(settings, node)
        self.assertEqual(result["mode"], "static")
        self.assertEqual(result["site_root"], "/var/www/nav")
        self.assertIn("root  /var/www/nav;", result["conf"])
        self.assertNotIn("sub_filter", result["conf"])

    def test_plan_remote_skips_host_checks(self) -> None:
        node = {"sni": "node.example.com", "dest": "127.0.0.1:8003", "xver": 1}
        result = plan(SETTINGS, node, local=False)
        self.assertTrue(result["ok"], result["error"])
        self.assertFalse(any(c["id"] in ("xray-config", "cert") for c in result["checks"]))

    def test_plan_detects_servernames_mismatch(self) -> None:
        """本机 config.json 里的 serverNames 与 SNI 不一致时必须拦住。"""
        config = Path(__file__).with_name("_xray_config_fixture.json")
        config.write_text(
            json.dumps(
                {
                    "inbounds": [
                        {
                            "port": 443,
                            "streamSettings": {
                                "security": "reality",
                                "realitySettings": {
                                    "serverNames": ["other.example.com"],
                                    "dest": "127.0.0.1:8003",
                                    "xver": 1,
                                },
                            },
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        self.addCleanup(lambda: config.unlink(missing_ok=True))

        node = {"sni": "node.example.com", "dest": "127.0.0.1:8003", "xver": 1}
        result = plan({**SETTINGS, "xray_config": str(config)}, node)
        self.assertFalse(result["ok"])
        self.assertTrue(any(c["id"] == "servernames" for c in result["checks"]))
        self.assertIn("serverNames", result["error"])

    def test_validators(self) -> None:
        self.assertTrue(valid_domain("node.example.com"))
        self.assertFalse(valid_domain("-bad.example.com"))
        self.assertTrue(valid_hostport("127.0.0.1:8003"))
        self.assertFalse(valid_hostport("127.0.0.1"))


class StaticSiteTest(unittest.TestCase):
    def _render(self, **kwargs) -> str:
        return render_selfsteal(
            "node.example.com",
            "https://www.lovelive-anime.jp",
            "127.0.0.1:8003",
            "/etc/letsencrypt/live",
            1,
            "127.0.0.1:8080",
            **kwargs,
        )

    def test_static_root_and_fallback(self) -> None:
        conf = self._render(site_root="/var/www/nav")
        self.assertIn("root  /var/www/nav;", conf)
        self.assertIn("try_files $uri $uri/ =404;", conf)
        self.assertIn("location ^~ /sub/ {", conf)
        self.assertNotIn("resolver", conf)
        self.assertNotIn("proxy_pass https://", conf)
        self.assertNotIn("proxy_pass https://$reality_upstream", conf)
        self.assertNotIn("map $http_upgrade", conf)

    def test_static_keeps_tls_and_hides_version(self) -> None:
        conf = self._render(site_root="/var/www/nav")
        self.assertIn("ssl_protocols       TLSv1.2 TLSv1.3;", conf)
        self.assertIn("server_tokens off;", conf)
        self.assertIn("listen 127.0.0.1:8003 ssl proxy_protocol http2;", conf)

    def test_site_root_injection_rejected(self) -> None:
        for bad in ("/var/www/nav; rm -rf /", "var/www/nav", "/var/www/../etc", "/var/www/na v"):
            with self.assertRaises(ValueError):
                self._render(site_root=bad)


class LoopbackTest(unittest.TestCase):
    def test_public_listen_rejected(self) -> None:
        for addr in ("0.0.0.0:8003", "*:8003", "192.168.1.10:8003", "[::]:8003"):
            with self.assertRaises(ValueError):
                render_selfsteal("node.example.com", "https://example.org", addr, "/c", 1, "127.0.0.1:8080")

    def test_ipv6_loopback_allowed(self) -> None:
        conf = render_selfsteal("node.example.com", "https://example.org", "[::1]:8003", "/c", 1, "127.0.0.1:8080")
        self.assertIn("listen [::1]:8003 ssl proxy_protocol http2;", conf)


if __name__ == "__main__":
    unittest.main()
