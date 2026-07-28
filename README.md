# JobsDB Assistant

当前开发版本：`v0.6.0`。新产品基于上游 JobsDB 自动投递引擎 v2.0
构建；历史 `v2.0-phase*` 标签仅代表上游引擎的重构阶段。

`v0.6.0` 完成从职位选择、定制材料审核到申请执行的本地闭环。用户可以为每个
职位只生成英文求职信并保留 JobsDB 默认简历，也可以生成独立英文简历和求职信。
定制简历只替换固定 v5 模板的 `Professional Summary`、四条
`Career Highlights` 和三项 `Core Competencies`，工作经历及后续内容保持
不变。Quick Apply 必须由用户先准备、再确认提交；Apply 只做人工材料交接。

所有候选人资料、JD、定制简历、求职信、cookies、浏览器 profile、SQLite、
日志和截图只保存在本地忽略目录，CI 不上传任何运行时 artifact。

## 🚀 快速开始

### 1. 安装

```bash
uv venv --python 3.11
uv sync --extra dev --extra dashboard
uv run playwright install chromium
uv pip list
uv run jobsdb-assistant --version
uv run jobsdb-assistant doctor
```

依赖版本由 `uv.lock` 固定。其他电脑首次使用时，在仓库根目录执行以上相同命令，
即可创建统一的项目 `.venv`；不要为 Dashboard 单独创建第二套环境。

将唯一的两页 v5 简历 PDF 放在私有路径
`workspace/resume-template-v5.pdf`。也可通过
`JOBSDB_RESUME_TEMPLATE_PATH=/absolute/path/resume-v5.pdf` 指定其他位置。
career-ops 的 `cv.md` 只作为评分上下文，不会被误当成 PDF 模板。

### 2. 发现职位（不会投递）

```bash
uv run jobsdb-assistant discover \
  --keyword "Product Manager"
```

地区固定为香港，其他搜索筛选使用 JobsDB 默认值。命令直接打开公开 JobsDB
页面抓取并保存职位，不读取账户、不登录、不要求邮箱或密码，也不会进入申请
状态机或提交申请。

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
`workspace/ai-tasks/`。评分阶段不会生成申请材料或执行投递；材料只在用户
通过 Dashboard 选定职位后生成。
单份简历首次导入不能直接生成画像提案：必须先回答或明确跳过全部必问维度，
Python 才允许 Agent 提交画像。

### 4. 启动本地审核 Dashboard

先检查依赖、SQLite schema、数据数量和默认端口：

```bash
uv run python -m src.main dashboard doctor
```

然后启动服务：

```bash
uv run python -m src.main dashboard start
```

服务固定监听 `127.0.0.1:8765`，健康检查为
`http://127.0.0.1:8765/health`，并自动打开本地浏览器。使用 `Ctrl+C`
停止。若不希望自动打开浏览器：

```bash
uv run python -m src.main dashboard start --no-browser
```

若端口被占用，命令会明确失败，不会静默换端口；可显式指定：

```bash
uv run python -m src.main dashboard doctor --port 8877
uv run python -m src.main dashboard start --port 8877
```

Dashboard 默认只显示已评分职位，也可切换到全部职位查看
`Pending evaluation`。展开职位可检查 Career Ops 原生 A–F findings、
evidence、Profile/JD/engine 版本溯源；页面不会自行补造逐条 Profile
判定。

每个职位可立即勾选或取消，状态保存在本地 SQLite。选择一个或多个职位后，可
点击以下任一入口，Python 会为每个职位创建独立任务：

- **仅定制求职信**：生成 100–300 个英文单词的求职信，不生成 PDF；批准后
  投递使用 JobsDB 当前默认简历，不删除、上传或切换简历。
- **定制简历 + 求职信**：每个职位独立生成一份英文简历 PDF 和一封
  100–300 个英文单词的求职信；选择五个职位会得到五套互不覆盖的材料。
- **Quick Apply**：可以使用已批准的职位材料准备申请，也可以在明确确认后直接使用
  **JobsDB default CV**、**no cover letter** 投递当前单个职位。
- **Apply**：只提供打开 JobsDB 职位详情的入口，由用户找到企业网站并人工投递。

当前 CC/Codex Agent 会话通过以下稳定 Python 协议逐个处理材料任务：

```bash
uv run python -m src.main workflow material-pending
uv run python -m src.main workflow material-submit --task-id TASK_ID --result RESULT_JSON
uv run python -m src.main workflow material-progress --batch-id BATCH_ID
```

材料保存在私有的 `workspace/materials/<job-id>/v<version>/`。完整模式预览
PDF；仅求职信模式明确显示将使用 JobsDB 默认简历。两种模式都展示求职信、
修改摘要、Reviewer 建议、ATS 建议和事实一致性检查：

- Reviewer 与 ATS 只展示建议，不阻塞批准。
- 发现疑似虚构内容时材料仍保留，但标记为事实风险；用户可拒绝、重新生成，
  或勾选事实风险覆盖后批准。
- 拒绝不会删除材料；重新生成会创建不可变的 N+1 版本并保留历史。
- 只有用户批准且版式完整的版本才可进入投递。

批准后，Quick Apply 显示“使用已批准材料准备申请”。前台 Worker 会串行执行：

