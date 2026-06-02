# トラブルシューティングガイド

## このツールの概要
求人ボックスの応募者データを6時間ごとに自動取得してGoogleスプレッドシートに書き込むツール。
GitHub Actionsで動作。ログインはplaywright-stealthでCAPTCHA回避。

## よくあるエラーと対処法

### ① ログイン失敗
```
RuntimeError: ログインに失敗しました。CAPTCHAが表示されているか...
```
**原因:** 求人ボックス側がbot検知を強化した  
**対処:** `src/scraper.py` の `login()` 関数を確認。stealth設定の強化が必要。Claudeに相談。

---

### ② 「直接投稿」リンクが見つからない
```
Locator.click: Timeout 30000ms exceeded.
waiting for get_by_role("link", name="直接投稿")
```
**原因:** 求人ボックスのUI変更  
**対処:** `playwright codegen https://secure.kyujinbox.com/login` で再調査してClaudeに共有。

---

### ③ CSVダウンロードが見つからない
```
Locator.click: Timeout 30000ms exceeded.
waiting for get_by_role("link", name=" 応募者情報をダウンロード")
```
**原因:** 応募者0件 → 正常スキップ（エラーメールは来ない）  
もしくは: UIが変更された  
**対処:** スプレッドシートに当該会社のデータが元々ないなら正常。あるなら②と同様。

---

### ④ スプレッドシートへの書き込みエラー
```
HttpError 400: Unable to parse range: OBS!A1:Z1
```
**原因:** スプレッドシートのタブ名が変わった  
**対処:** GitHub Secrets の `GOOGLE_SHEET_TAB` を実際のタブ名に更新。

---

### ⑤ 新規応募者なし（データが入らない）
```
新規応募者なし。処理終了。
```
**原因A:** 本当に新着なし（正常）  
**原因B:** `KYUJIN_SUB_ACCOUNTS` が `[]` のまま  
**対処B:** GitHub Secrets の `KYUJIN_SUB_ACCOUNTS` を確認・更新。

---

## GitHub Secretsの一覧
| 名前 | 内容 |
|---|---|
| `KYUJIN_MASTER_EMAIL` | 求人ボックス ログインID |
| `KYUJIN_MASTER_PASSWORD` | 同パスワード |
| `KYUJIN_SUB_ACCOUNTS` | `[{"name": "会社名"}, ...]` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | GCPサービスアカウントJSON |
| `GOOGLE_SHEET_ID` | スプレッドシートのID |
| `GOOGLE_SHEET_TAB` | シートのタブ名（例: `OBS`） |

## サブアカウントの追加方法
`KYUJIN_SUB_ACCOUNTS` Secretを更新するだけ：
```json
[{"name": "株式会社A"}, {"name": "株式会社B"}]
```
会社名は管理画面のアカウント切替メニューの表示名と完全一致させること。
