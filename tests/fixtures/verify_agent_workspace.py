"""Visual checks of the production UI using only deterministic offline preview data."""

from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import expect, sync_playwright

OUTPUT = Path(__file__).resolve().parents[2] / '.pytest_cache' / 'agent-ui'
OUTPUT.mkdir(parents=True, exist_ok=True)
expect.set_options(timeout=20000)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel='chrome', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1050})

    def visit(name, heading):
        page.goto('http://127.0.0.1:8527/?' + urlencode({'fixture_page': name}))
        expect(page.get_by_text(heading, exact=True).first).to_be_visible()
        expect(page.locator('[data-testid="stException"]')).to_have_count(0)
        expect(page.locator('[data-testid="stStatusWidget"]')).not_to_be_visible()

    visit('AI 命题', '从一个想法开始')
    page.screenshot(path=str(OUTPUT / 'create-desktop.png'), full_page=True)
    page.get_by_role('button', name='算法入门', exact=True).click()
    expect(page.get_by_role('textbox', name='描述你想出的题目')).to_have_value(
        '出一道适合初学者的二分查找题，背景是寻找宝藏。'
    )
    visit('AI 记录', '热搜词排行榜')
    page.screenshot(path=str(OUTPUT / 'history-desktop.png'), full_page=True)
    visit('AI 结果', '继续修改')
    page.screenshot(path=str(OUTPUT / 'detail-desktop.png'), full_page=True)
    page.get_by_text('编辑', exact=True).click()
    expect(page.get_by_role('textbox', name='题面', exact=True)).to_be_visible()
    page.screenshot(path=str(OUTPUT / 'editor-desktop.png'))
    visit('AI 异常', '模型服务暂时不可用，请稍后重试。')
    expect(page.get_by_role('button', name='重试', exact=True)).to_be_visible()
    page.screenshot(path=str(OUTPUT / 'failure-desktop.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    visit('AI 结果', '继续修改')
    page.get_by_text('题目', exact=True).click()
    expect(page.get_by_text('参考解法与程序', exact=True)).to_be_visible()
    expect(page.get_by_role('textbox', name='继续修改', exact=True)).to_have_count(0)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    page.screenshot(path=str(OUTPUT / 'detail-mobile.png'), full_page=True)
    visit('AI 命题', '从一个想法开始')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    page.screenshot(path=str(OUTPUT / 'create-mobile.png'), full_page=True)
    visit('AI 记录', '热搜词排行榜')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    page.screenshot(path=str(OUTPUT / 'history-mobile.png'), full_page=True)
    browser.close()

print(f'Desktop/mobile preview checks passed; screenshots: {OUTPUT}')
