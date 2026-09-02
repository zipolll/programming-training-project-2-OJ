# Programming Training Project 2 — Online Judge

程序设计训练大作业二的 Online Judge 项目。本仓库目前提供可运行的 FastAPI 后端、Streamlit 前端和测试基础设施；公共异步数据层、用户认证、课程 Step 1 题目管理、Step 2 语言注册和评测引擎、Step 2/3 Submission 生命周期，以及 Step 4/5 用户权限、评测日志与访问审计已经实现。前端管理页面与 AI 命题功能仍留待后续阶段。

## 环境要求

- Python 3.10 或更高版本；课程目标解释器版本为 Python 3.10
- C++ 需要 GCC 9+，统一使用 `-std=c++14` 编译
- 最终评测环境为 Linux；Windows 用户强烈建议在 WSL 中运行评测服务

## 安装

```bash
python -m venv .venv
```

激活虚拟环境后安装开发依赖：

```bash
python -m pip install -r requirements-dev.txt
```

如需覆盖默认配置，将 `.env.example` 复制为 `.env` 后修改。不要提交 `.env` 或任何密钥。

默认 SQLite 数据库位于 `data/runtime/oj.sqlite3`，启动时自动创建数据表、内置 Python/C++ 语言和初始管理员（用户名 `admin`，密码 `admintestpassword`）。数据库文件和 `.env` 均已被 Git 忽略。可通过 `OJ_DATABASE_PATH` 修改数据库位置，通过 `OJ_PROBLEMS_PATH` 修改题目目录，通过 `OJ_SESSION_MAX_AGE_SECONDS` 修改 Session 有效期；生产 HTTPS 环境应设置 `OJ_SESSION_COOKIE_SECURE=true`。

## 启动

启动后端：

```bash
python -m uvicorn backend.app.main:app --reload
```

API 健康检查位于 <http://localhost:8000/api/health>，交互文档位于 <http://localhost:8000/docs>。课程用户接口为：

- `POST /api/users/`：注册普通用户。
- `POST /api/auth/login`、`POST /api/auth/logout`：登录和登出。
- `GET /api/users/{user_id}`：本人或管理员查询用户信息和统计。
- `GET /api/users/`：管理员分页查询用户列表。
- `POST /api/users/admin`：管理员创建管理员。
- `PUT /api/users/{user_id}/role`：管理员设置 `user`、`admin` 或 `banned`。

旧的 `/api/users/register|login|logout|me` 路径保留为兼容别名；新代码应使用课程 API 路径。

用户名长度为 3–40 个字符，密码至少 6 位。接口响应不会返回密码、密码哈希或 Session ID。

## 用户角色与权限

| 操作 | 未登录 | user | admin | banned |
| --- | --- | --- | --- | --- |
| 查看题目、创建/编辑题目、创建语言、提交 | 401 | 允许 | 允许 | Session 作废 |
| 查看用户信息 | 401 | 仅本人 | 任意用户 | 不允许 |
| 用户列表、修改角色 | 401 | 403 | 允许 | 不允许 |
| 删除题目、重新评测 | 401 | 403 | 允许 | 不允许 |
| Submission 详情 | 401 | 仅本人 | 任意提交 | 不允许 |
| 私有评测日志 | 401 | 仅本人 | 任意日志 | 不允许 |
| 公开评测日志 | 401 | 任意已登录用户 | 任意日志 | 不允许 |

用户变为 `banned` 时，其全部数据库 Session 会立即删除，之后登录返回 403。系统禁止将最后一个有效管理员降级或封禁，避免不可恢复的权限状态。`submit_count` 直接统计该用户持久化 Submission 总数；`resolve_count` 只统计 `status=success` 且最终结果为 `AC` 的不同 `problem_id`，因此同题多次 AC 只算一次，WA、pending 和 error 均不计入。

课程 Step 1 题目接口如下，均使用统一的 `{code, msg, data}` 响应结构：

