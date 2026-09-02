# Programming Training Project 2 — Online Judge

程序设计训练大作业二的 Online Judge 项目。本仓库目前提供可运行的 FastAPI 后端、Streamlit 前端和测试基础设施；题目管理、评测、用户、日志与 AI 命题功能将在后续提交中逐步实现。

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

## 启动

启动后端：

```bash
python -m uvicorn backend.app.main:app --reload
```

API 健康检查位于 <http://localhost:8000/api/health>，交互文档位于 <http://localhost:8000/docs>。

另开终端启动前端：

```bash
python -m streamlit run frontend/app.py
```

## 质量检查

```bash
python -m ruff check .
python -m pytest
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
