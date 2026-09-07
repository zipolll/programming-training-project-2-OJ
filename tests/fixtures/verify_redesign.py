"""Visual QA using offline card_pages (8517) and navigation_pages (8518).

Run with --output PATH to choose the screenshot directory. No real API is used.
"""

import argparse
import json
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import expect, sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=Path(".pytest_cache/redesign"))
parser.add_argument("--rich", action="store_true")
parser.add_argument("--only", default="")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
expect.set_options(timeout=20000)
PAGES = [
    ("首页", "home"),
    ("登录", "login"),
    ("注册", "register"),
    ("题库", "catalogue"),
    ("我的题库", "banks"),
    ("提交记录", "submissions"),
    ("测试点", "cases"),
    ("题目内提交", "editor"),
    ("普通命题", "authoring"),
    ("编辑题目", "edit"),
    ("模型配置", "ai-config"),
    ("AI 命题", "ai-create"),
    ("语言注册", "languages"),
    ("用户管理", "users"),
    ("访问审计", "audit"),
    ("个人信息", "profile"),
    ("管理员信息", "admin-profile"),
]


def luminance(rgb):
    values = [int(x) / 255 for x in rgb.removeprefix("rgb(").removesuffix(")").split(",")]
    values = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in values]
    return sum(x * w for x, w in zip(values, (0.2126, 0.7152, 0.0722), strict=True))


def contrast(foreground, background):
    first, second = sorted((luminance(foreground), luminance(background)))
    return (second + 0.05) / (first + 0.05)


