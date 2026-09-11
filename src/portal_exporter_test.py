"""portal_exporter の単体テスト。ネットワークには出ない。
実行: cd src && python3 portal_exporter_test.py
"""
import os
import unittest
from unittest import mock

import portal_exporter as pe


class EnabledTest(unittest.TestCase):
    def test_disabled_when_env_empty(self):
        with mock.patch.dict(os.environ, {"PORTAL_INGEST_URL": "", "PORTAL_INGEST_TOKEN": ""}):
            self.assertFalse(pe.is_enabled())

    def test_enabled_when_both_set(self):
        with mock.patch.dict(os.environ, {"PORTAL_INGEST_URL": "https://x", "PORTAL_INGEST_TOKEN": "t"}):
            self.assertTrue(pe.is_enabled())


class PayloadTest(unittest.TestCase):
    def test_kyujinbox_payload(self):
        applicants = [{
            "applicant_id": "A2-0001-0001", "applied_at": "2026-09-11 10:00",
            "name": "山田 太郎", "gender": "男性", "_subaccount_name": "テスト株式会社",
            "_raw": {"応募No": "A2-0001-0001", "氏名": "山田 太郎"},
        }]
        payload = pe.build_kyujinbox_payload(applicants, {"A2-0001-0001": "1234-5678"}, "rpa_scheduled")
        self.assertEqual(payload["media"], "kyujinbox")
        self.assertEqual(payload["route"], "rpa_scheduled")
        a = payload["applicants"][0]
        self.assertEqual(a["media"], "kyujinbox")
        self.assertEqual(a["external_id"], "1234-5678")
        self.assertEqual(a["display_name"], "テスト株式会社")
        self.assertEqual(a["external_key"], "A2-0001-0001")
        self.assertEqual(a["applied_at"], "2026-09-11 10:00")
        self.assertEqual(a["fields"]["name"], "山田 太郎")
        self.assertEqual(a["fields"]["subaccount_name"], "テスト株式会社")
        self.assertNotIn("_raw", a["fields"])
        self.assertNotIn("applicant_id", a["fields"])
        self.assertEqual(a["raw"]["応募No"], "A2-0001-0001")

    def test_kyujinbox_unknown_account(self):
        applicants = [{"applicant_id": "A2-0001-0002", "name": "x", "_raw": {}}]
        payload = pe.build_kyujinbox_payload(applicants, {}, "rpa_scheduled")
        self.assertEqual(payload["applicants"][0]["external_id"], "unknown")

    def test_kyujinbox_skips_empty_id(self):
        applicants = [{"applicant_id": "", "name": "x", "_raw": {}}]
        payload = pe.build_kyujinbox_payload(applicants, {}, "rpa_scheduled")
        self.assertEqual(payload["applicants"], [])

    def test_ats_payload(self):
        rows = [{
            "お仕事ID": "1782146", "お名前": "山田 太郎", "応募受付日時": "2026-04-11 21:22:00",
            "拠点名・管理NO": "株式会社FICKS158_オリジナル_大阪市北区", "メールアドレス": "a@example.com",
        }]
        payload = pe.build_ats_payload(rows, "rpa_scheduled")
        a = payload["applicants"][0]
        self.assertEqual(a["media"], "ats")
        self.assertEqual(a["external_id"], "株式会社FICKS158_オリジナル_大阪市北区")
        self.assertEqual(a["external_key"], "1782146__山田太郎__202604112122")
        self.assertEqual(a["fields"]["name"], "山田 太郎")
        self.assertEqual(a["fields"]["email"], "a@example.com")
        self.assertEqual(a["fields"]["job_id"], "1782146")
        self.assertEqual(a["raw"]["お仕事ID"], "1782146")


class FieldKeysTest(unittest.TestCase):
    def test_field_keys_match_portal_schema(self):
        # ポータル側 FieldsSchema は strict。許可された16キー以外を送ると一括で 400 になる
        allowed = {
            "name", "gender", "birthdate", "current_job", "phone", "email", "address", "education",
            "work_history", "message", "job_title", "job_id", "status", "selection_comment",
            "job_label", "subaccount_name",
        }
        self.assertEqual(set(pe._KB_FIELD_KEYS) | {"subaccount_name"}, allowed)
        self.assertTrue(set(pe._ATS_FIELD_MAP) <= allowed)

    def test_env_strips_whitespace(self):
        with mock.patch.dict(os.environ, {"PORTAL_INGEST_URL": "https://x/\n", "PORTAL_INGEST_TOKEN": " t "}):
            self.assertEqual(pe._env("PORTAL_INGEST_URL"), "https://x/")
            self.assertEqual(pe._env("PORTAL_INGEST_TOKEN"), "t")

    def test_http_error_excerpt_is_single_line(self):
        bad = mock.Mock(status_code=502, text="<html>\n  <body>\n bad gateway\n</body>")
        with mock.patch.dict(os.environ, {"PORTAL_INGEST_URL": "https://x", "PORTAL_INGEST_TOKEN": "t"}):
            with mock.patch("portal_exporter.requests.post", return_value=bad):
                with self.assertLogs("portal_exporter", level="ERROR") as cm:
                    pe.send({"media": "ats", "route": "rpa_scheduled", "applicants": [{"external_key": "x"}]})
        self.assertNotIn("\n", cm.output[0].split("HTTP 502: ", 1)[1])


class ChunkTest(unittest.TestCase):
    def test_chunks_of_200(self):
        items = [{"external_key": str(i)} for i in range(450)]
        chunks = list(pe.chunked(items, 200))
        self.assertEqual([len(c) for c in chunks], [200, 200, 50])


class SendTest(unittest.TestCase):
    def test_send_noop_when_disabled(self):
        with mock.patch.dict(os.environ, {"PORTAL_INGEST_URL": "", "PORTAL_INGEST_TOKEN": ""}):
            with mock.patch("portal_exporter.requests.post") as post:
                pe.send({"media": "kyujinbox", "route": "rpa_scheduled", "applicants": [{"external_key": "x"}]})
                post.assert_not_called()

    def test_send_posts_in_chunks_and_never_raises(self):
        payload = {"media": "kyujinbox", "route": "rpa_scheduled",
                   "applicants": [{"external_key": str(i)} for i in range(250)]}
        ok = mock.Mock(status_code=200)
        ok.json.return_value = {"received": 1, "inserted": 1, "skipped": 0, "unassigned": 0}
        with mock.patch.dict(os.environ, {"PORTAL_INGEST_URL": "https://x/", "PORTAL_INGEST_TOKEN": "t"}):
            with mock.patch("portal_exporter.requests.post", return_value=ok) as post:
                pe.send(payload)
                self.assertEqual(post.call_count, 2)
                url = post.call_args_list[0].kwargs.get("url") or post.call_args_list[0].args[0]
                self.assertEqual(url, "https://x/api/ingest")
                self.assertEqual(len(post.call_args_list[0].kwargs["json"]["applicants"]), 200)

    def test_send_notifies_on_http_error_without_raising(self):
        bad = mock.Mock(status_code=500, text="boom")
        notifier = mock.Mock()
        with mock.patch.dict(os.environ, {"PORTAL_INGEST_URL": "https://x", "PORTAL_INGEST_TOKEN": "t"}):
            with mock.patch("portal_exporter.requests.post", return_value=bad):
                pe.send({"media": "ats", "route": "rpa_scheduled", "applicants": [{"external_key": "x"}]}, notifier)
        notifier.check.assert_called_once()


if __name__ == "__main__":
    unittest.main()
