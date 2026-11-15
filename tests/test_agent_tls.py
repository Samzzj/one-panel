"""agent TLS 指纹固定的测试：真实起一个 TLS agent，面板侧用 AgentClient 连它。"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from agent import Agent, AgentServer, cert_fingerprint
from panel.remote import AgentClient, fingerprint_of

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, ".test-tls")


def make_cert(directory: str) -> tuple[str, str]:
    os.makedirs(directory, exist_ok=True)
    cert = os.path.join(directory, "tls.crt")
    key = os.path.join(directory, "tls.key")
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
         "-keyout", key, "-out", cert, "-subj", "/CN=agent-test"],
        check=True, capture_output=True,
    )
    return cert, key


def start_agent(cert: str, key: str) -> tuple[AgentServer, int]:
    args = argparse.Namespace(
        token="tok-123", xray_bin="xray", xray_config="/tmp/none.json",
        xray_api="127.0.0.1:10085", restart_cmd="true", status_cmd="true",
        nginx_dir="/tmp", allow=["127.0.0.1"],
    )
    agent = Agent(args)
    server = AgentServer(("127.0.0.1", 0), agent)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


@unittest.skipUnless(shutil.which("openssl"), "需要 openssl 生成测试证书")
class AgentTlsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        shutil.rmtree(WORK, ignore_errors=True)
        cls.cert, cls.key = make_cert(WORK)
        cls.server, cls.port = start_agent(cls.cert, cls.key)
        cls.url = f"https://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(WORK, ignore_errors=True)

    def client(self, pin: str = "") -> AgentClient:
        return AgentClient({"agent_url": self.url, "token": "tok-123", "agent_cert": pin})

    def test_probe_matches_cert_fingerprint(self) -> None:
        expected = cert_fingerprint(self.cert)
        self.assertEqual(len(expected), 64)
        self.assertEqual(self.client().probe_fingerprint(), expected)

    def test_pinned_connection_works(self) -> None:
        pin = self.client().probe_fingerprint()
        result = self.client(pin).health()
        self.assertTrue(result.get("ok"), result)

    def test_wrong_pin_is_rejected(self) -> None:
        result = self.client("00" * 32).health()
        self.assertFalse(result.get("ok"))
        self.assertIn("指纹不匹配", result.get("error", ""))

    def test_https_without_pin_is_rejected(self) -> None:
        result = self.client("").health()
        self.assertFalse(result.get("ok"))
        self.assertIn("测试", result.get("error", ""))

    def test_wrong_token_is_rejected(self) -> None:
        pin = self.client().probe_fingerprint()
        bad = AgentClient({"agent_url": self.url, "token": "wrong", "agent_cert": pin})
        result = bad.health()
        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("status"), 401)

    def test_fingerprint_helper(self) -> None:
        self.assertEqual(fingerprint_of(b""), hashlib.sha256(b"").hexdigest())


if __name__ == "__main__":
    unittest.main()
