"""Xray 服务端配置生成测试。"""

from __future__ import annotations

import json
import unittest

from panel.x25519 import generate_keypair
from panel.xray import build_config

PRIVATE, PUBLIC = generate_keypair()

SETTINGS = {
    "xray_api": "127.0.0.1:10085",
    "xray_config": "/tmp/config.json",
}

VISION_NODE = {
    "id": 1,
    "name": "HK Vision",
    "transport": "vision",
    "listen": "0.0.0.0",
    "port": 443,
    "sni": "node.example.com",
    "dest": "127.0.0.1:8003",
    "xver": 1,
    "private_key": PRIVATE,
    "public_key": PUBLIC,
    "short_ids": ["ab12cd34"],
    "xhttp_path": "/",
    "xhttp_mode": "auto",
    "fingerprint": "chrome",
}

XHTTP_NODE = {
    "id": 2,
    "name": "JP XHTTP",
    "transport": "xhttp",
    "listen": "0.0.0.0",
    "port": 8443,
    "sni": "node.example.com",
    "dest": "127.0.0.1:8003",
    "xver": 1,
    "private_key": PRIVATE,
    "public_key": PUBLIC,
    "short_ids": ["ab12cd34"],
    "xhttp_path": "/media",
    "xhttp_mode": "auto",
    "fingerprint": "chrome",
}

CLIENT = {
    "id": 7,
    "node_id": 1,
    "uuid": "1b09c2ec-e5e9-43d6-bc82-f0b900c6c2e9",
    "enabled": True,
}


class BuildConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = build_config(
            [VISION_NODE, XHTTP_NODE], [CLIENT, {**CLIENT, "id": 8, "node_id": 2}], SETTINGS
        )
        self.inbounds = {item["tag"]: item for item in self.config["inbounds"]}

    def test_api_inbound_present(self) -> None:
        api = self.inbounds["api"]
        self.assertEqual(api["protocol"], "dokodemo-door")
        self.assertEqual(api["port"], 10085)
        self.assertEqual(api["listen"], "127.0.0.1")

    def test_vision_inbound(self) -> None:
        inbound = self.inbounds["node-1"]
        self.assertEqual(inbound["protocol"], "vless")
        self.assertEqual(inbound["settings"]["decryption"], "none")
        self.assertEqual(inbound["settings"]["clients"][0]["flow"], "xtls-rprx-vision")
        self.assertEqual(inbound["settings"]["clients"][0]["email"], "c7")

        stream = inbound["streamSettings"]
        self.assertEqual(stream["network"], "tcp")
        self.assertEqual(stream["security"], "reality")
        reality = stream["realitySettings"]
        self.assertEqual(reality["dest"], "127.0.0.1:8003")
        self.assertEqual(reality["xver"], 1)
        self.assertEqual(reality["serverNames"], ["node.example.com"])
        self.assertEqual(reality["privateKey"], PRIVATE)
        self.assertEqual(reality["shortIds"], ["ab12cd34"])
        self.assertFalse(reality["show"])
        self.assertNotIn("xhttpSettings", stream)

    def test_xhttp_inbound(self) -> None:
        inbound = self.inbounds["node-2"]
        stream = inbound["streamSettings"]
        self.assertEqual(stream["network"], "xhttp")
        self.assertEqual(stream["xhttpSettings"], {"path": "/media", "mode": "auto"})
        self.assertEqual(stream["security"], "reality")
        # XHTTP 不能带 Vision flow
        self.assertNotIn("flow", inbound["settings"]["clients"][0])

    def test_no_geoip_dependency(self) -> None:
        text = json.dumps(self.config)
        self.assertNotIn("geoip:", text)
        rules = self.config["routing"]["rules"]
        self.assertEqual(rules[0]["outboundTag"], "api")
        self.assertIn("bittorrent", json.dumps(rules))

    def test_stats_policy(self) -> None:
        level = self.config["policy"]["levels"]["0"]
        self.assertTrue(level["statsUserUplink"])
        self.assertTrue(level["statsUserDownlink"])
        self.assertEqual(self.config["api"]["services"], ["HandlerService", "LoggerService", "StatsService"])

    def test_outbounds(self) -> None:
        protocols = [item["protocol"] for item in self.config["outbounds"]]
        self.assertEqual(protocols, ["freedom", "blackhole"])

    def test_json_serializable(self) -> None:
        text = json.dumps(self.config, ensure_ascii=False)
        self.assertIn("realitySettings", text)
        json.loads(text)


if __name__ == "__main__":
    unittest.main()
