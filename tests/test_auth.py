"""密码哈希与登录限流测试。"""

from __future__ import annotations

import time
import unittest

from panel.auth import LoginLimiter, hash_password, password_problem, verify_password


class PasswordTest(unittest.TestCase):
    def test_hash_verify(self) -> None:
        stored = hash_password("TestPanel!2026")
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))
        self.assertTrue(verify_password("TestPanel!2026", stored))
        self.assertFalse(verify_password("wrong-password", stored))

    def test_unique_salt(self) -> None:
        self.assertNotEqual(hash_password("same-password"), hash_password("same-password"))

    def test_malformed_hash(self) -> None:
        self.assertFalse(verify_password("x", "not-a-hash"))
        self.assertFalse(verify_password("x", "pbkdf2_sha256$1$bad"))

    def test_policy(self) -> None:
        self.assertTrue(password_problem("short"))
        self.assertTrue(password_problem("1234567890123"))
        self.assertEqual(password_problem("TestPanel!2026"), "")


class LimiterTest(unittest.TestCase):
    def test_blocks_after_limit(self) -> None:
        limiter = LoginLimiter(limit=3, window=60)
        for _ in range(3):
            limiter.fail("1.2.3.4")
        self.assertGreater(limiter.blocked("1.2.3.4"), 0)
        self.assertEqual(limiter.blocked("5.6.7.8"), 0)
        limiter.reset("1.2.3.4")
        self.assertEqual(limiter.blocked("1.2.3.4"), 0)

    def test_window_expiry(self) -> None:
        limiter = LoginLimiter(limit=1, window=1)
        limiter.fail("9.9.9.9")
        self.assertGreater(limiter.blocked("9.9.9.9"), 0)
        time.sleep(1.1)
        self.assertEqual(limiter.blocked("9.9.9.9"), 0)


if __name__ == "__main__":
    unittest.main()
