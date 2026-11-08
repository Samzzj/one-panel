"""X25519 与 REALITY 密钥格式测试（RFC 7748 官方向量）。"""

from __future__ import annotations

import unittest

from panel.util import b64url_decode, b64url_encode
from panel.x25519 import generate_keypair, public_from_private, public_from_private_b64, x25519

ALICE_PRIVATE = bytes.fromhex("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
ALICE_PUBLIC = bytes.fromhex("8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a")
BOB_PRIVATE = bytes.fromhex("5dab087e624a8a4b79e17f8b83800ee66f3bb1292618b6fd1c2f8b27ff88e0eb")
BOB_PUBLIC = bytes.fromhex("de9edb7d7b7dc1b4d35b61c2ece435373f8343c85b78674dadfc7e146f882b4f")
SHARED = bytes.fromhex("4a5d9d5ba4ce2de1728e3bf480350f25e07e21c947d19e3376f09b3c1e161742")


class X25519Test(unittest.TestCase):
    def test_rfc7748_alice_public(self) -> None:
        self.assertEqual(public_from_private(ALICE_PRIVATE), ALICE_PUBLIC)

    def test_rfc7748_bob_public(self) -> None:
        self.assertEqual(public_from_private(BOB_PRIVATE), BOB_PUBLIC)

    def test_rfc7748_shared_secret(self) -> None:
        self.assertEqual(x25519(ALICE_PRIVATE, BOB_PUBLIC), SHARED)
        self.assertEqual(x25519(BOB_PRIVATE, ALICE_PUBLIC), SHARED)

    def test_keypair_roundtrip(self) -> None:
        private_b64, public_b64 = generate_keypair()
        self.assertEqual(len(b64url_decode(private_b64)), 32)
        self.assertEqual(len(b64url_decode(public_b64)), 32)
        self.assertEqual(public_from_private_b64(private_b64), public_b64)
        self.assertNotIn("=", private_b64)
        self.assertNotIn("=", public_b64)

    def test_base64url_no_padding(self) -> None:
        raw = bytes(range(32))
        encoded = b64url_encode(raw)
        self.assertEqual(b64url_decode(encoded), raw)
        self.assertEqual(len(encoded), 43)


if __name__ == "__main__":
    unittest.main()
