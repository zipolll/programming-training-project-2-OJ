# Programming Training Project 2 — Online Judge

程序设计训练大作业二的 Online Judge 项目。本仓库目前提供可运行的 FastAPI 后端、Streamlit 前端和测试基础设施；公共异步数据层、用户认证与课程 Step 1 题目管理已经实现；评测、提交、日志与 AI 命题功能将在后续提交中逐步实现。

## 环境要求

- Python 3.10 或更高版本
- 最终评测环境为 Linux；Windows 用户建议使用 WSL
- C++ 评测功能后续需要 GCC 9+ 和 C++14

## 安装

```bash
python -m venv .venv
```

激活虚拟环境后安装开发依赖：

```bash
python -m pip install -r requirements-dev.txt
```

如需覆盖默认配置，将 `.env.example` 复制为 `.env` 后修改。不要提交 `.env` 或任何密钥。

默认 SQLite 数据库位于 `data/runtime/oj.sqlite3`，启动时自动创建数据表与初始管理员（用户名 `admin`，密码 `admintestpassword`）。数据库文件和 `.env` 均已被 Git 忽略。可通过 `OJ_DATABASE_PATH` 修改数据库位置，通过 `OJ_PROBLEMS_PATH` 修改题目目录，通过 `OJ_SESSION_MAX_AGE_SECONDS` 修改 Session 有效期；生产 HTTPS 环境应设置 `OJ_SESSION_COOKIE_SECURE=true`。

## 启动

启动后端：

```bash
python -m uvicorn backend.app.main:app --reload
```

API 健康检查位于 <http://localhost:8000/api/health>，交互文档位于 <http://localhost:8000/docs>。本阶段还提供以下用户接口：

- `POST /api/users/register`：注册普通用户。
- `POST /api/users/login`：登录并设置随机的 HttpOnly Session Cookie。
- `POST /api/users/logout`：注销并立即作废当前 Session。
- `GET /api/users/me`：查询当前登录用户。

用户名长度为 3–40 个字符，密码至少 6 位。接口响应不会返回密码、密码哈希或 Session ID。

课程 Step 1 题目接口如下，均使用统一的 `{code, msg, data}` 响应结构：

- `GET /api/problems/`：登录用户查看按题号稳定排序的题目摘要列表。
- `GET /api/problems/{problem_id}`：登录用户查看完整题目配置。
- `POST /api/problems/`：登录用户新增完整题目。
- `PUT /api/problems/{problem_id}`：登录用户完整替换题目配置。
- `DELETE /api/problems/{problem_id}`：管理员删除题目。

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
