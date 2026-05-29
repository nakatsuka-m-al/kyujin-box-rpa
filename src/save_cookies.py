"""
セッション保存スクリプト（ローカルで実行する）

使い方:
    python3 src/save_cookies.py

ブラウザが開くので手動でログイン（CAPTCHA含む）し、
ダッシュボードが表示されたらターミナルで Enter を押す。
出力されたJSON文字列を GitHub Secret「KYUJIN_COOKIES」に登録する。
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
        print("ログイン後、ダッシュボード画面が表示されてから")
        print("ここで Enter を押してください")
        print("=" * 60)
        input()

        # cookies + localStorage の両方を保存
        state = context.storage_state()

        # デバッグ用：保存されたクッキー名を表示
        cookie_names = [c["name"] for c in state.get("cookies", [])]
        print(f"\n保存したクッキー ({len(cookie_names)} 件): {cookie_names}")

        origins = state.get("origins", [])
        for o in origins:
            ls = o.get("localStorage", [])
            if ls:
                print(f"localStorage ({o['origin']}): {[x['name'] for x in ls]}")

        print()
        print("=" * 60)
        print("以下を GitHub Secret「KYUJIN_COOKIES」に登録してください:")
        print("（既存のSecretを上書き更新）")
        print("=" * 60)
        print(json.dumps(state, ensure_ascii=False))
        print("=" * 60)

        browser.close()


if __name__ == "__main__":
    main()
