"""Visual checks of the production UI using only deterministic offline preview data."""

import sys
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import expect, sync_playwright

OUTPUT = Path(__file__).resolve().parents[2] / '.pytest_cache' / 'agent-ui'
OUTPUT.mkdir(parents=True, exist_ok=True)
expect.set_options(timeout=20000)
PREVIEW_URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8527/'

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel='chrome', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1050})

    def visit(name, heading):
        page.goto(PREVIEW_URL.rstrip('/') + '/?' + urlencode({'fixture_page': name}))
        expect(page.get_by_text(heading, exact=True).first).to_be_visible()
        expect(page.locator('[data-testid="stException"]')).to_have_count(0)
        expect(page.locator('[data-testid="stStatusWidget"]')).not_to_be_visible()
        if name in ('AI 结果', 'AI 异常', 'AI 进度', 'AI 已停止', 'AI 长标题'):
            expect(page.get_by_text('任务信息', exact=True)).to_be_visible()

    def snapshot(name):
        expect(page.locator('[data-testid="stStatusWidget"]')).not_to_be_visible()
        # Allow responsive component hydration and font layout to settle.
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUTPUT / name), full_page=True)

    def chat_alignment():
        chat = page.locator('.st-key-oj_agent_conversation')
        user = chat.locator('[data-testid="stChatMessage"]').filter(
            has=page.locator('[data-testid="stChatMessageAvatarUser"]')).first
        ai = chat.locator('[data-testid="stChatMessage"]').filter(
            has=page.locator('[data-testid="stChatMessageAvatarAssistant"]')).first
        user_avatar = user.locator('[data-testid="stChatMessageAvatarUser"]')
        ai_avatar = ai.locator('[data-testid="stChatMessageAvatarAssistant"]')
        user_content = user.locator('[data-testid="stChatMessageContent"]')
        ai_content = ai.locator('[data-testid="stChatMessageContent"]')
        assert user_avatar.bounding_box()['x'] > user_content.bounding_box()['x']
        assert ai_avatar.bounding_box()['x'] < ai_content.bounding_box()['x']
        assert (
            user_avatar.evaluate('(e)=>getComputedStyle(e).backgroundColor')
            != ai_avatar.evaluate('(e)=>getComputedStyle(e).backgroundColor')
        )

    visit('AI 命题', '从一个想法开始')
    page.screenshot(path=str(OUTPUT / 'create-desktop.png'), full_page=True)
    expect(page.get_by_role('button', name='算法入门', exact=True)).to_have_count(0)
    page.get_by_role('textbox', name='描述你想出的题目').fill('出一道二分查找题')
    visit('AI 记录', '热搜词排行榜')
    page.screenshot(path=str(OUTPUT / 'history-desktop.png'), full_page=True)
    expect(page.get_by_role('button', name='修改', exact=True)).to_have_count(0)
    expect(page.get_by_role('button', name='重试', exact=True)).to_have_count(0)
    visit('AI 结果', '热搜词排行榜')
    expect(page.get_by_role('textbox', name='继续修改', exact=True)).to_have_count(0)
    expect(page.get_by_role('progressbar')).to_have_count(0)
    snapshot('detail-desktop.png')
    overview = page.locator('.st-key-oj_agent_overview')
    workspace = page.locator('.st-key-oj_agent_workspace')
    expect(overview).to_have_count(1)
    expect(workspace).to_have_count(1)
    expect(workspace.get_by_role('button', name='手动编辑', exact=True)).to_be_visible()
    version = overview.locator('.react-aria-ComboBox > [role="group"]')
    more = overview.get_by_role('button', name='更多', exact=True)
    assert abs(version.bounding_box()['height'] - more.bounding_box()['height']) <= 2
    assert abs(version.bounding_box()['y'] - more.bounding_box()['y']) <= 2
    page.get_by_role('button', name='AI 修改', exact=True).click()
    expect(page.get_by_role('textbox', name='继续修改', exact=True)).to_be_visible()
    snapshot('ai-desktop.png')
    chat_alignment()
    page.get_by_role('button', name='手动编辑', exact=True).click()
    expect(page.get_by_role('textbox', name='题面', exact=True)).to_be_visible()
    page.get_by_role('textbox', name='题面', exact=True).fill('临时修改的题面')
    page.get_by_role('tab', name='分类与限制', exact=True).click()
    page.get_by_role('textbox', name='标题', exact=True).fill('临时标题')
    page.get_by_role('tab', name='题面与样例', exact=True).click()
    expect(page.get_by_role('textbox', name='题面', exact=True)).to_have_value('临时修改的题面')
    page.screenshot(path=str(OUTPUT / 'editor-desktop.png'))
    page.get_by_role('button', name='取消编辑', exact=True).click()
    page.get_by_role('button', name='导入题目', exact=True).click()
    expect(page.get_by_role('dialog')).to_be_visible()
    expect(page.get_by_role('button', name='确认导入', exact=True)).to_be_disabled()
    snapshot('import-desktop.png')
    visit('AI 异常', '模型服务暂时不可用，请稍后重试。')
    expect(page.get_by_role('button', name='重试', exact=True)).to_be_visible()
    page.screenshot(path=str(OUTPUT / 'failure-desktop.png'), full_page=True)
    expect(overview.get_by_role('button', name='打开之前的可用版本')).to_be_visible()
    visit('AI 已停止', 'AI 出题任务')
    expect(page.get_by_role('heading', name='题目描述', exact=True)).to_have_count(0)
    expect(workspace.get_by_role('button', name='手动编辑', exact=True)).to_have_count(0)
    expect(workspace.locator('.oj-empty-state')).to_have_count(0)
    request = overview.locator('.oj-agent-request-preview')
    assert request.evaluate('(e)=>e.clientHeight <= parseFloat(getComputedStyle(e).lineHeight)*3+1')
    expect(request.locator('script')).to_have_count(0)
    assert abs(version.bounding_box()['y'] - more.bounding_box()['y']) <= 2
    snapshot('stopped-desktop.png')
    overview.screenshot(path=str(OUTPUT / 'overview-stopped-desktop.png'))
    overview.get_by_text('展开完整需求', exact=True).click()
    expect(overview.get_by_text('请使用 NumPy 广播计算校正结果', exact=False).last).to_be_visible()
    page.get_by_role('button', name='修改要求后重试', exact=True).click()
    expect(page.get_by_role('button', name='按修改后的要求重试', exact=True)).to_be_visible()
    expect(page.locator('.st-key-oj_agent_ai_panel')).to_have_count(0)
    expect(page.locator('.st-key-oj_agent_document')).to_have_count(0)
    expect(page.get_by_role('textbox', name='继续修改', exact=True)).to_have_count(0)
    retry_panel = page.locator('.st-key-oj_agent_retry_panel')
    assert retry_panel.bounding_box()['width'] > workspace.bounding_box()['width'] * .85
    snapshot('retry-desktop.png')
    visit('AI 长标题', '展开完整需求')
    title = overview.locator('.oj-agent-title')
    assert title.evaluate('(e)=>e.clientHeight <= parseFloat(getComputedStyle(e).lineHeight)*2+1')
    expect(title.locator('b')).to_have_count(0)
    assert title.bounding_box()['x'] + title.bounding_box()['width'] <= version.bounding_box()['x']
    snapshot('long-title-desktop.png')
    page.get_by_role('button', name='AI 修改', exact=True).click()
    expect(page.get_by_text('展开完整消息', exact=True)).to_be_visible()
    chat_alignment()
    message = page.locator('.oj-agent-message-preview').first
    assert message.evaluate('(e)=>e.clientHeight <= parseFloat(getComputedStyle(e).lineHeight)*4+1')
    expect(message.locator('script')).to_have_count(0)
    snapshot('chat-long-desktop.png')
    page.get_by_text('展开完整消息', exact=True).click()
    conversation = page.locator('.st-key-oj_agent_conversation')
    expect(
        conversation.get_by_text('请使用 NumPy 广播计算校正结果', exact=False).last
    ).to_be_visible()
    page.set_viewport_size({'width': 390, 'height': 844})
    visit('AI 结果', '热搜词排行榜')
    expect(page.get_by_role('tab', name='参考解法', exact=True)).to_be_visible()
    expect(page.get_by_role('textbox', name='继续修改', exact=True)).to_have_count(0)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    snapshot('detail-mobile.png')
    page.locator('.st-key-oj_agent_document').screenshot(path=str(OUTPUT / 'document-mobile.png'))
    page.get_by_role('button', name='AI 修改', exact=True).click()
    expect(page.get_by_role('textbox', name='继续修改', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='返回题目')).to_be_visible()
    expect(page.get_by_role('tab', name='题面', exact=True)).to_have_count(0)
    snapshot('ai-mobile.png')
    chat_alignment()
    page.locator('.st-key-oj_agent_ai_panel').screenshot(path=str(OUTPUT / 'panel-mobile.png'))
    page.get_by_role('button', name='返回题目').click()
    expect(page.get_by_role('tab', name='题面', exact=True)).to_be_visible()
    visit('AI 已停止', 'AI 出题任务')
    assert abs(version.bounding_box()['height'] - more.bounding_box()['height']) <= 2
    assert abs(version.bounding_box()['y'] - more.bounding_box()['y']) <= 2
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    snapshot('stopped-mobile.png')
    overview.screenshot(path=str(OUTPUT / 'overview-stopped-mobile.png'))
    workspace.screenshot(path=str(OUTPUT / 'workspace-stopped-mobile.png'))
    page.get_by_role('button', name='修改要求后重试', exact=True).click()
    expect(page.locator('.st-key-oj_agent_retry_panel')).to_be_visible()
    expect(page.get_by_role('textbox', name='继续修改', exact=True)).to_have_count(0)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    snapshot('retry-mobile.png')
    visit('AI 命题', '从一个想法开始')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    page.screenshot(path=str(OUTPUT / 'create-mobile.png'), full_page=True)
    visit('AI 记录', '热搜词排行榜')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    page.screenshot(path=str(OUTPUT / 'history-mobile.png'), full_page=True)
    browser.close()

print(f'Desktop/mobile preview checks passed; screenshots: {OUTPUT}')
