# 求人ボックス 応募者データ自動連携

求人ボックスの応募者データを自動取得し、Google Sheets と RPM（ゼクウ製ATS）に連携するツール。

## セットアップ

### 1. ローカルデバッグ（セレクタ調査）

```bash
pip install playwright google-auth google-auth-httplib2 google-api-python-client requests
playwright install chromium

# ブラウザを表示してセレクタを記録
playwright codegen https://employer.kyujinbox.com/login
```

### 2. GitHub Secrets 登録

| Secret名 | 内容 |
|---|---|
| `KYUJIN_MASTER_EMAIL` | 求人ボックス マスターID |
| `KYUJIN_MASTER_PASSWORD` | 同パスワード |
| `KYUJIN_SUB_ACCOUNTS` | `[{"id":"xxx","name":"店舗A"},...]` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | GCPサービスアカウントJSON |
| `GOOGLE_SHEET_ID` | スプレッドシートID |
| `RPM_API_KEY` | RPM APIキー（取得後） |
| `RPM_API_ENDPOINT` | RPM APIエンドポイント（取得後） |
| `SLACK_WEBHOOK_URL` | エラー通知先（任意） |

### 3. 手動実行でテスト

GitHub Actions タブ → "求人ボックス 応募者同期" → "Run workflow"

## TODO

- [ ] `src/scraper.py` の `COLUMN_MAP` を実際のCSVヘッダに合わせて更新
- [ ] `src/scraper.py` の `switch_to_subaccount` のセレクタを確定
- [ ] `src/scraper.py` の `download_csv` のセレクタを確定
- [ ] `src/exporters.py` の `FIELD_MAP` を RPM API 仕様書に合わせて更新
- [ ] GitHub Secrets 登録
