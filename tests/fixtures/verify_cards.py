"""Optional real-browser QA against card_pages.py; writes only test artifacts.

Start the fixture on port 8517, then run this file with Playwright installed.
Uses the locally installed Chrome, without accessing a real account or API.
"""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUTPUT = Path(__file__).resolve().parents[2] / ".pytest_cache" / "card-ui"
OUTPUT.mkdir(parents=True, exist_ok=True)
PAGES = [
    "题库",
    "提交记录",
    "测试点",
    "用户管理",
    "访问审计",
    "普通命题",
    "编辑题目",
    "模型配置",
    "AI 命题",
    "语言注册",
    "代码提交",
    "题目内提交",
]

with sync_playwright() as pw:
    print("Launching Chrome", flush=True)
    browser = pw.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    page.goto("http://127.0.0.1:8517")
    page.locator('[class*="st-key-oj_record_problem_hotword-ranking"]').wait_for()
    page.wait_for_timeout(500)
    if "--inspect" in sys.argv:
        print(page.evaluate("""() => {
            const row = document.querySelector('div[class*="st-key-oj_record_"]');
            return [row, ...row.querySelectorAll('div, p, button')].map(e => {
              const s = getComputedStyle(e), r = e.getBoundingClientRect();
              return {tag:e.tagName, cls:e.className, test:e.dataset.testid,
                display:s.display, height:s.height, box:s.boxSizing, flex:s.flex,
                position:s.position, padding:s.padding, margin:s.margin,
                rect:{x:r.x,y:r.y,w:r.width,h:r.height},
                text:e.textContent.slice(0,70)};
            });
        }"""), flush=True)
        browser.close()
        raise SystemExit(0)
    results = []
    for index, name in enumerate([] if "--interactions" in sys.argv else PAGES):
        page.locator('[data-testid="stSelectbox"]').first.get_by_role("combobox").click()
        page.get_by_role("option", name=name, exact=True).click()
        # Wait for the rerun's new layout and fonts to settle before measuring.
        page.wait_for_timeout(900)
        assert page.locator('[data-testid="stException"]').count() == 0, name
        for width in (1440, 390):
            page.set_viewport_size({"width": width, "height": 1000})
            page.wait_for_timeout(250)
            metrics = page.evaluate("""() => {
                const rows = [...document.querySelectorAll('div[class*="st-key-oj_record_"]')];
                const records = rows.map(row => {
                    const r = row.getBoundingClientRect();
                    const badge = row.querySelector('.oj-badge');
                    const b = badge?.getBoundingClientRect();
                    const cells = [...row.querySelectorAll('.oj-cell-text, .oj-badge, button p')]
                      .map(x => x.getBoundingClientRect()).filter(r => r.height > 0)
                      .map(r => r.y + r.height / 2);
                    const horizontal = row.querySelector('[data-testid="stHorizontalBlock"]');
                    const cols = [...horizontal.children]
                      .filter(e => e.dataset.testid === 'stColumn')
                      .map(e => e.getBoundingClientRect());
                    return {height: r.height, gapTop: b ? b.top-r.top : null,
                      gapBottom: b ? r.bottom-b.bottom : null,
                      columnWidths: cols.map(c => c.width),
                      columnLefts: cols.map(c => c.left),
                      centerSpread: cells.length ? Math.max(...cells)-Math.min(...cells) : 0};
                });
                const labels = [...document.querySelectorAll('.oj-field-label')];
                const headers = document.querySelectorAll('div[class*="st-key-oj_table_header_"]');
                return {records,
                  horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
                  mobileLabelsVisible: labels.filter(x =>
                    x.getBoundingClientRect().height > 0).length,
                  headersVisible: [...headers]
                    .filter(x => x.getBoundingClientRect().height > 0).length};
            }""")
            results.append({"page": name, "width": width, **metrics})
            assert not metrics["horizontalOverflow"], (name, width, metrics)
            for record in metrics["records"]:
                if width == 1440:
                    if record["gapTop"] is not None:
                        # The bottom edge includes the one-pixel row divider.
                        assert abs(record["gapTop"] - record["gapBottom"]) < 1.1, record
                        assert record["gapTop"] >= 8, record
                    if name != "访问审计":
                        assert record["centerSpread"] < .5, record
                        assert record["height"] < 52, record
                else:
                    assert metrics["headersVisible"] == 0
                    assert metrics["mobileLabelsVisible"] > 0
                    assert max(record["columnLefts"]) - min(record["columnLefts"]) < 1
                    assert min(record["columnWidths"]) > 290
            print(f"Measured {name} at {width}px", flush=True)
            page.screenshot(path=str(OUTPUT / f"{index:02}_{width}.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})
    # Audit details must be focusable, independently expandable, and readable on a phone.
    page.locator('[data-testid="stSelectbox"]').first.get_by_role("combobox").click()
    page.get_by_role("option", name="访问审计", exact=True).click()
    detail = page.locator('[data-testid="stExpander"] summary').first
    detail.wait_for()
    assert detail.get_attribute("aria-expanded") in (None, "false")
    detail.click()
    page.locator('[data-testid="stJson"]').first.wait_for()
    page.set_viewport_size({"width": 390, "height": 1000})
    page.screenshot(path=str(OUTPUT / "audit-expanded-mobile.png"))
    # A real keyboard activation must still invoke the submission callback.
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.locator('[data-testid="stSelectbox"]').first.get_by_role("combobox").click()
    page.get_by_role("option", name="提交记录", exact=True).click()
    link = page.get_by_role("button", name="2", exact=True)
    link.wait_for()
    link.hover()
    assert link.evaluate("e => getComputedStyle(e).color") == "rgb(29, 78, 216)"
    link.focus()
    page.keyboard.press("Enter")
    page.get_by_role("heading", name="评测详情 #2").wait_for()
    page.get_by_role("button", name="← 返回提交记录", exact=True).click()
    page.get_by_role("button", name="2", exact=True).wait_for()
    if results:
        (OUTPUT / "metrics.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print("Layout and interaction checks passed", flush=True)
    browser.close()
