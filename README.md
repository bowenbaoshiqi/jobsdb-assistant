# JobsDB Assistant

当前产品版本：`v0.1.0`。新产品基于上游 JobsDB 自动投递引擎 v2.0
构建；历史 `v2.0-phase*` 标签仅代表上游引擎的重构阶段。

`v0.1.0` 是新产品的 public-safe foundation：保留上游 Quick Apply
投递流程，同时为后续 JobsDB 职位发现、评分、定制材料、两阶段审批和本地
Dashboard 建立稳定契约。JobsDB 的按钮名称在本项目中始终记为
`Quick Apply` 或 `Apply`。

所有候选人资料、JD、定制简历、求职信、cookies、浏览器 profile、SQLite、
日志和截图只保存在本地忽略目录，CI 不上传任何运行时 artifact。

## 🚀 快速开始

### 1. 安装

```bash
uv venv && uv pip install -e ".[dev]"
uv run playwright install chromium
uv run jobsdb-assistant --version
uv run jobsdb-assistant doctor
```

### 2. 登录（manual 模式，无需存凭证）

```bash
uv run jobsdb-assistant start --login-mode manual --max-jobs 5
```

首次运行会打开浏览器等你手动登录 JobsDB（可过验证码）。登录态存入持久化 profile（`data/browser_profile/`），之后长期复用，无需再登录。

### 3. 投递

```bash
scripts/run_apply.sh 5     # 一键投递(推荐),先校验登录 cookies 再启动;不传数字默认 5
python -m src.main stats   # 查看统计
```

### 4. Claude Code Skill：说"帮我投5个"（最省事）

仓库附带 skill 文档 [docs/skills/start-apply.md](docs/skills/start-apply.md)，复制到 Claude Code 的项目 skills 目录即可启用：

```bash
mkdir -p .claude/skills/start-apply
cp docs/skills/start-apply.md .claude/skills/start-apply/SKILL.md
```

之后在 Claude Code 里直接说 `帮我投5个`（或 `投10个` / `开始投递`）。Skill 会自动：解析数量 → 检查登录态 → 后台启动 `run_apply.sh` → 盯日志 → 按 ✅/⏭️/❌ 表格汇报（失败附原因和截图）。判读规则已内置，如 `⏭️ skipped` 是标准 Apply 的正常跳过，不是失败。

## 📋 投递行为

- **Quick Apply** → 自动投递三步向导：选 "Don't include a cover letter" → Profile 页一路 Continue（漏填下拉自动补填，选最后一个有效选项）→ 点 Submit 并确认成功页
- **Apply**（跳外部网站）→ 当前引擎不自动提交，保留为后续人工打开详情页
- **验证码 / 复杂表单 / 登录过期** → 弹 macOS 通知，等人工处理
- 频率控制：每小时 ≤10 次，间隔 ≥3 分钟，防封号

## 🧹 清理运行时数据

```bash
python scripts/clean_data.py            # dry-run,只列出要删的
python scripts/clean_data.py --apply    # 实际删除(只动 data/,不碰凭证)
```

## 👥 多账户（可选）

```bash
python -m src.main account add personal --email you@example.com
python -m src.main account use personal
```

每个账户独立的浏览器 profile / cookies / 投递记录（`data/browser_profile/<alias>/` 等），切换账户 = 全新浏览器身份。

## 🔒 安全

本仓库不含真实凭证：`accounts/`、`data/`、`workspace/`、`.env` 和本地
agent 设置均受 `.gitignore` 保护。每次提交前运行：

```bash
uv run python scripts/privacy_guard.py
```

守卫会检查 Git 已跟踪文件中的私有路径和疑似密钥。详见
[PRIVACY_CHECKLIST.md](PRIVACY_CHECKLIST.md)。

## ⚠️ 注意

- 请遵守 JobsDB 使用条款；每次投递数量不宜过多，避免账号被限制
- 拟人化鼠标（Bezier 曲线）+ 指纹伪装 + 会话持久化降低检测风险，但不保证零风控

## 📝 更新日志

### v0.1.0 (2026-07-23) — Public-safe Foundation

- 单一产品版本、领域契约和 SQLite migration ledger
- 不回显私有路径或凭证的 `doctor` 环境诊断
- Git tracked-file 隐私守卫和独立 CI privacy gate
- 408 个确定性测试，line+branch 综合覆盖率 82.49%
- 保留上游 v2.0 Quick Apply 行为

### Upstream v2.0.0 (2026-07-22) — TDD 重构 + e2e 实战加固

- **重构**（行为与 v1.0 一致）：浏览器抽象层（Protocol + Fake 实现）、工厂模式 DI、543 行 apply_flow 拆成状态机 + 7 个 StepHandler、异常三分法清零 8 处静默吞错、覆盖率 39%→65%、ruff 221→0
- **新能力**：manual 登录模式（免存凭证）、`start-apply` skill + `run_apply.sh` 一键投递
- **e2e 加固**：只投 Quick Apply（标准 Apply 记 SKIPPED）、Cover Letter 按 label 文本选择（radio id 动态）、Continue 推进 + 校验自动补填、成功判定扩充、视口外元素先滚动再点、超时单位修复、Apply 按钮重渲染自动重试
- 339 个测试全绿；真实 5 职位会话成功率 100%

### Upstream v0.1.0 (2026-07-20)

首个版本：Quick Apply 识别、Cover Letter 自动处理、多账户、反检测、投递统计。

---

## 🏗️ 技术栈与架构（开发者向，使用无需阅读）

**技术栈**：Python 3.11+ · Playwright · SQLite · Pydantic · pytest · ruff · uv

**架构要点**（v2.0 TDD 重构，Strangler Fig 分 6 阶段迁移）：

- `BrowserPort` / `PageController`（Protocol）依赖反转：`jobsdb/*` 不 import Playwright；测试用 `FakePageController` 毫秒级跑，不起浏览器
- `ComponentFactory` DI：`Orchestrator` 的 10 个依赖由工厂注入，`FakeFactory` 支持全流程内存单测
- 投递状态机：`apply/flow.py` + `steps/` 7 个 StepHandler + `detectors.py` 纯查询
- 异常三分法：A 重试 / B 降级 / C 上抛

```
src/
├── browser/     # 浏览器抽象层(ports / fake / playwright 实现 / stealth)
├── jobsdb/      # JobsDB 交互(apply 状态机、login、selectors)
├── simulation/  # 人类行为模拟(鼠标 Bezier、拟人打字)
├── scheduler/   # 频率控制与队列
├── storage/     # SQLite + cookies
└── orchestrator.py  # 协调器(工厂注入)
```

**测试**（三分类）：`uv run pytest` 默认跑 unit + characterization（不起浏览器）；
e2e 需真实登录，默认跳过。本地 release gate：

```bash
uv run ruff check src/ tests/ scripts/privacy_guard.py
uv run pytest -m 'not e2e' --cov=src --cov-branch --cov-report=term-missing
```

详见 [v0.1.0 实现计划](docs/superpowers/plans/2026-07-23-v0.1.0-public-safe-foundation.md)。

## 📄 许可证

MIT License