- `GET /api/problems/`：登录用户查看按题号稳定排序的题目摘要列表。
- `GET /api/problems/{problem_id}`：登录用户查看完整题目配置。
- `POST /api/problems/`：登录用户新增完整题目。
- `PUT /api/problems/{problem_id}`：登录用户完整替换题目配置。
- `DELETE /api/problems/{problem_id}`：管理员删除题目。

课程 Step 2 语言接口：

- `GET /api/languages/`：查询当前启用的语言名称列表。
- `POST /api/languages/`：登录用户注册语言；请求字段严格遵循课程 API 的 `name`、`file_ext`、`compile_cmd`、`run_cmd`、`time_limit` 和 `memory_limit`。

命令模板仅允许 `{src}`、`{exe}` 占位符。系统会用 `shlex` 将 API 中的字符串模板转换为参数数组，拒绝管道、重定向、命令连接符、变量展开和未知占位符；执行始终使用 `asyncio.create_subprocess_exec`，不会启用 shell。语言配置持久化在公共异步 SQLite 数据层中，名称全局唯一。

## 评测引擎

下一阶段的 Submission 后台任务可直接调用异步接口：

```python
result = await request.app.state.judge_service.judge(
    JudgeRequest(problem_id="P1001", language="python", code=source_code)
)
```

评测器在操作系统临时目录中为每次请求创建独立工作区，编译一次后逐个运行题目的所有测试点，结束时清理源文件、可执行文件和临时数据。每个 AC 测试点计 10 分；单点结果为 `AC`、`WA`、`TLE`、`MLE`、`RE`、`CE` 或 `UNK`。它会限制采集的 stdout/stderr，按 UTF-8 严格解码输出，并且仅忽略每行末尾空格及输出末尾多余换行。

Linux/WSL 下同时通过 `resource.setrlimit` 限制地址空间和 CPU 时间，并由 `psutil` 监控主进程及其递归子进程；超时或超内存时终止整个进程组。Windows 下通过 `psutil` 监控和终止进程树，并使用异步墙钟超时，但没有与 Linux `setrlimit` 完全等价的内核级限制，因此属于开发环境的安全降级。可配置项包括：

- `OJ_JUDGE_COMPILE_TIMEOUT_SECONDS`：编译超时，默认 10 秒。
- `OJ_JUDGE_COMPILE_MEMORY_LIMIT_MB`：编译内存上限，默认 512 MB。
- `OJ_JUDGE_OUTPUT_LIMIT_BYTES`：每条 stdout/stderr 流的最大采集量，默认 64 KiB。
- `OJ_JUDGE_TEMP_ROOT`：可选的临时目录根；必须指向项目源码树之外的受控目录。未设置时使用操作系统临时目录。

该评测器满足课程作业的单用户异步评测、资源限制和多语言要求，但不是面向不可信互联网用户的生产级安全沙箱。它不提供容器/虚拟机隔离、网络隔离、系统调用过滤或多租户防护；不要将其直接暴露给不可信公网流量。

## Submission 生命周期

课程 Step 2/3 接口如下：

- `POST /api/submissions/`：登录用户提交代码并立即获得 `pending` 状态。
- `GET /api/submissions/`：按用户或题目筛选，支持状态与分页；普通用户始终只能看到自己的提交。
- `GET /api/submissions/{submission_id}`：提交者本人或管理员查看总体结果。
- `PUT /api/submissions/{submission_id}/rejudge`：管理员启动重新评测。

Submission 的 `status` 只有 `pending`、`success` 和 `error`。`pending` 表示等待或正在执行；`success` 表示评测流程正常完成，因此用户程序得到 `AC`、`WA`、`CE`、`RE`、`TLE`、`MLE` 或 `UNK` 都属于 `success`；只有评测基础设施、任务数据或调度发生异常时才使用 `error`。测试点结果含义分别为通过、答案错误、编译错误、运行错误、超时、超内存和未知结果。

应用 lifespan 启动一个受统一追踪的单 worker `asyncio.Queue`。提交记录先事务持久化，再入队；worker 会从数据库重新读取 Submission、Problem 和 Language，并调用已有 judge service。启动时会恢复数据库中遗留的 `pending` 记录，关闭时停止接收任务、限时等待队列并取消 worker。每次重评都会原子增加 `evaluation_version`，写回结果时同时匹配版本与 `pending` 状态，旧任务不能覆盖较新的结果。

