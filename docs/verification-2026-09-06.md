# 全站视觉与评测体验验证记录

日期：2026-09-06。环境：Windows、Streamlit 1.63、Chrome 无头浏览器。

最终结果：Ruff 通过；完整测试 336 项全部通过；三个浏览器回归脚本通过。测试仅有现有第三方依赖弃用警告。

## 已验证

- 后端：真实 C++ 编译错误提交产生逐点 CE 并保存，得分为零；历史空 CE 日志使用保存总分推导，非 CE 空日志不伪造；提交详情包含原始代码和语言，列表不返回代码，访问权限保持本人／管理员限制。
- 页面：公共卡片表格、语义色状态、审计北京时间与摘要列移除；命题分区和动态样例／测试点；题库逐行移出、重复添加、题面原地收录。
- 编辑器：本地打包高亮，长代码自动增高，刷新恢复草稿，提交事件包含最新完整代码和对应语言，提交后打开独立评测详情，代码折叠区原地打开。
- 导航：题目 → 提交 → 评测 → 浏览器回退／前进／刷新；返回提交页保留代码，回退不再次提交；AI 阶段切换、刷新、回退和前进恢复对应视图。
- 视觉：1440px 和 390px 下检查页面溢出、列表重排、命题模式字号；系统深色设置下侧栏文字清晰、应用保持浅色。选中模式使用白字。

## 可重复执行

```text
python -m ruff check .
python -m pytest -q
```

浏览器回归使用独立模拟数据，不访问真实账号或写入业务数据库。分别在端口 8517、8518 启动以下预览后运行对应检查：

```text
python -m streamlit run tests/fixtures/card_pages.py --server.port 8517 --server.headless true
python -m streamlit run tests/fixtures/navigation_pages.py --server.port 8518 --server.headless true
python tests/fixtures/verify_experience.py
python tests/fixtures/verify_navigation.py
python tests/fixtures/verify_theme.py
```

浏览器脚本需要 Playwright 与本机 Chrome；页面截图保存在忽略提交的 `.pytest_cache/experience-ui`。

## 实现说明与未验证项

- Streamlit 1.63 在同页浏览器回退时可能发送旧查询参数。导航辅助层在 `popstate` 时重新加载浏览器实际地址，不新增历史记录；普通重绘和轮询不触发此行为。跨页跳转只执行一次原生导航。
- 本次未在 Linux／WSL 运行，未覆盖其资源限制和进程组终止路径。
- 当前 Streamlit 菜单没有旧版深浅切换选项；验证的是系统深色偏好和固定浅色配置，未操作不存在的旧版菜单。
- 未进行真实中文输入法的人工候选词交互、真实网络断开重连或生产账号全流程验收。中文代码内容和完整提交事件由自动测试覆盖。
- 草稿保存在当前标签页的 `sessionStorage`，不是跨设备保存；禁用浏览器存储时编辑和提交仍可用，但不能恢复草稿。普通命题和题库的未保存表单不纳入恢复。
- 早期完整测试曾因系统负载让一个极短时限评测用例误触发超时；该组单独重跑通过，未放宽业务评测时限。
