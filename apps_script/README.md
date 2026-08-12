# Apps Script 設置手順（ATS メールトリガー）

応募通知メールを検知して GitHub Actions を起動する。

## 1. GitHub トークンを発行する

GitHub は API でのトークン発行に対応していないため、Web UI で作成する。

1. https://github.com/settings/personal-access-tokens/new を開く
2. 以下を設定する

   | 項目 | 値 |
   |---|---|
   | Token name | `apps-script-ats-trigger` |
   | Expiration | 1年（期限が切れると停止するので要注意） |
   | Repository access | Only select repositories → `kyujin-box-rpa` |
   | Permissions → Repository permissions → **Contents** | **Read and write** |

   ※ `repository_dispatch` には Contents の書き込み権限が必要。
   ※ リポジトリを限定すること。他のリポジトリへの権限は不要。

3. 生成されたトークン（`github_pat_` で始まる文字列）を控える
   画面を離れると二度と表示されない

## 2. Apps Script を設置する

1. 通知メールを受信している Google アカウントでログインする
2. https://script.google.com/home → 「新しいプロジェクト」
3. プロジェクト名を「ATS応募通知トリガー」などにする
4. `ats_mail_trigger.gs` の中身をすべて貼り付ける
5. 先頭の `GITHUB_TOKEN` に、手順1のトークンを貼る
6. 保存する

## 3. 動作を確認する

**まず GitHub 側の疎通を確認する**

関数選択で `testDispatch` を選んで実行する。
初回は Google の認可画面が出るので許可する。

→ GitHub の Actions タブに「ATS 高速同期（メールトリガー）」が起動すれば成功。

**次にメールの判別を確認する**

関数選択で `testDetect` を選んで実行する。
実行ログに以下のように出れば成功（GitHub は呼ばれない）。

```
ats2  <-  【Oubo Pay】株式会社BLAZEの求人に新着応募がありました
```

「判別不可」と出る場合は、そのメールの本文に求人URLが含まれているか確認する。

## 4. 自動実行を設定する

1. 左メニューの時計アイコン（トリガー）→「トリガーを追加」
2. 以下を設定する

   | 項目 | 値 |
   |---|---|
   | 実行する関数 | `checkAtsMail` |
   | イベントのソース | 時間主導型 |
   | 時間ベースのトリガー | 分ベースのタイマー |
   | 間隔 | 1分おき |
   | エラー通知設定 | 毎日通知（推奨） |

## 5. 本番へ切り替える

検証が済んだら、スクリプト先頭の

```javascript
const TARGET = 'test';
```

を

```javascript
const TARGET = 'production';
```

に変更して保存する。書き込み先が本番タブに切り替わる。

---

## 運用上の注意

**トークンの有効期限**
期限が切れると通知が止まる。止まっても気付きにくいので、
期限日をカレンダーに登録しておくこと。

**メールが届かなかった場合**
定期実行の全件同期（1日3回）が保険として動き続けるため、
最終的には取り込まれる。この定期実行は止めないこと。

**「RPA要確認」ラベル**
アカウントを判別できなかったメールに付く。
このラベルが付いたメールがあれば、本文の形式が変わった可能性がある。

**処理済みラベルの付け方**
GitHub の起動に成功したメールにだけ付ける。
失敗したメールはラベルが付かないため、次の実行で自動的に再試行される。