SQLite 会保存最终结果、总分、编译/运行输出、耗时、内存和每个测试点的 `id/result/time/memory/error_summary`。Step 3 的列表与详情接口不会返回测试点明细；这些数据预留给 Step 5 日志接口。stdout、stderr、编译信息和测试点错误摘要在持久化前均有限长处理。

## 评测日志与访问审计

`GET /api/submissions/{submission_id}/log` 返回当前评测版本的逐测试点 `details`、得分和总分。Submission 详情表示一次任务的总体状态；Evaluation Log 表示该任务当前版本的测试点明细，两者不会混在同一响应中。管理员可通过 `PUT /api/problems/{problem_id}/log_visibility` 持久化设置题目 `public_cases`：默认私有；公开后所有已登录用户可查看该题提交的日志，但仍不能借此读取他人的 Submission 总体结果。

独立的 `audit_logs` 表以结构化字段记录操作者、动作、目标、成功状态、HTTP 状态、必要变更摘要和时间。当前审计覆盖日志查看（包括已登录用户被拒绝的 403）、日志可见性变更、角色/封禁变更、管理员重评和题目删除。管理员可通过 `GET /api/logs/access/` 查询课程规定的日志访问记录。审计摘要不保存密码、密码哈希、Session/Cookie、完整用户代码、请求体或模型密钥；普通运行日志不能替代该审计表。

数据库初始化会幂等创建 `problem_log_visibility` 和 `audit_logs` 及索引。旧题目没有可见性记录时按私有处理；重复初始化不会删除或重写已有用户、题目、Submission 或测试点结果。

## 题目存储

每道题保存为 `data/problems/<problem_id>.json`。JSON 包含 `id`、标题与题面、输入输出说明、样例、约束、测试点，以及提示、来源、标签、时间/内存限制、作者和难度等可选字段。`samples` 与 `testcases` 都是由 `{input, output}` 组成的非空列表；可选字段缺省时按课程 API 返回 `""`、`[]`、`3.0` 秒和 `128` MB 等默认值。

题号只允许字母、数字、下划线和连字符，且必须以字母或数字开头。持久化由 repository 层在线程中完成，写入使用同目录临时文件与原子替换，避免更新失败破坏已有题目。测试通过 `OJ_PROBLEMS_PATH`/应用设置指向 pytest 临时目录，不会污染 `data/problems`。

另开终端启动前端：

```bash
python -m streamlit run frontend/app.py
```

## 质量检查

```bash
python -m ruff check .
python -m pytest
```

只运行题目管理测试：

```bash
python -m pytest tests/test_problems.py
```

只运行评测与语言测试：

```bash
python -m pytest tests/test_languages.py tests/test_comparator.py tests/test_judge.py
```

只运行 Submission 生命周期测试：

```bash
python -m pytest tests/test_submissions.py
```

在 Windows 原生环境中测试会验证安全降级路径；提交前还应在 Linux/WSL 中运行完整测试，以覆盖 `setrlimit` 与进程组终止逻辑。测试使用临时 SQLite 数据库和临时题目目录，不会污染开发数据。

## 提交规范

所有提交必须遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/v1.0.0/)：

```text
<type>(optional-scope): <description>
```

允许的类型包括 `feat`、`fix`、`docs`、`style`、`refactor`、`perf`、`test`、`build`、`ci`、`chore` 和 `revert`。示例：

```text
feat(problems): add problem creation endpoint
fix(judge): terminate timed-out subprocesses
docs: document local development setup
```

安装仓库自带的提交信息校验钩子：

```bash
python scripts/install_git_hooks.py
```

## 项目结构

```text
backend/app/       FastAPI 应用、公共基础设施和业务模块
frontend/          Streamlit 前端和 API 客户端
data/              题目配置及运行数据目录
tests/             自动测试
scripts/           项目维护脚本
```
