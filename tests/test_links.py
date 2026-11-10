"""分享链接、订阅与 Clash YAML 测试。"""

from __future__ import annotations

import base64
import unittest
from urllib.parse import parse_qs, unquote, urlsplit

from panel.links import (
    build_links,
    clash_config,
    clash_proxy,
    subscription_payload,
    vless_link,
)

VISION = {
    "transport": "vision",
    "port": 443,
    "sni": "node.example.com",
    "public_key": "urMekeRvAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "short_ids": ["ab12cd34"],
    "xhttp_path": "/",
    "xhttp_mode": "auto",
    "fingerprint": "chrome",
}

XHTTP = {
    "transport": "xhttp",
    "port": 8443,
    "sni": "node.example.com",
    "public_key": "urMekeRvAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "short_ids": ["ab12cd34"],
    "xhttp_path": "/media",
    "xhttp_mode": "packet-up",
    "fingerprint": "firefox",
}

UUID = "1b09c2ec-e5e9-43d6-bc82-f0b900c6c2e9"


class LinkTest(unittest.TestCase):
    def test_vision_link(self) -> None:
        link = vless_link(VISION, UUID, "香港 Vision", "203.0.113.10")
        self.assertTrue(link.startswith(f"vless://{UUID}@203.0.113.10:443?"))
        parts = urlsplit(link)
        query = parse_qs(parts.query)
        self.assertEqual(query["security"], ["reality"])
        self.assertEqual(query["sni"], ["node.example.com"])
        self.assertEqual(query["type"], ["tcp"])
        self.assertEqual(query["flow"], ["xtls-rprx-vision"])
        self.assertEqual(query["sid"], ["ab12cd34"])
        self.assertEqual(query["spx"], ["/"])
        self.assertEqual(query["fp"], ["chrome"])
        self.assertEqual(query["support-x25519mlkem768"], ["true"])
        self.assertEqual(unquote(parts.fragment), "香港 Vision")

    def test_xhttp_link(self) -> None:
        link = vless_link(XHTTP, UUID, "日本 XHTTP", "203.0.113.10")
        query = parse_qs(urlsplit(link).query)
        self.assertEqual(query["type"], ["xhttp"])
        self.assertEqual(query["path"], ["/media"])
        self.assertEqual(query["mode"], ["packet-up"])
        self.assertEqual(query["host"], ["node.example.com"])
        self.assertNotIn("flow", query)
        self.assertEqual(query["fp"], ["firefox"])
        self.assertEqual(query["support-x25519mlkem768"], ["true"])

    def test_ipv6_host_wrapped(self) -> None:
        link = vless_link(VISION, UUID, "v6", "2001:db8::1")
        self.assertIn("@[2001:db8::1]:443?", link)

    def test_clash_vision(self) -> None:
        proxy = clash_proxy(VISION, UUID, "hk", "203.0.113.10")
        self.assertEqual(proxy["type"], "vless")
        self.assertEqual(proxy["network"], "tcp")
        self.assertEqual(proxy["flow"], "xtls-rprx-vision")
        self.assertTrue(proxy["tls"])
        self.assertEqual(proxy["reality-opts"]["public-key"], VISION["public_key"])
        self.assertEqual(proxy["reality-opts"]["short-id"], "ab12cd34")
        self.assertTrue(proxy["reality-opts"]["support-x25519mlkem768"])

    def test_clash_xhttp(self) -> None:
        proxy = clash_proxy(XHTTP, UUID, "jp", "203.0.113.10")
        self.assertEqual(proxy["network"], "xhttp")
        self.assertEqual(proxy["xhttp-opts"]["path"], "/media")
        self.assertEqual(proxy["xhttp-opts"]["mode"], "packet-up")
        self.assertNotIn("flow", proxy)

    def test_clash_yaml_shape(self) -> None:
        text = clash_config([clash_proxy(VISION, UUID, "hk", "203.0.113.10")], "Test Panel")
        self.assertIn("proxies:\n  - name: hk", text)
        self.assertIn("reality-opts:", text)
        self.assertIn("public-key:", text)
        self.assertIn("proxy-groups:", text)
        self.assertIn("MATCH,PROXY", text)
        # 不应出现 Python 的 None/True 字面量
        self.assertNotIn("None", text)
        self.assertNotIn("True", text)


class SubscriptionTest(unittest.TestCase):
    def test_base64_roundtrip(self) -> None:
        links = ["vless://a@b:1?x=1#n1", "vless://c@d:2?y=2#n2"]
        payload = subscription_payload(links)
        decoded = base64.b64decode(payload).decode("utf-8")
        self.assertEqual(decoded.split("\n"), links)

    def test_build_links_filters_disabled(self) -> None:
        sub = {
            "name": "用户A",
            "clients": [
                {
                    "uuid": UUID,
                    "enabled": 1,
                    "node_enabled": 1,
                    "node_name": "HK",
                    "transport": "vision",
                    "port": 443,
                    "sni": "node.example.com",
                    "public_key": VISION["public_key"],
                    "short_ids": '["ab12cd34"]',
                    "xhttp_path": "/",
                    "xhttp_mode": "auto",
                    "fingerprint": "chrome",
                },
                {
                    "uuid": "disabled-uuid",
                    "enabled": 0,
                    "node_enabled": 1,
                    "node_name": "JP",
                    "transport": "xhttp",
                    "port": 8443,
                    "sni": "node.example.com",
                    "public_key": VISION["public_key"],
                    "short_ids": '["ab12cd34"]',
                    "xhttp_path": "/m",
                    "xhttp_mode": "auto",
                    "fingerprint": "chrome",
                },
            ],
        }
        links = build_links(sub, "203.0.113.10")
        self.assertEqual(len(links), 1)
        self.assertIn("用户A-HK", unquote(links[0]))
        self.assertIn("type=tcp", links[0])

    def test_server_address_wins(self) -> None:
        sub = {
            "name": "用户A",
            "clients": [
                {
                    "uuid": UUID,
                    "enabled": 1,
                    "node_enabled": 1,
                    "server_enabled": 1,
                    "server_address": "198.51.100.7",
                    "node_name": "HK",
                    "transport": "vision",
                    "port": 443,
                    "sni": "node.example.com",
                    "public_key": VISION["public_key"],
                    "short_ids": '["ab12cd34"]',
                    "xhttp_path": "/",
                    "xhttp_mode": "auto",
                    "fingerprint": "chrome",
                }
            ],
        }
        links = build_links(sub, "203.0.113.10")
        self.assertEqual(len(links), 1)
        self.assertIn("@198.51.100.7:443?", links[0])

    def test_disabled_server_skipped(self) -> None:
        sub = {
            "name": "用户A",
            "clients": [
                {
                    "uuid": UUID,
                    "enabled": 1,
                    "node_enabled": 1,
                    "server_enabled": 0,
                    "server_address": "198.51.100.7",
                    "node_name": "HK",
                    "transport": "vision",
                    "port": 443,
                    "sni": "node.example.com",
                    "public_key": VISION["public_key"],
                    "short_ids": '["ab12cd34"]',
                    "xhttp_path": "/",
                    "xhttp_mode": "auto",
                    "fingerprint": "chrome",
                }
            ],
        }
        self.assertEqual(build_links(sub, "203.0.113.10"), [])


if __name__ == "__main__":
    unittest.main()
