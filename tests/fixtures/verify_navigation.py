"""Browser history regression across native Streamlit pages."""

from playwright.sync_api import expect, sync_playwright

expect.set_options(timeout=20000)

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:8518")
    page.get_by_role("button", name="热搜词排行榜", exact=True).click()
    page.get_by_role("button", name="去提交", exact=True).click()
    editor = page.locator(".cm-content")
    expect(editor).to_be_visible()
    editor.fill("print('latest')")
    page.get_by_role("button", name="提交评测", exact=True).click()
    expect(page.locator("h1")).to_contain_text("评测详情 #4", timeout=20000)
    print("DETAIL", page.url, flush=True)
    page.go_back()
    page.wait_for_timeout(1500)
    print("BACK", page.url, page.locator("h1").all_text_contents(), flush=True)
    assert "submission=" not in page.url
    expect(editor).to_contain_text("print('latest')", timeout=15000)
    page.go_forward()
    expect(page.locator("h1")).to_contain_text("评测详情 #4", timeout=15000)
    page.reload()
    expect(page.locator("h1")).to_contain_text("评测详情 #4", timeout=15000)
    assert not errors, errors
    browser.close()
    print("Native cross-page navigation passed.")
