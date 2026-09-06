# 课程 API 与 Linux 兼容性核查

## 本轮修复结果

以下历史核查针对 `2a7e2df`，本轮已依据用户补充的助教说明在工作区修复：

- 恢复 `public_cases` 配置与完整日志权限矩阵；私有日志对本人仅返回 score/counts，公开不扩大 Submission 详情权限。
- 删题后回退所有相关用户的 submit_count/resolve_count；保留历史提交，并避免同题号重新创建时恢复旧贡献。
- 两个查询接口统一要求 user_id、problem_id 至少提供一个；修正审计 action 为 view_logs。
- 时间/内存逐项使用题目显式配置、语言配置、系统 3 秒/128 MB 的优先级；持久化保留字段省略状态。
- 补上管理员重置接口、任务停止和重启、会话失效及重置期间的 HTTP 请求隔离。
- 修复组合错误优先级、并发限流及 404/405/500 JSON 响应。
- 修复 Advance 管理员查看/取消任务权限、终态取消 409、参考题目不存在 404。
- 内置 Python 改为当前环境运行时解析，迁移旧绝对路径配置；动态语言注册不安装编译器。
- README 更新接口语义与 Linux/WSL 环境步骤；前端区分“明细未公开”与“暂无日志”。

已在本机 Ubuntu WSL2 安装 Python 虚拟环境支持与 GCC/G++，独立验证环境位于 `/home/zfxwsl/.cache/oj-api-verification-20260906`。Linux 完整套件 351 项通过，之后增加的并发限流、删题竞争与动态 C 编译三项也通过，共覆盖 354 项。Windows 完整套件 354 项通过；Ruff 与补丁格式检查通过。语言注册页面也已使用 3 秒默认值。没有对开发实例调用 reset，测试使用临时题目目录和数据库。

历史题目 JSON 中已写出的 time_limit/memory_limit 继续按显式配置处理，无法推断其曾经是否由旧默认值生成。重置与后台任务使用当前单进程架构，多进程共享运行数据库不在此实现支持范围。实际评分仍取决于助教测试与人工验收。

## 修复前的核查记录

核查时间：2026-09-06。代码版本：`2a7e2df0207ac71a9f4bc184429917d7a63242a3`。

