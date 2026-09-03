import sys, re
sys.path.insert(0, "scripts")
from playwright.sync_api import sync_playwright
from jinzai_common import UA_POOL
url = sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(user_agent=UA_POOL[0], locale="ja-JP")
    pg = ctx.new_page()
    r = pg.goto(url, timeout=30000)
    pg.wait_for_timeout(2000)
    print("STATUS", r.status if r else None, pg.title())
    t = pg.inner_text("body")
    print(len(t))
    print(t[:6000])
    b.close()
