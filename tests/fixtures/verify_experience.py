"""Isolated browser regression for editor, CE details and URL history."""

from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import expect, sync_playwright

expect.set_options(timeout=20000)

OUT = Path(__file__).resolve().parents[2] / ".pytest_cache" / "experience-ui"
OUT.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:8517/?"


with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE + urlencode({"fixture_page": "题目内提交"}))
    editor = page.locator(".cm-content")
    expect(editor).to_be_visible(timeout=20000)
    code = "# draft\n" + "print('hello')\n" * 70
    editor.fill(code)
    assert editor.bounding_box()["height"] > 1000
    page.reload()
    expect(editor).to_contain_text("# draft", timeout=20000)
    expect(editor).to_contain_text("print('hello')")
    assert page.locator(".cm-line span").count() > 0
    page.screenshot(path=str(OUT / "editor-desktop.png"))
    page.get_by_role("button", name="提交评测", exact=True).click()
    expect(page.locator("h1")).to_contain_text("评测详情 #4", timeout=20000)
    expect(page.get_by_text("提交语言 · C++", exact=True)).to_be_visible()
    page.get_by_text("查看提交代码", exact=True).click()
    expect(page.locator('[data-testid="stCode"]').filter(has_text="#include")).to_be_visible()
    assert not page.get_by_role("button", name="刷新一次").count()
    page.screenshot(path=str(OUT / "detail-desktop.png"))
    page.goto(BASE + urlencode({"fixture_page": "题目内提交"}))
    expect(editor).to_contain_text("# draft", timeout=20000)
    page.goto(BASE + urlencode({"fixture_page": "提交记录", "submission": 4}))
    expect(page.locator("h1")).to_contain_text("评测详情 #4", timeout=20000)
    page.reload()
    expect(page.locator("h1")).to_contain_text("评测详情 #4", timeout=20000)
    for width in (1440, 390):
        page.set_viewport_size({"width": width, "height": 1000})
        for name in ("测试点", "访问审计", "我的题库", "题库", "代码提交"):
            page.goto(BASE + urlencode({"fixture_page": name}))
            expect(page.get_by_text("预览页面", exact=True)).to_be_visible()
            page.wait_for_timeout(700)
            assert not page.locator('[data-testid="stException"]').count()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            page.screenshot(path=str(OUT / f"{name}-{width}.png"), full_page=True)
    assert not errors, errors
    browser.close()
    print("Editor, highlight, refresh, submission, source expansion, history and layouts passed.")