依据：[课程 API 文档](https://dbg-course.github.io/python-docs/oj/api/)，页面标注更新日期为 2026-09-03。核查使用线上正文、后端源码、临时数据库 API 探针及 GitHub Ubuntu CI 日志。没有使用助教的私有测试，也没有修改业务代码或开发数据库。

结论：**尚未完全符合 API 文档。Linux 下已有实际测试通过记录，主要缺口是接口契约、日志可见性和异常处理；本机 WSL 尚未配齐运行依赖。**

## 覆盖范围

基础 API 加测试重置接口共 22 个 HTTP 方法/路径组合，当前实现其中 20 个；路由存在不代表全部语义符合。

| 分组 | 文档接口 | 核查结果 |
| --- | --- | --- |
| 题目 | `GET/POST /api/problems/`、`GET/PUT/DELETE /api/problems/{problem_id}` | 五项均存在；字段默认值、编辑 ID 一致性、管理员删除、持久化已有测试 |
| 评测 | `POST/GET /api/submissions/`、`GET /api/submissions/{submission_id}`、`PUT /api/submissions/{submission_id}/rejudge` | 四项均存在；pending、成绩、总分、总体编译/运行信息和重评覆盖已有记录；组合异常优先级有偏差 |
| 语言 | `GET/POST /api/languages/` | 两项均存在；支持文档中的 `{src}`、`{exe}` 命令模板；旧数据库解释器路径存在迁移风险 |
| 用户 | `POST /api/auth/login`、`POST /api/auth/logout`、`POST /api/users/admin`、`POST/GET /api/users/`、`GET /api/users/{user_id}`、`PUT /api/users/{user_id}/role` | 七项均存在；初始管理员、Cookie、密码哈希、本人/管理员权限、分页与用户统计有现有测试 |
| 日志 | `GET /api/submissions/{submission_id}/log`、`GET /api/logs/access/` | 路由存在；可见性与 action 字段不符合，见下文 |
| 日志可见性 | `PUT /api/problems/{problem_id}/log_visibility` | 缺失 |
| 测试重置 | `POST /api/reset/` | 缺失 |
| AI Advance | 模型配置、创建/查询任务、事件、取消、Token 与费用统计 | 使用 `/api/agent/...` 等价设计；文档允许路径和字段结构不同，但管理员权限及结束任务取消行为有差异 |

## 必须处理的基础 API 差异

### 1. 日志可见性功能缺失（高优先级）

文档要求管理员可配置 `public_cases`，默认 False；普通用户仅在公开时可见逐测试点 `details`，管理员可见。当前：

- 管理员调用 `PUT /api/problems/audit_sum/log_visibility` 返回 `404 {"detail":"Not Found"}`。
- `EvaluationLogService.get_visible()` 仅按“本人或管理员”授权，不读取任何公开设置。
- 探针在未配置公开状态的题目下创建已完成提交，普通提交者仍得到完整 `details`。
- 不存在公开后供其他已登录用户访问的授权分支。

相关代码：`backend/app/modules/logs/service.py:37`、`:48`、`:51`，`backend/app/api/router.py`。现有 `tests/test_app.py:57` 反而断言该配置接口不存在；README 也说明不再读取旧的可见性表。修复必须同步修改这部分测试与文档，不能仅恢复一个路由。

### 2. 缺少自动测试重置接口（高优先级）

管理员调用 `POST /api/reset/` 得到 404。文档要求清空测试用户、题目、提交数据，退出登录并重建初始管理员，返回 `200 / system reset successfully / data:null`。

文档注明该接口不计 Step 6 分数，但自动测试可能依赖它隔离测试数据。不能据此保证缺失不影响自动评测，也不能声称一定会因此丢失全部分数。

### 3. 异常优先级不一致（高优先级）

文档明确规定：`401 > 403 > 400 > 429 > 409 > 404 > 500`。

| 独立临时数据库中的复现场景 | 实际 | 文档要求 |
| --- | --- | --- |
| 未登录，提交损坏的 JSON 到 `/api/submissions/` | 400 | 优先 401 |
| 普通用户查询其他人的提交，同时 `page=1` 而缺 `page_size` | 400 | 优先 403 |
| 一分钟内已经成功提交三次，再提交不存在的题目 | 404 | 优先 429 |

对照场景：未登录且 JSON 合法但缺字段时返回 401；超过限额但题目正常时返回 429。因此问题是组合异常的判断顺序，不是相关状态码完全没有实现。

原因分别为框架在依赖鉴权前解析损坏 JSON、`SubmissionService.list_visible()` 先检查分页再检查目标用户权限、`SubmissionService.create()` 先查资源再查频率。相关代码：`backend/app/modules/submissions/service.py:46`、`:85`。应补充交叉条件测试。

### 4. 日志审计 action 拼写不符（中优先级）

文档明确要求 `view_logs`，`GET /api/logs/access/` 实际返回 `view_log`。内部记录用的是正确复数形式，错误发生在响应转换处：`backend/app/modules/logs/router.py:86`。

### 5. 异常响应未统一（中优先级）

文档要求 API JSON 响应含 `code` 且与 HTTP 状态码一致。当前路由未找到时返回 `{"detail":"Not Found"}`；在临时应用中注入一个受控的语言列表异常后，得到 HTTP 500、纯文本 `Internal Server Error`。

`backend/app/core/exceptions.py:32` 仅注册 FastAPI `HTTPException` 与 `RequestValidationError` 处理器，未统一 Starlette 路由错误和未捕获异常。应增加安全的 JSON 兜底，不回显异常堆栈或敏感内容。

## Advance 行为差异

路径、事件采用 JSON 轮询和字段名称不同本身不构成违约；课程文档明确允许等价实现，README 已介绍当前方案。仍有以下语义偏差：

1. 文档允许任务创建者或管理员查询任务/事件，当前 `_owned_task()` 不给管理员例外。探针中管理员读取其他用户的已存在任务返回 404。位置：`backend/app/modules/agent/router.py:58`。
2. 文档列出任务结束后取消应返回 409；当前 `AgentTaskManager.cancel()` 对结束状态直接返回，HTTP 接口仍返回 200 和 `cancellation requested`。位置：`backend/app/modules/agent/task_manager.py:156`。
3. 指定不存在的参考题目，源码将其转成 ValueError，创建任务接口返回 400；文档列的是 404。位置：`backend/app/modules/agent/task_manager.py:109`、`backend/app/modules/agent/router.py:149` 附近。这一项为源码核查，没有访问真实模型服务。

配置加密、密钥不明文回传、任务隔离、真实取消执行、Token 费用统计已有项目测试。未进行真实模型服务端到端验收。

## Linux 核查

### 已有正面证据

[当前提交的 GitHub CI](https://github.com/zipolll/programming-training-project-2-OJ/actions/runs/34024302990) 已完成：

| 环境 | 结果 |
| --- | --- |
| Ubuntu 24.04 / Python 3.10.21 | 337 passed，2 warnings，156.36 秒 |
| Ubuntu 24.04 / Python 3.12.14 | 337 passed，2 warnings，192.11 秒 |

两个任务的 Ruff 也通过；测试摘要无 skipped。现有 C++ 编译与 AC/CE/RE/TLE、Python AC/WA/RE/TLE/MLE、超时子进程清理等测试因此已有 Linux 执行证据。这不是助教隐藏测试结果。

源码对应能力：

- `shlex.split(..., posix=True)` 解析命令；不调用 Windows shell。
- 默认 C++ 用 `g++`，Linux 输出文件为 `program`，Windows 才使用 `program.exe`。
- `{src}` 与 `{exe}` 展开为工作区路径；默认临时目录下为绝对路径，满足文档强调的路径要求。
- Linux 使用 `resource.setrlimit(RLIMIT_AS/RLIMIT_CPU)`、独立进程组与 `os.killpg`；Windows 单独使用降级实现。
- 文档的 `python3 {src}`、`g++ {src} -o {exe}`、`{exe}` 模板与现有解析方式兼容，实际运行要求相关解释器/编译器已安装。
- 不支持任意管道、重定向、`&&` 等 shell 语法；API 正文展示的模板不依赖这些语法，因此不能把这点直接认定为课程不合格，也不能承诺支持“所有 Linux 命令”。

### 本机 WSL 当前状态

已安装 `Ubuntu` WSL2，探测到 Linux `6.6.87.2-microsoft-standard-WSL2`、`/usr/bin/python3` 3.12.3。当前 PATH 下未找到 `g++`、`cc`、`make`、`pytest`；Python 也没有 pip、FastAPI。只做了读取与探测，未安装依赖。

建议在 Ubuntu 内独立克隆项目、创建 Linux 虚拟环境，安装 `python3-venv`、`python3-pip`、`build-essential` 后安装项目依赖，再运行 `python -m pytest` 和 `python -m uvicorn backend.app.main:app`。评分环境的实际端口或启动协议以老师后续要求为准；本 API 页面未规定额外的提交启动脚本名称。

### Windows 数据库复用风险（已复现配置行为）

`default_languages()` 保存 `sys.executable`；语言初始化采用 `INSERT OR IGNORE`，不会更新已有记录。临时数据库中预置 Windows 风格解释器路径，再调用初始化后仍保留旧路径。

因此直接从 WSL 运行 `/mnt/d/...` 下现有 Windows 工作目录、同时复用 `data/runtime/oj.sqlite3`，会沿用旧解释器路径，存在评测启动失败风险。Windows `.venv` 也不能当作 Linux 虚拟环境使用。独立 Linux 环境应使用新的运行数据库，或者显式迁移/修复语言配置；不要为解决此问题直接删除有价值的数据。

仓库仅跟踪 `data/runtime/.gitkeep`，不跟踪 SQLite 数据库；从 GitHub 全新克隆、在 Linux 首次初始化不会继承本机 Windows 数据库路径。

## 建议修复顺序与验证边界

先恢复日志可见性与测试重置，再修复异常优先级、审计 action 和响应兜底；随后对齐 Advance 行为，最后补齐 WSL 环境及跨系统语言配置迁移措施。

核查中的 API 探针使用全新临时数据库；提交队列替换为空操作以测试接口契约，日志测试注入确定的已完成结果，AI 测试仅插入本地任务记录。因此这些探针证明接口差异，不代替真实编译、资源限制或模型服务验证。Linux 评测证据来自上述当前提交 CI；本机 WSL 未运行完整测试。

修复后应新增遵循课程文档的回归测试，并在 Linux 上运行。仅重复现有测试，无法覆盖本报告发现的合同差异。
