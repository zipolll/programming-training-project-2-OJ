"""Offline production-renderer checks for the unified editor and conversation."""

import os
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import expect, sync_playwright

OUTPUT = Path(".pytest_cache/agent-editor-screenshots")
OUTPUT.mkdir(parents=True, exist_ok=True)
BASE_URL = os.getenv("OJ_FIXTURE_BASE_URL", "http://127.0.0.1:8529/")

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    page = browser.new_page(viewport={"width": 1440, "height": 1100})
    frontend_errors = []
    page.on(
        "console",
        lambda message: (
            frontend_errors.append(message.text) if message.type in ("error", "warning") else None
        ),
    )
    page.on("pageerror", lambda error: frontend_errors.append(str(error)))

    def visit(scenario):
        page.goto(BASE_URL + "?" + urlencode({"fixture_page": scenario}))
        expect(page.locator(".st-key-oj_agent_workspace")).to_be_visible(timeout=30000)
        expect(page.locator('[data-testid="stException"]')).to_have_count(0)

    for size in ("desktop", "mobile"):
        if size == "mobile":
            page.set_viewport_size({"width": 390, "height": 844})
        # Display page: problem and task information only, without the AI dialog.
        visit("AI 结果")
        workspace = page.locator(".st-key-oj_agent_workspace")
        info = page.locator(".st-key-oj_agent_task_information")
        expect(info).to_be_visible()
        expect(page.get_by_role("textbox", name="修改意见", exact=True)).to_have_count(0)
        expect(page.locator(".st-key-oj_agent_ai_bottom")).to_have_count(0)
        expect(page.get_by_role("button", name="AI 修改", exact=True)).to_have_count(0)
        expect(page.get_by_role("button", name="手动编辑", exact=True)).to_have_count(0)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(OUTPUT / f"display-{size}.png"), full_page=True)
        # Editor page: the conversation card sits below the workspace, actions under the input.
        workspace.get_by_role("button", name="修改", exact=True).click()
        statement_field = page.get_by_role("textbox", name="题面", exact=True)
        expect(statement_field).to_be_visible()
        # The statement field grows with its content instead of clipping it.
        assert statement_field.evaluate("(e) => e.scrollHeight <= e.clientHeight + 1")
        # It must also hug the content instead of leaving large empty space.
        long_statement = "\n".join(
            f"第{index}段：验证题面输入框随内容自动伸展。" for index in range(1, 13)
        )
        statement_field.fill(long_statement)
        statement_field.press("Tab")
        expect(statement_field).to_have_value(long_statement)
        page.wait_for_timeout(600)
        assert statement_field.evaluate("(e) => Math.abs(e.scrollHeight - e.clientHeight) <= 2")
        expect(info).to_have_count(0)
        ai = page.locator(".st-key-oj_agent_ai_bottom")
        expect(ai.get_by_role("textbox", name="修改意见", exact=True)).to_be_visible()
        ws_box = workspace.bounding_box()
        ai_box = ai.bounding_box()
        assert ai_box["y"] >= ws_box["y"] + ws_box["height"]
        actions = page.locator(".st-key-oj_agent_editor_actions")
        expect(actions.get_by_role("button")).to_have_count(3)
        boxes = [
            actions.get_by_role("button", name=name, exact=True).bounding_box()
            for name in ("验证", "保存", "另存为新版本")
        ]
        assert max(b["height"] for b in boxes) - min(b["height"] for b in boxes) < 2
        assert max(b["y"] for b in boxes) - min(b["y"] for b in boxes) < 2
        feedback = ai.get_by_role("textbox", name="修改意见", exact=True)
        assert boxes[0]["y"] > feedback.bounding_box()["y"]
        # The actions sit outside the conversation card, directly below it.
        expect(ai.locator(".st-key-oj_agent_editor_actions")).to_have_count(0)
        assert boxes[0]["y"] >= ai_box["y"] + ai_box["height"]
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        actions.screenshot(path=str(OUTPUT / f"actions-{size}.png"))
        ai.screenshot(path=str(OUTPUT / f"conversation-{size}.png"))
        # A running check shows one hint instead of stacking progress blocks.
        actions.get_by_role("button", name="验证", exact=True).click()
        expect(
            page.get_by_text("正在验证当前草稿，完成后结果会显示在这里。", exact=True)
        ).to_be_visible()
        expect(page.get_by_role("progressbar")).to_have_count(0)
        expect(
            page.get_by_text("参考程序已通过全部样例和测试点。验证未保存题目。", exact=True)
        ).to_be_visible(timeout=10000)
        page.wait_for_timeout(300)
        expect(page.locator(".st-key-oj_agent_ai_bottom")).to_have_count(1)
        expect(page.get_by_role("textbox", name="修改意见", exact=True)).to_have_count(1)
        expect(page.locator(".st-key-oj_agent_editor_actions")).to_have_count(1)
        # Draft survives tab switches and the unsaved-changes navigation guard.
        statement_field.fill("未保存的手工修改")
        statement_field.press("Tab")
        page.get_by_role("tab", name="分类与限制", exact=True).click()
        page.get_by_role("tab", name="题面与样例", exact=True).click()
        editor_field = page.get_by_role("textbox", name="题面", exact=True)
        expect(editor_field).to_have_value("未保存的手工修改")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(OUTPUT / f"editor-{size}.png"), full_page=True)
        page.locator(".st-key-agent_back_history button").click()
        expect(page.get_by_role("dialog")).to_be_visible()
        page.get_by_role("button", name="留在当前页面", exact=True).click()
        expect(page.get_by_role("textbox", name="题面", exact=True)).to_have_value(
            "未保存的手工修改"
        )
        page.once("dialog", lambda dialog: dialog.accept())
        # A stopped task without content keeps only the retry entries.
        visit("AI 已停止")
        expect(page.get_by_role("button", name="修改", exact=True)).to_have_count(0)
        expect(page.get_by_role("textbox", name="修改意见", exact=True)).to_have_count(0)
        expect(page.locator(".st-key-oj_agent_ai_bottom")).to_have_count(0)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(OUTPUT / f"stopped-{size}.png"), full_page=True)
    browser.close()

bad_messages = (
    "Encountered two children with the same key",
    "Cannot set a node at a delta path",
    "Could not find fragment with id",
)
assert not [
    message for message in frontend_errors if any(marker in message for marker in bad_messages)
], frontend_errors

print(f"Desktop/mobile checks passed: {OUTPUT.resolve()}")
