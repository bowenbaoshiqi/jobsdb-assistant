# JobsDB Assistant

当前产品版本：`v0.3.0`。新产品基于上游 JobsDB 自动投递引擎 v2.0
构建；历史 `v2.0-phase*` 标签仅代表上游引擎的重构阶段。

`v0.3.0` 在单关键词 JobsDB 香港职位发现之上，增加确认后版本化的候选人画像，
以及 career-ops 原生 A–F、1.0–5.0 职位评分。Claude Code/Codex 提供 AI
推理，Python 与 SQLite 稳定控制校验、缓存和报告。原有 Quick Apply 投递流程
保持不变。

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

### 2. 发现职位（不会投递）

```bash
uv run jobsdb-assistant discover \
  --keyword "Product Manager" \
  --login-mode manual
```

地区固定为香港，其他搜索筛选使用 JobsDB 默认值。首次运行可以在打开的浏览器
中手动登录；命令只抓取并保存职位，不会进入申请状态机，也不会提交申请。

### 3. 在 Claude Code 或 Codex 中生成画像并评分

仓库内置同一套 `jobsdb-assistant` Skill：

- Codex/open-agent：`.agents/skills/jobsdb-assistant/SKILL.md`
- Claude Code：`.claude/skills/jobsdb-assistant/SKILL.md`

在 CC/Codex 中说“用 jobsdb-assistant 搜索并评分 AI Architect 职位”。保持
当前 Agent 会话直到任务完成。首次运行会：

1. 按 manifest 安装两个固定 SHA 的 public fork；
2. 使用 ai-job-search onboarding 能力提取资料，并完成 Python 强制校验的
   画像访谈；薪资和推荐人等敏感项可以明确选择不提供；
3. 展示候选人画像，等待你明确确认后保存 `CandidateProfile v1`；
4. 抓取 JobsDB 当前职位；
5. 使用 career-ops 原生 A–F 规则评分；
6. 输出完整本地报告。

后续运行默认复用已安装的 fork、已确认画像和未变化 JD 的评分缓存。只有明确要求
更新画像时才创建 `v2`；不会自动覆盖旧版本或自动更新 fork。

Python CLI 是 Skill 使用的稳定协议：

```bash
uv run python -m src.main workflow profile-prepare --run-id RUN_ID --source PATH
uv run python -m src.main discover --keyword "AI Architect"
uv run python -m src.main workflow evaluation-prepare --run-id RUN_ID
uv run python -m src.main workflow report
```

包含简历、画像、JD 和 AI 结果的检查点保存在忽略的
`workspace/ai-tasks/`。v0.3 不生成定制简历/求职信，也不从评分流程执行投递。
单份简历首次导入不能直接生成画像提案：必须先回答或明确跳过全部必问维度，
Python 才允许 Agent 提交画像。

### 4. 登录并投递（manual 模式，无需存凭证）

```bash
uv run jobsdb-assistant start --login-mode manual --max-jobs 5
```

首次运行会打开浏览器等你手动登录 JobsDB（可过验证码）。登录态存入持久化 profile（`data/browser_profile/`），之后长期复用，无需再登录。

### 5. 投递

```bash
scripts/run_apply.sh 5     # 一键投递(推荐),先校验登录 cookies 再启动;不传数字默认 5
python -m src.main stats   # 查看统计
```

### 6. Claude Code 投递 Skill：说"帮我投5个"

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

### v0.3.0 (2026-07-24) — Candidate & Evaluation

- 固定 SHA、只读校验的 ai-job-search 与 career-ops public forks
- ai-job-search 候选人 onboarding、事实证据、显式确认和不可变画像版本
- Python 强制的 typed 画像访谈门禁，禁止 Agent 跳过缺失信息提问
- career-ops 原生 A–F、1.0–5.0 职位评分，不混合评分或自定义加权
- `JD hash + profile hash + engine SHA + contract` 精确增量缓存
- 私有、原子、schema-bound CC/Codex AI 检查点
- 当前 JobsDB 职位安全排序报告；不渲染完整 JD 或候选人原始资料

### v0.2.0 (2026-07-24) — JobsDB Discovery

- 单一关键词搜索，地区默认为香港，每次最多收集 50 个唯一职位
- 复用现有抓取器的滚动能力，以达到上限或连续无新增为停止条件
- 保存完整 JD，并分类为 `Quick Apply`、`Apply` 或 `unknown`
- SHA-256 不可变 JD 快照，支持新增、未变化和内容变更检测
- `discover` 与申请队列隔离，不会触发投递

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
├── adapters/    # ai-job-search / career-ops schema-bound 检查点
├── application/ # 候选人画像、增量评分和 v0.3 主流程
├── browser/     # 浏览器抽象层(ports / fake / playwright 实现 / stealth)
├── domain/      # 画像、JD、原生 A–F 评分契约
├── integrations/# 固定 fork manifest 与只读校验
├── jobsdb/      # JobsDB 交互(apply 状态机、login、selectors)
├── reporting/   # 本地安全评分报告
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

详见 [v0.2.0 实现计划](docs/superpowers/plans/2026-07-24-v0.2.0-jobsdb-discovery.md)。

## 📄 许可证

MIT License
