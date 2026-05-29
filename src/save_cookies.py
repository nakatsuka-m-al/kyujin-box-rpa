"""
クッキー保存スクリプト（ローカルで1回だけ実行する）

使い方:
    python3 src/save_cookies.py

ブラウザが開くので手動でログイン（CAPTCHA含む）し、
ログイン完了後にターミナルで Enter を押す。
クッキーのJSON文字列が出力されるので、GitHub Secret「KYUJIN_COOKIES」に登録する。
"""

import json
from playwright.sync_api import sync_playwright


def main() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        page.goto("https://secure.kyujinbox.com/login")

        print()
        print("=" * 60)
        print("ブラウザでログインしてください（CAPTCHA含む）")
        print("ログイン完了してトップページが表示されたら")
        print("ここで Enter を押してください")
        print("=" * 60)
        input()

        cookies = context.cookies()
        print()
        print("=" * 60)
        print("以下を GitHub Secret「KYUJIN_COOKIES」に登録してください:")
        print("=" * 60)
        print(json.dumps(cookies, ensure_ascii=False))
        print("=" * 60)

        browser.close()


if __name__ == "__main__":
    main()
