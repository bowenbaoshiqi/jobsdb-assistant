# 隐私保护检查清单

在提交到 GitHub 之前，请确认以下敏感信息**没有被上传**：

## ❌ 绝对不上传的内容

- [ ] `.env` 文件（包含 JOBSDB_EMAIL 和 JOBSDB_PASSWORD）
- [ ] `accounts/` 目录下的所有 JSON 文件（包含真实账号密码）
- [ ] `data/` 目录下的所有内容：
  - `browser_profile*/` - 浏览器 profile（包含登录状态、cookies、浏览历史）
  - `cookies*.json` - 登录 cookies
  - `*.db` / `*.sqlite` - 数据库（包含投递记录）
  - `*.png` / 截图 - 可能包含个人信息
  - `*.log` / 日志 - 可能包含账号信息
  - `auto_apply.log` - 投递日志
- [ ] `workspace/` 下的候选人资料、定制简历、求职信和审批记录
  - `workspace/ai-tasks/` - Agent 任务、结果和临时材料
  - `workspace/materials/` - 每个职位的 PDF、求职信、检查和版本清单
- [ ] `.claude/`、`.codex/`、`.agents/` 中的本地设置（共享 skill 除外）
- [ ] 任何位置的 `*.pdf`、`*.docx`、`*.db`、截图或真实职位报告
- [ ] 源码和配置中形似 GitHub、OpenAI、AWS 凭证的字符串

## ✅ 可以上传的内容

- 源代码 (`src/`, `config/`, `scripts/`, `tests/`)
- 配置文件模板 (`.env.example`, `config/defaults.yaml`)
- 文档 (`README.md`)
- 共享工作流 skill (`.claude/skills/jobsdb-assistant/` 和
  `.agents/skills/jobsdb-assistant/`)
- 依赖配置 (`pyproject.toml`)
- 示例账户文件 (`accounts/example.json` - 不含真实密码)

## 🔒 已配置的保护措施

`.gitignore` 已配置忽略：
- `.env*` - 环境变量文件
- `data/` - 所有运行时数据
- `accounts/` - 账户凭证（但保留 `example.json`）
- `workspace/` - 候选人资料与生成材料
- 常见简历、截图和数据库扩展名
- agent 本地设置（只放行项目共享 skill）
- `*.log` - 日志文件
- `__pycache__/` - Python 缓存

## 📝 首次使用说明

新用户克隆仓库后需要：

1. 复制环境变量模板：
   ```bash
   cp .env.example .env
   # 编辑 .env 填入你的 JobsDB 账号密码
   ```

2. 添加账户（推荐）：
   ```bash
   python -m src.main account add personal --email your-email@example.com
   ```

3. 安装依赖：
   ```bash
   uv sync --extra dev --extra dashboard
   uv run playwright install chromium
   uv pip list
   ```

4. 每次提交前运行自动隐私检查：
   ```bash
   uv run python scripts/privacy_guard.py
   ```

守卫只扫描 Git 已跟踪文件，因此它是 `.gitignore` 之外的第二道防线。
发现私有路径或疑似密钥时会返回非零退出码，适合在本地和 CI 中执行。
CI 不得使用 artifact upload 上传 `data/`、`workspace/`、PDF、求职信、
SQLite、截图或 Agent 检查点。
