"""Inspect native theme settings and fixed-light application tokens."""

from pathlib import Path

from playwright.sync_api import expect, sync_playwright

expect.set_options(timeout=20000)

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto("http://127.0.0.1:8518")
    expect(page.get_by_role("button", name="热搜词排行榜", exact=True)).to_be_visible()
    out = Path(__file__).resolve().parents[2] / ".pytest_cache" / "experience-ui"
    out.mkdir(parents=True, exist_ok=True)
    def colors():
        return page.locator('[data-testid="stSidebar"] a p').evaluate_all(
            "els => els.map(e => getComputedStyle(e).color)"
        )
    light = colors()
    page.emulate_media(color_scheme="dark")
    page.reload()
    expect(page.get_by_role("button", name="热搜词排行榜", exact=True)).to_be_visible()
    assert colors() == light
    assert all(color != "rgb(255, 255, 255)" for color in colors())
    page.screenshot(path=str(out / "dark-system-desktop.png"))
    page.get_by_role("link", name="命题中心", exact=True).click()
    expect(page.get_by_text("普通命题", exact=True)).to_be_visible(timeout=15000)
    controls = page.locator('[class*="problem_authoring_mode"] [role="radiogroup"] button')
    assert controls.count() == 2
    assert controls.first.locator("p").evaluate("e => getComputedStyle(e).fontSize") == "20px"
    selected_color = controls.first.locator("p").evaluate("e => getComputedStyle(e).color")
    assert selected_color == "rgb(255, 255, 255)"
    page.screenshot(path=str(out / "authoring-desktop.png"))
    sidebar_close = page.locator('[data-testid="stSidebarCollapseButton"] button')
    if sidebar_close.is_visible():
        sidebar_close.click()
    page.set_viewport_size({"width": 390, "height": 900})
    page.wait_for_timeout(500)
    assert controls.first.locator("p").evaluate("e => getComputedStyle(e).fontSize") == "18px"
    page.screenshot(path=str(out / "authoring-mobile.png"))
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    controls.filter(has_text="AI 智能命题").click()
    stages = page.locator('[class*="agent_active_view"] [role="radio"]')
    stages.filter(has_text="创建任务").click()
    expect(page.get_by_text("命题方向", exact=True)).to_be_visible()
    stages.filter(has_text="进度与结果").click()
    expect(page.get_by_text("尚无命题任务，请先在“创建任务”中发起挑战。",
                            exact=False)).to_be_visible()
    expect(page.locator('[data-testid="stStatusWidget"]')).not_to_be_visible()
    page.reload()
    expect(stages.filter(has_text="进度与结果")).to_have_attribute(
        "aria-checked", "true"
    )
    expect(page.locator('[data-testid="stStatusWidget"]')).not_to_be_visible()
    page.go_back()
    expect(page.get_by_text("命题方向", exact=True)).to_be_visible()
    expect(stages.filter(has_text="创建任务")).to_have_attribute("aria-checked", "true")
    expect(page.locator('[data-testid="stStatusWidget"]')).not_to_be_visible()
    # popstate triggers a document reload; let its browser bridge finish mounting.
    page.wait_for_timeout(750)
    page.go_forward()
    expect(stages.filter(has_text="进度与结果")).to_have_attribute("aria-checked", "true")
    print("System-dark palette, sidebar legibility and authoring typography passed.")
    browser.close()