1. 完整模式保留默认简历、删除其他非默认简历，再上传并校验当前职位的定制 PDF；
2. 仅求职信模式跳过全部远程简历管理操作，继续使用 JobsDB 默认简历；
3. 根据模式选择定制简历或默认简历，并填写对应求职信；
4. 停在 Review 页面，等待用户在 Dashboard 点击“确认提交”；
5. 复用同一浏览器页面完成提交并记录结果。

关闭 Dashboard 会安全停止 Worker。若提交临界阶段发生异常，状态会标记为
“提交结果待确认”，不会盲目重复提交。Apply 职位在完整模式提供定制简历下载，
仅求职信模式使用 JobsDB 默认简历；两者都会复制求职信并打开 JobsDB 详情页，
由用户自行进入企业网站投递。

直接 Quick Apply 复用原有浏览器状态机、登录态、频率限制和申请历史。同一时间
只允许一个任务；验证码、登录失效或复杂表单会转为人工处理。点击前确认框会明确
说明使用默认 CV、不附求职信以及提交不可由本系统撤回。

### 5. 登录并投递（manual 模式，无需存凭证）

```bash
uv run jobsdb-assistant start --login-mode manual --max-jobs 5
```

首次运行会打开浏览器等你手动登录 JobsDB（可过验证码）。登录态存入持久化 profile（`data/browser_profile/`），之后长期复用，无需再登录。

### 6. 投递

```bash
scripts/run_apply.sh 5     # 一键投递(推荐),先校验登录 cookies 再启动;不传数字默认 5
python -m src.main stats   # 查看统计
```

### 7. Claude Code 投递 Skill：说"帮我投5个"

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

### v0.6.0 (2026-07-28) — Closed-loop Applications

- 固定 v5 两页模板，仅定制 Summary、四条 Highlights 和三项 Competencies
- Python 渲染 PDF，并硬性校验页数、冻结区域文本/坐标、文件大小和可提取文本
- 持久化、可恢复且幂等的职位申请状态和审计事件
- Quick Apply 串行替换远端简历、校验唯一文件名、填写英文求职信
- 支持“仅定制求职信”和“定制简历 + 求职信”两个独立入口
- 仅求职信模式保留 JobsDB 默认简历并跳过远程简历管理
- “准备申请”和“确认提交”两阶段人工门禁，浏览器会话持续到最终结果
- Apply 职位提供完整人工交接，不自动操作企业外部网站
- 保留 v0.4 的默认 CV/no cover letter 快捷入口

### v0.5.0 (2026-07-27) — Tailored Materials

- 多职位批量创建、每职位独立且可恢复的材料任务
- 固定 `ai-job-search` fork 能力的 schema-bound Adapter，不修改上游代码
- 每职位英文定制简历 PDF 与 100–300 词英文求职信
- Reviewer、ATS、事实一致性检查及简体中文 Dashboard 反馈
- PDF/求职信预览、下载/复制、批准、拒绝、事实风险覆盖和 N+1 重新生成
- 私有文件哈希、路径逃逸/软链接/伪 PDF 防护和不可变版本安装
- CC/Codex 前台 Agent 工作流；单任务失败隔离，Python/SQLite 为状态权威
- 明确边界：v0.5 不执行职位投递

### v0.4.0 (2026-07-27) — Review Dashboard

- FastAPI + Jinja2 + Vanilla JS 本地审核界面，仅监听 `127.0.0.1`
- 已评分/全部职位、搜索、分数、Apply 类型和选择状态筛选
- Career Ops 原生 A–F findings/evidence、Profile/JD/engine 溯源可视化
- SQLite 即时保存 `waiting_for_materials` 选择状态
- 单职位 Quick Apply：JobsDB 默认 CV、不附求职信、显式确认、持久任务状态
- Apply 职位保持人工打开和投递，不进入自动浏览器状态机
- 统一 `.venv`、可复现 Dashboard extras、doctor/health/start 操作文档

### v0.3.0 (2026-07-24) — Candidate & Evaluation

- 固定 SHA、只读校验的 ai-job-search 与 career-ops public forks
- ai-job-search 的完整 CV 解析与逐项访谈综合，原始回答由 Python 保存
- 私有、不可变的 career-ops 原生画像包：`cv.md`、`config/profile.yml`、
  `modes/_profile.md`
- ai-job-search 候选人 onboarding、事实证据、显式确认和不可变画像版本
- Python 强制的 typed 画像访谈门禁，禁止 Agent 跳过缺失信息提问
- career-ops 原生 A–F、1.0–5.0 职位评分，不混合评分或自定义加权
- `JD hash + profile bundle hash + engine SHA + contract` 精确增量缓存
- 私有、原子、schema-bound CC/Codex AI 检查点
- 当前 JobsDB 职位安全排序报告；不渲染完整 JD 或候选人原始资料

### v0.2.0 (2026-07-24) — JobsDB Discovery

- 单一关键词搜索，地区默认为香港，每次最多收集 50 个唯一职位
- 公开浏览器发现流程与账户、密码和登录完全隔离
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
├── application/ # 候选人画像、增量评分和材料生成主流程
├── browser/     # 浏览器抽象层(ports / fake / playwright 实现 / stealth)
├── domain/      # 画像、JD、原生 A–F 评分与材料契约
├── integrations/# 固定 fork manifest 与只读校验
├── jobsdb/      # JobsDB 交互(apply 状态机、login、selectors)
├── materials/   # 私有材料校验与不可变安装
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
