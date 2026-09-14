"""portal_stats_exporter の単体テスト。ネットワークには出ない。
実行: cd src && python3 portal_stats_exporter_test.py
"""
import os
import unittest
from unittest import mock

import portal_stats_exporter as pse


class EnabledTest(unittest.TestCase):
    def test_disabled_when_env_empty(self):
        with mock.patch.dict(os.environ, {"PORTAL_INGEST_URL": "", "PORTAL_INGEST_TOKEN": ""}):
            self.assertFalse(pse.is_enabled())

    def test_enabled_when_both_set(self):
        with mock.patch.dict(os.environ, {"PORTAL_INGEST_URL": "https://x", "PORTAL_INGEST_TOKEN": "t"}):
            self.assertTrue(pse.is_enabled())


class ValueTest(unittest.TestCase):
    def test_month_of(self):
        self.assertEqual(pse.month_of("202608"), "2026-08")
        with self.assertRaises(ValueError):
            pse.month_of("2026-08")

    def test_int(self):
        self.assertEqual(pse._int("¥113,653"), 113653)
        self.assertEqual(pse._int("10255"), 10255)
        self.assertIsNone(pse._int("-"))
        self.assertIsNone(pse._int(""))

    def test_rate(self):
        self.assertEqual(pse._rate("4.0%"), 0.04)
        self.assertEqual(pse._rate("0.04"), 0.04)
        self.assertEqual(pse._rate("166.7%"), 1.667)  # 求人ボックス側の数字をそのまま
        self.assertIsNone(pse._rate("-"))


class PayloadTest(unittest.TestCase):
    def test_build_payload(self):
        items = [{
            "term": "202608", "account_id": "1234-5678", "account_name": "テスト株式会社",
            "raw": {"ID": "1234-5678", "求人数": "9,543", "公開中": "9392", "表示回数": "237,944",
                    "クリック数": "9543", "CTR": "4.0%", "応募数": "118", "CVR": "1.2%",
                    "平均CPC": "29", "費用": "¥276,212", "広告費": "¥276,212"},
        }]
        payload = pse.build_payload(items)
        self.assertEqual(payload["channel"], "kyujinbox")
        self.assertEqual(payload["route"], "rpa_scheduled")
        row = payload["rows"][0]
        self.assertEqual(row["month"], "2026-08")
        self.assertEqual(row["external_id"], "1234-5678")
        self.assertEqual(row["cost"], 276212)
        self.assertEqual(row["applications"], 118)
        self.assertEqual(row["ctr"], 0.04)
        self.assertNotIn("広告費", row)  # 費用と同じ値なので送らない

    def test_skips_empty_id(self):
        self.assertEqual(pse.build_payload([{"term": "202608", "account_id": "", "raw": {}}])["rows"], [])


class SendTest(unittest.TestCase):
    def test_noop_when_disabled(self):
        with mock.patch.dict(os.environ, {"PORTAL_INGEST_URL": "", "PORTAL_INGEST_TOKEN": ""}):
            with mock.patch.object(pse.requests, "post") as post:
                pse.send({"channel": "kyujinbox", "route": "rpa_scheduled", "rows": [{"month": "2026-08"}]})
                post.assert_not_called()

    def test_chunks_of_200_and_never_raises(self):
        rows = [{"month": "2026-08", "external_id": f"{i:04d}-0000"} for i in range(450)]
        with mock.patch.dict(os.environ, {"PORTAL_INGEST_URL": "https://x", "PORTAL_INGEST_TOKEN": "t"}):
            with mock.patch.object(pse.requests, "post") as post:
                post.return_value = mock.Mock(status_code=200, json=lambda: {"received": 1, "upserted": 1})
                pse.send({"channel": "kyujinbox", "route": "rpa_scheduled", "rows": rows})
                self.assertEqual(post.call_count, 3)

    def test_notifies_on_http_error_without_raising(self):
        notifier = mock.Mock()
        with mock.patch.dict(os.environ, {"PORTAL_INGEST_URL": "https://x", "PORTAL_INGEST_TOKEN": "t"}):
            with mock.patch.object(pse.requests, "post") as post:
                post.return_value = mock.Mock(status_code=500, text="boom")
                pse.send({"channel": "kyujinbox", "route": "rpa_scheduled",
                          "rows": [{"month": "2026-08", "external_id": "1234-5678"}]}, notifier)
        notifier.check.assert_called_once()


if __name__ == "__main__":
    unittest.main()
