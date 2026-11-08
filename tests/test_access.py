"""访问白名单解析与匹配测试。"""

from __future__ import annotations

import unittest

from panel.access import is_allowed, normalize, parse_rules


class AccessTest(unittest.TestCase):
    def test_empty_means_allow_all(self) -> None:
        self.assertTrue(is_allowed("8.8.8.8", ""))
        self.assertTrue(is_allowed("8.8.8.8", "   \n  "))

    def test_single_ip(self) -> None:
        self.assertTrue(is_allowed("203.0.113.7", "203.0.113.7"))
        self.assertFalse(is_allowed("203.0.113.8", "203.0.113.7"))

    def test_cidr_v4(self) -> None:
        text = "10.0.0.0/8\n192.168.1.0/24"
        self.assertTrue(is_allowed("10.1.2.3", text))
        self.assertTrue(is_allowed("192.168.1.50", text))
        self.assertFalse(is_allowed("192.168.2.1", text))

    def test_cidr_v6(self) -> None:
        text = "2001:db8::/32"
        self.assertTrue(is_allowed("2001:db8::1", text))
        self.assertFalse(is_allowed("2001:db9::1", text))

    def test_loopback_switch(self) -> None:
        self.assertTrue(is_allowed("127.0.0.1", "203.0.113.7", include_loopback=True))
        self.assertFalse(is_allowed("127.0.0.1", "203.0.113.7", include_loopback=False))
        self.assertTrue(is_allowed("::1", "203.0.113.7", include_loopback=True))

    def test_mixed_versions_do_not_crash(self) -> None:
        self.assertFalse(is_allowed("8.8.8.8", "2001:db8::/32", include_loopback=False))
        self.assertFalse(is_allowed("2001:db8::1", "10.0.0.0/8", include_loopback=False))

    def test_invalid_ip(self) -> None:
        self.assertFalse(is_allowed("not-an-ip", "10.0.0.0/8", include_loopback=False))

    def test_normalize(self) -> None:
        text = "  10.0.0.0/8 \n\n10.0.0.0/8, 192.168.0.1 ; 2001:db8::/32 "
        self.assertEqual(normalize(text), "10.0.0.0/8\n192.168.0.1\n2001:db8::/32")

    def test_invalid_entry_raises(self) -> None:
        with self.assertRaises(ValueError):
            normalize("10.0.0.0/8\nnot-a-network")
        with self.assertRaises(ValueError):
            parse_rules("10.0.0.0/33")


if __name__ == "__main__":
    unittest.main()
