"""追踪模块的离线测试：网络一律打桩，手机号用真实号码库。"""

from __future__ import annotations

import unittest
from unittest import mock

from judgedee import trace

IPAPI_OK = {
    "status": "success",
    "query": "8.8.8.8",
    "country": "United States",
    "countryCode": "US",
    "region": "VA",
    "regionName": "Virginia",
    "city": "Ashburn",
    "zip": "20149",
    "lat": 39.03,
    "lon": -77.5,
    "timezone": "America/New_York",
    "isp": "Google LLC",
    "org": "Google Public DNS",
    "as": "AS15169 Google LLC",
    "mobile": False,
    "proxy": True,
    "hosting": True,
}

IPINFO_OK = {
    "ip": "1.1.1.1",
    "city": "Sydney",
    "region": "New South Wales",
    "country": "AU",
    "loc": "-33.8679,151.2073",
    "org": "AS13335 Cloudflare, Inc.",
    "postal": "1000",
    "timezone": "Australia/Sydney",
}


class NormalizeIpTest(unittest.TestCase):
    def test_accepts_v4_and_v6(self):
        self.assertEqual(trace.normalize_ip(" 8.8.8.8 "), "8.8.8.8")
        self.assertEqual(trace.normalize_ip("[::1]"), "::1")

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            trace.normalize_ip("999.1.1.1")
        with self.assertRaises(ValueError):
            trace.normalize_ip("")


class LookupIpTest(unittest.TestCase):
    def test_invalid_ip_returns_error_without_request(self):
        with mock.patch.object(trace, "_get_json") as fake:
            result = trace.lookup_ip("999.1.1.1")
        fake.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertIn("不合法", result["error"])

    def test_primary_provider(self):
        with mock.patch.object(trace, "_get_json", return_value=dict(IPAPI_OK)):
            result = trace.lookup_ip("8.8.8.8")
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "ip-api.com")
        fields = dict(result["fields"])
        self.assertEqual(fields["国家"], "United States")
        self.assertEqual(fields["城市"], "Ashburn")
        self.assertEqual(fields["代理 / VPN"], "是")
        self.assertIn("39.03", result["maps"])

    def test_falls_back_to_second_provider(self):
        calls = []

        def fake(url, proxy, timeout):
            calls.append(url)
            if "ip-api.com" in url:
                raise RuntimeError("502")
            return dict(IPINFO_OK)

        with mock.patch.object(trace, "_get_json", side_effect=fake):
            result = trace.lookup_ip("1.1.1.1")
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "ipinfo.io")
        self.assertEqual(dict(result["fields"])["城市"], "Sydney")
        self.assertEqual(len(calls), 2)

    def test_both_providers_fail(self):
        with mock.patch.object(trace, "_get_json", side_effect=RuntimeError("boom")):
            result = trace.lookup_ip("1.1.1.1")
        self.assertFalse(result["ok"])
        self.assertIn("ip-api.com", result["error"])

    def test_provider_error_payload_is_reported(self):
        with mock.patch.object(
            trace, "_get_json", return_value={"status": "fail", "message": "private range"}
        ):
            result = trace.lookup_ip("10.0.0.1")
        self.assertFalse(result["ok"])
        self.assertIn("private range", result["error"])


class MapLinkTest(unittest.TestCase):
    def test_quotes_address(self):
        link = trace.map_link("北京市 海淀区")
        self.assertTrue(link.startswith("https://www.google.com/maps/search/"))
        self.assertNotIn(" ", link)


class PhoneTest(unittest.TestCase):
    def setUp(self):
        try:
            import phonenumbers  # noqa: F401
        except ImportError:  # pragma: no cover - 环境没装就跳过
            self.skipTest("phonenumbers 未安装")

    def test_parses_chinese_mobile(self):
        result = trace.parse_phone("+86 138 0013 8000")
        self.assertTrue(result["ok"])
        self.assertEqual(result["region"], "CN")
        self.assertEqual(result["e164"], "+8613800138000")
        self.assertIn("北京", result["location"])
        self.assertEqual(result["operator"], "中国移动")
        fields = dict(result["fields"])
        self.assertEqual(fields["号码类型"], "手机")
        self.assertEqual(fields["是否有效"], "有效")

    def test_default_region_applies(self):
        result = trace.parse_phone("13800138000", region="CN")
        self.assertTrue(result["ok"])
        self.assertEqual(result["e164"], "+8613800138000")

    def test_short_number_errors(self):
        result = trace.parse_phone("+861")
        self.assertFalse(result["ok"])
        self.assertTrue(result["error"])

    def test_blank_input_errors(self):
        result = trace.parse_phone("   ")
        self.assertFalse(result["ok"])
        self.assertIn("请输入", result["error"])

    def test_missing_dependency_message(self):
        with mock.patch.dict("sys.modules", {"phonenumbers": None}):
            result = trace.parse_phone("+8613800138000")
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
