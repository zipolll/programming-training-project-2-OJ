"""Offline production-renderer checks for the unified editor and conversation."""

from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import expect, sync_playwright

OUTPUT = Path('.pytest_cache/agent-editor-screenshots')
OUTPUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge')
    page = browser.new_page(viewport={"width": 1440, "height": 1100})

    def visit(scenario):
        page.goto('http://127.0.0.1:8529/?' + urlencode({'fixture_page': scenario}))
        expect(page.locator('.st-key-oj_agent_workspace')).to_be_visible(timeout=30000)
        expect(page.locator('[data-testid="stException"]')).to_have_count(0)

    for size in ('desktop', 'mobile'):
        if size == 'mobile':
            page.set_viewport_size({'width': 390, 'height': 844})
        visit('AI 结果')
        workspace = page.locator('.st-key-oj_agent_workspace')
        ai = page.locator('.st-key-oj_agent_ai_bottom')
        document = page.locator('.st-key-oj_agent_document')
        expect(ai.get_by_role('textbox', name='修改意见', exact=True)).to_be_visible()
        expect(page.get_by_role('button', name='AI 修改', exact=True)).to_have_count(0)
        expect(page.get_by_role('button', name='手动编辑', exact=True)).to_have_count(0)
        ai_box = ai.bounding_box()
        doc_box = document.bounding_box()
        assert ai_box['y'] >= doc_box['y'] + doc_box['height']
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        page.screenshot(path=str(OUTPUT / f'display-{size}.png'), full_page=True)
        ai.screenshot(path=str(OUTPUT / f'conversation-{size}.png'))
        workspace.get_by_role('button', name='修改', exact=True).click()
        expect(page.get_by_role('textbox', name='题面', exact=True)).to_be_visible()
        actions = page.locator('.st-key-oj_agent_editor_actions')
        expect(actions.get_by_role('button')).to_have_count(3)
        boxes = [actions.get_by_role('button', name=name, exact=True).bounding_box()
                 for name in ('验证', '保存', '另存为新版本')]
        assert max(b['height'] for b in boxes) - min(b['height'] for b in boxes) < 2
        assert max(b['y'] for b in boxes) - min(b['y'] for b in boxes) < 2
        actions.screenshot(path=str(OUTPUT / f'actions-{size}.png'))
        page.get_by_role('textbox', name='题面', exact=True).fill('未保存的手工修改')
        page.get_by_role('textbox', name='题面', exact=True).press('Tab')
        page.get_by_role('tab', name='分类与限制', exact=True).click()
        page.get_by_role('tab', name='题面与样例', exact=True).click()
        editor_field = page.get_by_role('textbox', name='题面', exact=True)
        expect(editor_field).to_have_value('未保存的手工修改')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        page.screenshot(path=str(OUTPUT / f'editor-{size}.png'), full_page=True)
        page.locator('.st-key-agent_back_history button').click()
        expect(page.get_by_role('dialog')).to_be_visible()
        page.get_by_role('button', name='留在当前页面', exact=True).click()
        expect(page.get_by_role('textbox', name='题面', exact=True)).to_have_value(
            '未保存的手工修改'
        )
        page.once('dialog', lambda dialog: dialog.accept())
        visit('AI 已停止')
        expect(page.get_by_role('button', name='修改', exact=True)).to_have_count(0)
        expect(page.get_by_role('textbox', name='修改意见', exact=True)).to_have_count(0)
        expect(page.locator('.st-key-oj_agent_ai_panel')).to_have_count(0)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        page.screenshot(path=str(OUTPUT / f'stopped-{size}.png'), full_page=True)
    browser.close()

print(f'Desktop/mobile checks passed: {OUTPUT.resolve()}')