results = []
errors = []
with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.on("pageerror", lambda error: errors.append(str(error)))
    for name, slug in PAGES:
        if args.only and slug not in args.only.split(","):
            continue
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(
            "http://127.0.0.1:8517/?" + urlencode({"fixture_page": name, "rich": int(args.rich)})
        )
        expect(page.get_by_text("预览页面", exact=True)).to_be_visible()
        page.wait_for_timeout(800)
        expect(page.get_by_test_id("stApp")).to_have_attribute(
            "data-test-script-state", "notRunning", timeout=30000
        )
        expect(page.locator('[data-testid="stSkeleton"]')).to_have_count(0)
        if slug == "editor":
            expect(page.locator(".cm-content")).to_be_visible()
            expect(page.get_by_role("button", name="提交评测", exact=True)).to_be_visible()
        expect(page.locator('[data-testid="stException"]')).to_have_count(0)
        # A caught fixture error is still a broken preview, not a successful render.
        assert "Unexpected fixture request" not in page.locator("body").inner_text()
        for caption in page.get_by_test_id("stCaptionContainer").all():
            assert caption.evaluate("e => getComputedStyle(e).opacity") == "1"
            if caption.locator("p").count():
                assert (
                    contrast(
                        caption.locator("p").first.evaluate("e => getComputedStyle(e).color"),
                        "rgb(243, 246, 248)",
                    )
                    >= 4.5
                )
        if slug in {"login", "register"}:
            form = page.locator('[data-testid="stForm"]')
            expect(page.get_by_role("button", name=name, exact=True)).to_be_visible()
            assert form.bounding_box()["width"] <= 481, form.evaluate("""e =>
                [e, e.parentElement, e.parentElement.parentElement].map(x => ({
                    cls: x.className, width: x.getBoundingClientRect().width,
                    style: x.getAttribute('style')
                }))""")
            field = page.get_by_role("textbox", name="用户名")
            border = field.evaluate("e => getComputedStyle(e.parentElement).borderColor")
            assert contrast(border, "rgb(255, 255, 255)") >= 3
        for width in (1440, 1024, 390):
            page.set_viewport_size({"width": width, "height": 1000})
            page.wait_for_timeout(150)
            metrics = page.evaluate("""() => ({
                overflow: document.documentElement.scrollWidth > innerWidth + 1,
                headers: [...document.querySelectorAll('[class*="st-key-oj_table_header_"]')]
                    .filter(x => x.getBoundingClientRect().height > 0).length,
                labels: [...document.querySelectorAll('.oj-field-label')]
                    .filter(x => x.getBoundingClientRect().height > 0).length,
                badges: [...document.querySelectorAll('.oj-badge')].map(x => ({
                    fg: getComputedStyle(x).color, bg: getComputedStyle(x).backgroundColor
                }))
            })""")
            assert not metrics["overflow"], (name, width, metrics)
            if slug == "banks":
                columns = page.locator(".st-key-oj_bank_grid").evaluate(
                    "e => getComputedStyle(e).gridTemplateColumns.split(' ').length"
                )
                assert columns == {1440: 3, 1024: 2, 390: 1}[width], (width, columns)
                metrics["bank_columns"] = columns
            if slug in {"authoring", "edit"}:
                identifier = page.get_by_role("textbox", name="题目 ID", exact=True).bounding_box()
                title_box = page.get_by_role("textbox", name="标题", exact=True).bounding_box()
                if width >= 1024:
                    assert abs(identifier["y"] - title_box["y"]) < 2
                    assert abs(title_box["width"] - identifier["width"]) < 2
                    source_box = page.get_by_role("textbox", name="来源", exact=True).bounding_box()
                    author_box = page.get_by_role("textbox", name="作者", exact=True).bounding_box()
                    assert abs(source_box["x"] - identifier["x"]) < 2
                    assert abs(author_box["x"] - title_box["x"]) < 2
                    assert abs(source_box["width"] - identifier["width"]) < 2
                else:
                    assert title_box["y"] > identifier["y"] + identifier["height"]
            if slug in {"profile", "admin-profile"}:
                panels = [
                    page.locator(f".st-key-oj_panel_default_profile_{key}").bounding_box()
                    for key in ("identity", "stats")
                ]
                headings = [
                    page.locator(f".st-key-oj_panel_heading_profile_{key} h2").bounding_box()
                    for key in ("identity", "stats")
                ]
                if width == 1440:
                    assert abs(panels[0]["y"] - panels[1]["y"]) < 2, panels
                    assert abs(panels[0]["height"] - panels[1]["height"]) < 2, panels
                    assert abs(headings[0]["y"] - headings[1]["y"]) < 2, headings
                else:
                    assert panels[1]["y"] >= panels[0]["y"] + panels[0]["height"]
            if width == 390 and page.locator(".oj-field-label").count():
                assert metrics["headers"] == 0 and metrics["labels"] > 0
            for badge in metrics["badges"]:
                assert contrast(badge["fg"], badge["bg"]) >= 4.5, badge
            page.screenshot(path=str(args.output / f"{slug}-{width}.png"), full_page=True)
            results.append({"page": name, "width": width, **metrics})
        print(f"Verified {slug}: 1440 / 1024 / 390", flush=True)

    # Check focus, the reading surface and authentic multipage URL behavior.
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.goto("http://127.0.0.1:8518/?" + urlencode({"rich": int(args.rich)}))
    title = page.get_by_role("button", name="热搜词排行榜", exact=True)
    expect(title).to_be_visible()
    title.focus()
    assert title.evaluate("e => getComputedStyle(e).outlineStyle") != "none"
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="题目描述", exact=True)).to_be_visible()
    expect(page.get_by_text("查看提示", exact=True)).to_be_visible()
    expect(page.get_by_test_id("stApp")).to_have_attribute(
        "data-test-script-state", "notRunning", timeout=30000
    )
    for width in (1440, 1024, 390):
        page.set_viewport_size({"width": width, "height": 1000})
        page.wait_for_timeout(150)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        facts = page.locator(".st-key-oj_problem_facts").bounding_box()
        statement = page.locator(".st-key-problem_statement").bounding_box()
        assert abs(facts["x"] - statement["x"]) < 2
        assert abs(facts["width"] - statement["width"]) < 2
        assert abs(statement["y"] - facts["y"] - facts["height"] - 24) < 2
        summary = [
            item.bounding_box()
            for item in page.locator(".st-key-oj_problem_summary .oj-info-card").all()
        ]
        if facts["width"] < 700:
            assert abs(summary[0]["y"] - summary[1]["y"]) < 2
            assert summary[2]["y"] > summary[0]["y"]
            assert abs(summary[2]["y"] - summary[3]["y"]) < 2
        else:
            assert max(box["y"] for box in summary) - min(box["y"] for box in summary) < 2
        page.screenshot(path=str(args.output / f"problem-{width}.png"), full_page=True)
        popover = (
            page.get_by_test_id("stPopover")
            .filter(has_text="添加到题库")
            .get_by_role("button")
            .first
        )
        popover.click()
        confirm = page.get_by_role("button", name="确认添加", exact=True)
        expect(confirm).to_be_visible()
        button_box = confirm.bounding_box()
        assert (35 <= button_box["height"] <= 40) if width > 700 else button_box["height"] >= 44
        assert confirm.locator("p").evaluate("e => getComputedStyle(e).fontSize") == "14px"
        page.screenshot(path=str(args.output / f"add-to-bank-{width}.png"), full_page=True)
        if width == 1440:
            confirm.click()
            expect(
                page.get_by_text("已收录到题库；重复添加不会产生重复记录。", exact=True)
            ).to_be_visible()
        page.keyboard.press("Escape")
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.get_by_role("button", name="去提交", exact=True).click()
    editor = page.locator(".cm-content")
    expect(editor).to_be_visible()
    editor.fill("print('训练草稿')")
    page.reload()
    expect(editor).to_contain_text("训练草稿")
    page.get_by_role("button", name="提交评测", exact=True).click()
    expect(page.locator("h1")).to_contain_text("评测详情 #4")
    expect(page.get_by_test_id("stApp")).to_have_attribute(
        "data-test-script-state", "notRunning", timeout=30000
    )
    for width in (1440, 1024, 390):
        page.set_viewport_size({"width": width, "height": 1000})
        page.wait_for_timeout(150)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        if width == 390:
            metrics_boxes = [
                item.bounding_box()
                for item in page.locator('.st-key-oj_result_summary [data-testid="stMetric"]').all()
            ]
            assert metrics_boxes[0]["y"] < metrics_boxes[1]["y"]
            assert abs(metrics_boxes[1]["y"] - metrics_boxes[2]["y"]) < 2
        page.screenshot(path=str(args.output / f"result-{width}.png"), full_page=True)
    page.go_back()
    expect(editor).to_contain_text("训练草稿")
    page.go_forward()
    expect(page.locator("h1")).to_contain_text("评测详情 #4")
    page.reload()
    expect(page.locator("h1")).to_contain_text("评测详情 #4")

    # Long content and an empty personal bank collection use only fixture data.
    for width in (1440, 390):
        page.set_viewport_size({"width": width, "height": 1000})
        page.goto(
            "http://127.0.0.1:8518/?rich=1&problem=long_problem_identifier_for_responsive_layout_2026"
        )
        expect(page.get_by_role("heading", name="题目描述", exact=True)).to_be_visible()
        expect(page.get_by_test_id("stApp")).to_have_attribute(
            "data-test-script-state", "notRunning"
        )
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(args.output / f"problem-long-{width}.png"), full_page=True)
        page.get_by_test_id("stPopover").filter(has_text="添加到题库").get_by_role(
            "button"
        ).first.click()
        page.get_by_role("combobox", name="选择题库", exact=True).click()
        page.get_by_role("option", name="图论与动态规划专题复习题库", exact=True).click()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(args.output / f"add-to-bank-long-{width}.png"), full_page=True)
        page.goto("http://127.0.0.1:8518/?fixture_banks=empty&problem=hotword-ranking")
        page.get_by_test_id("stPopover").filter(has_text="添加到题库").get_by_role(
            "button"
        ).first.click()
        expect(page.get_by_text("还没有题库，先创建一个吧。", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="确认添加", exact=True)).to_have_count(0)
        page.get_by_role("button", name="创建题库", exact=True).click()
        expect(page.locator("h1")).to_have_text("创建题库")

    # Relocated actions must retain their permissions and explicit confirmation.
    page.set_viewport_size({"width": 1440, "height": 1000})
    for role in ("admin", "user"):
        page.goto("http://127.0.0.1:8518/?" + urlencode({"fixture_role": role}))
        page.get_by_role("button", name="热搜词排行榜", exact=True).click()
        page.get_by_test_id("stPopover").filter(has_text="更多").get_by_role("button").first.click()
        expect(page.get_by_role("button", name="编辑题目", exact=True)).to_be_visible()
        delete = page.get_by_role("button", name="删除题目", exact=True)
        if role == "admin":
            delete.click()
            confirmation = page.get_by_role("button", name="确认删除", exact=True)
            expect(confirmation).to_be_disabled()
            page.get_by_text("我确认永久删除该题目。", exact=True).click()
            expect(page.get_by_role("checkbox", name="我确认永久删除该题目。")).to_be_checked()
            expect(confirmation).to_be_enabled()
        else:
            expect(delete).to_have_count(0)
            page.get_by_role("button", name="编辑题目", exact=True).click()
            expect(page.get_by_role("textbox", name="标题", exact=True)).to_have_value(
                "热搜词排行榜"
            )

    page.goto("http://127.0.0.1:8518/problem-banks?rich=1")
    page.get_by_role("button", name="图论与动态规划专题复习题库", exact=True).click()
    expect(page.locator(".oj-hero")).to_contain_text("进入题库后可以阅读全部内容。")
    page.get_by_test_id("stPopover").filter(has_text="更多").get_by_role("button").first.click()
    page.get_by_role("button", name="删除题库", exact=True).click()
    expect(page.get_by_role("button", name="确认删除", exact=True)).to_be_disabled()
    page.get_by_text("确认删除此题库", exact=True).click()
    expect(page.get_by_role("checkbox", name="确认删除此题库", exact=True)).to_be_checked()
    expect(page.get_by_role("button", name="确认删除", exact=True)).to_be_enabled()
    page.emulate_media(reduced_motion="reduce")
    duration = page.get_by_role("button", name="确认删除", exact=True).evaluate(
        "e => getComputedStyle(e).transitionDuration"
    )
    assert all(float(x.removesuffix("s")) <= 0.001 for x in duration.split(", "))
    assert not errors, errors
    (args.output / "metrics.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    browser.close()
print("All layouts, badge contrasts, keyboard focus and submission history passed.")
