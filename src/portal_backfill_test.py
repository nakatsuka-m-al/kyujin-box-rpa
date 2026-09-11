"""portal_backfill の単体テスト。ネットワーク・シートには出ない。
実行: cd src && python3 portal_backfill_test.py
"""
import unittest

import portal_backfill as b


class RowsToDictsTest(unittest.TestCase):
    def test_pads_short_rows_and_skips_blank_headers(self):
        header = ["応募No", "", "氏名"]
        rows = [["A2-1"], ["A2-2", "x", "山田"]]
        d = b.rows_to_dicts(header, rows)
        self.assertEqual(d[0], {"応募No": "A2-1", "氏名": ""})
        self.assertEqual(d[1], {"応募No": "A2-2", "氏名": "山田"})


class KyujinboxItemsTest(unittest.TestCase):
    def test_maps_sheet_headers_to_fields_and_keeps_row_numbers(self):
        header = ["応募No", "応募日時", "氏名", "拠点名", "アカウントID"]
        rows = [["A2-1", "2026-09-11 10:00", "山田", "テスト株式会社", "1234-5678"],
                ["", "", "", "", ""],
                ["A2-3", "2026-09-12 11:00", "佐藤", "テスト株式会社", "1234-5678"]]
        items = b.kyujinbox_items(b.rows_to_dicts(header, rows), from_row=2)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["external_id"], "1234-5678")
        self.assertEqual(items[0]["external_key"], "A2-1")
        self.assertEqual(items[0]["display_name"], "テスト株式会社")
        self.assertEqual(items[0]["fields"]["name"], "山田")
        self.assertEqual(items[0]["fields"]["subaccount_name"], "テスト株式会社")
        self.assertEqual(items[0]["applied_at"], "2026-09-11 10:00")
        self.assertEqual(items[0]["source_sheet_row"], 2)
        self.assertEqual(items[1]["source_sheet_row"], 4)  # 空行を飛ばしても行番号はシート通り
        self.assertEqual(items[0]["raw"]["応募No"], "A2-1")

    def test_unknown_account_when_column_empty(self):
        header = ["応募No", "氏名", "拠点名", "アカウントID"]
        items = b.kyujinbox_items(b.rows_to_dicts(header, [["A2-1", "x", "会社", ""]]), from_row=2)
        self.assertEqual(items[0]["external_id"], "unknown")


class AtsItemsTest(unittest.TestCase):
    def test_uses_normalized_key_and_row_numbers(self):
        header = ["お仕事ID", "お名前", "応募受付日時", "拠点名・管理NO"]
        rows = [["1782146", "山田 太郎", "2026年4月11日21時22分", "株式会社FICKS158_オリジナル_大阪市北区"],
                ["", "", "", ""]]
        items = b.ats_items(b.rows_to_dicts(header, rows), from_row=2)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["external_key"], "1782146__山田太郎__202604112122")
        self.assertEqual(items[0]["source_sheet_row"], 2)


if __name__ == "__main__":
    unittest.main()
