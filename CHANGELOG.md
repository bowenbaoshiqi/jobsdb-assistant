# 更新日志

本项目遵循 [语义化版本](https://semver.org/)。

## [v0.5.0] — 2026-07-27 — Tailored Materials

- Added one resumable, failure-isolated generation task and one immutable
  material package per selected JobsDB job.
- Added a pinned, schema-bound application-material adapter over the existing
  ai-job-search fork without changing the fork.
- Added English tailored CV PDF and 100–300-word English cover letter output.
- Added advisory Reviewer and ATS findings plus explicit factual-consistency
  warnings that users may reject, regenerate, or consciously override.
- Added safe PDF/text staging, hashing, path containment, symlink rejection,
  atomic installation, and immutable N+1 version history.
- Added a Simplified-Chinese local preview and review UI with PDF preview,
  cover-letter copy, approval, rejection, and regeneration.
- Added Python-owned CC/Codex task listing, result submission, and progress
  reporting with isolated failures.
- Kept all application submission outside v0.5.

## [v0.4.0] — 2026-07-27 — Review Dashboard

- Added the loopback-only FastAPI/Jinja2/vanilla-JavaScript review Dashboard.
- Added persisted job selection, native A–F trace views, manual refresh, and
  direct default-CV Quick Apply confirmation.
- Kept Apply jobs manual and preserved the existing browser state machine.

## [v0.3.0] — 2026-07-24 — Candidate & Evaluation

- Added fixed-SHA public-fork integration locks for ai-job-search and
  career-ops without modifying either fork.
- Added evidence-backed candidate onboarding proposals, explicit confirmation,
  immutable profile versions, and normal-run profile reuse.
- Added complete evidence-backed CV extraction and one synthesis per typed
  interview answer while Python preserves the exact raw answers.
- Added deterministic private career-ops-native profile bundles containing
  `cv.md`, `config/profile.yml`, `modes/_profile.md`, and an integrity
  manifest; both pinned forks remain read-only.
- Added a Python-enforced typed interview gate so a first-run CV cannot become
  a proposal until every required dimension is answered or explicitly
  skipped.
- Added native career-ops ordered A–F evaluation with its original 1.0–5.0
  overall score and no score fusion or custom weighting.
- Added exact incremental evaluation caching over JD, native profile bundle,
  engine, and contract hashes.
- Added private atomic JSON checkpoints serviced by the active Claude Code or
  Codex session.
- Added a Python-controlled workflow CLI and safe local evaluation report.
- Corrected public JobsDB discovery so it never resolves credentials or calls
  the login flow; authentication remains exclusive to application execution.
- Kept material generation, Dashboard review, and application execution out of
  the evaluation workflow.

## [v0.1.0] — 2026-07-23 — Public-safe Foundation

- Established the new JobsDB Assistant product version and public privacy gates.
- Added domain contract skeletons and transactional SQLite migration tracking.
- Added redacting environment diagnostics.
- Raised deterministic line and branch coverage to at least 80%.
- Preserved the upstream v2.0 Quick Apply behavior.

The entries below are retained as upstream engine history.

## [v2.1.0] — 2026-07-21 — 手动登录模式 + 残留清理

### 概述

把 v1.0 的手动登录流程收编成正式能力：`LoginHandler` 按 `config.login.mode` 切换 auto/manual，CLI 增 `--login-mode` 旗标。同时清理三份临时 monkeypatch 脚本与 `data/` 下 710MB 运行时残留。

设计文档：[docs/superpowers/specs/2026-07-21-manual-login-mode-design.md](docs/superpowers/specs/2026-07-21-manual-login-mode-design.md)
TDD 证据：[docs/testing/2026-07-21-manual-login-mode.tdd.md](docs/testing/2026-07-21-manual-login-mode.tdd.md)

### 新增

#### 1. `LoginHandler` manual 登录模式
- `LoginHandler.__init__` 增 `login_config: LoginConfig` 参数（默认 None → auto，向后兼容）
- `ensure_logged_in` 按 `config.login.mode` 分支：`manual` → `_do_login_manual`，`auto` → 原 `_do_login`（不变）
- `_do_login_manual`：导航登录页 → logger 通知 → 被动轮询 `_is_logged_in` → 登录成功备份 cookies → 超时返回 False（不抛异常）
- `_backup_session_cookies`：登录成功后备份 jobsdb/seek 域 cookies 到 `data/cookies_<alias>.json`
- **manual 模式不要求凭证**：绕过 `_get_credentials`，持久化 profile 即凭证

#### 2. CLI `--login-mode` 旗标
- `src/main.py start` 增 `--login-mode {auto,manual}`，覆盖 `config.login.mode`
- manual 模式强制 headed（用户需在浏览器窗口登录）

#### 3. 激活闲置的 `LoginConfig`
- `config/login.mode` / `manual_wait_minutes` / `poll_interval_seconds` 此前已定义但从未被源码读取，本次正式激活

#### 4. `scripts/clean_data.py`
- 默认 dry-run，`--apply` 才真删；`--keep-profiles` 保留 `browser_profile` 持久登录态
- 清 24 个 `browser_profile_test_*` + 实验 profile + debug 产物 + 临时 cookies/db/log
- 只动 `data/`，绝不碰 `accounts/`、`.env`

### 变更

- `ComponentFactory.create_login_handler` 增 `login_config` 参数，`DefaultFactory`/`FakeFactory` 同步透传
- `Orchestrator._init_browser` 传 `self.config.login` 给工厂

### 删除

- `run_v2_apply.py` / `run_v2_apply_chrome.py` / `run_v2_apply_manual.py`（均 untracked，能力已被 `--login-mode manual` 取代）
- `data/` 下 710MB 运行时残留（24 个测试 profile、debug HTML/PNG、临时 db/cookies/log）

### 测试

- 新增 `tests/unit/test_login_manual.py`（9 用例）：manual 模式凭证无关、轮询、超时、cookie 备份、auto 回归保护
- 新增 `tests/unit/test_factory.py` 2 用例：`login_config` 透传 / 默认 auto
- 全量回归 309 passed, 1 skipped；总覆盖率 67.52%（超 60% 门槛）；touched files ruff 零告警

### 非目标

- 真实 Chrome profile 方案（系统 Chrome 目录 hack）未收编，另立议题
- OS 通知（osascript）不做，manual 模式仅 logger 通知
- `scripts/auto_apply.py`（v1.0 遗留）未动，超出本次范围

---

## [v2.0.0] — 2026-07-20 — TDD 重构

### 概述

v2.0 是一次**纯重构**：投递行为与 v1.0 完全一致，无新功能。目标是在开发新功能前，按 TDD 模式重写，**降低耦合、增强健壮性**。采用 Strangler Fig 模式分 6 阶段渐进迁移，v1.0 全程可用。

设计文档：[docs/superpowers/specs/2026-07-20-v2.0-design.md](docs/superpowers/specs/2026-07-20-v2.0-design.md)
实现计划：[docs/superpowers/plans/2026-07-20-v2.0-implementation.md](docs/superpowers/plans/2026-07-20-v2.0-implementation.md)

### 架构改进

#### 1. 浏览器抽象层（依赖反转）
- 新增 `src/browser/ports/`：`BrowserPort` + `PageController` 用 `Protocol`（`@runtime_checkable`）定义接口
- `src/jobsdb/*` 只依赖 `PageController` 接口，**不再 import Playwright 的 `Page`**（类型耦合仅留在 `ports/page_controller.py` 的 `ElementHandle`）
- 生产实现：`PlaywrightPageController` / `PlaywrightBrowser`
- 测试实现：`FakePageController` / `FakeBrowser`（纯内存，毫秒级，不起浏览器）

#### 2. 工厂模式依赖注入
- 新增 `src/factory.py`：`ComponentFactory`（Protocol，10 个 create 方法）生产 `Orchestrator` 的全部依赖
- `DefaultFactory` 生产真实组件（等价 v1.0 行为）
- `FakeFactory` 生产内存假组件（`FakeBrowser` + `:memory:` DB）
- `Orchestrator.__init__` 接受 `factory` 参数，单测注入 `FakeFactory` 即可全程不起浏览器、不落盘测协调逻辑

#### 3. 投递流程状态机拆分
- v1.0 的 543 行 `apply_flow.py` God Object 拆成 `src/jobsdb/apply/` 包：
  - `flow.py`：`ApplyFlow` 状态机 + `default_handler_chain()`
  - `steps/`：7 个 `StepHandler`（resume / questions / cover_letter / review / submit / navigation / popup_dismiss / captcha_check），每个独立可测
  - `detectors.py`：纯查询函数（`check_captcha` / `check_success` / `detect_current_step` / `get_error_message`）
  - `step_base.py`：`StepHandler` Protocol + `ApplyStep` 枚举（打破 flow↔detectors 循环 import）

#### 4. 异常三分法（spec §7.3）
- **A 类（重试）**：`RateLimitError` 等可恢复异常，捕获 + 退避重试
- **B 类（降级）**：cookie banner 关闭失败、`wait_for_load_state` 超时等非阻断异常，记日志继续
- **C 类（上抛）**：`CaptchaDetectedError` / `SessionExpiredError` / `LoginError` 等终止性异常，转报告或上抛
- `Orchestrator.run()` 顶层只捕获 `JobsDBError` 子类，其他异常上抛（不再 catch-all 静默吞错）
- **清零** v1.0 的 8 处 `except Exception: pass`

### 测试体系

- **三分类 marker**：`unit` / `characterization` / `e2e`（`pyproject.toml` 配置）
- 默认 `addopts = "-m 'not e2e'"`，本地 pytest 不会误起浏览器
- 覆盖率：39% → **65.37%**（`pyproject` 卡 `fail_under=60`）
- 测试数：298 passed, 1 skipped
- ruff lint：221 errors → **0**（CI 启用 lint job）

新增测试文件：
- `tests/unit/test_browser_ports.py` — 接口契约
- `tests/unit/test_factory.py` — DI 工厂
- `tests/unit/test_orchestrator.py` — Orchestrator 协调 + 边界异常
- `tests/unit/test_apply_steps.py` — 7 个 StepHandler
- `tests/unit/test_apply_with_fake_page.py` — FakePageController 驱动 apply_flow
- `tests/unit/test_fake_page.py` — FakePageController 自身
- `tests/unit/test_tracker.py` / `test_cookies.py` / `test_screenshot.py` — 覆盖率补齐
- `tests/unit/test_playwright_controller.py` — 委托逻辑

### 修复的 v1.0 latent bug

- `src/jobsdb/apply_flow.py` 缺 `import random`（`random.uniform` 在 line 158 会 NameError）
- `src/main.py` 缺 `os` / `shutil` / `Path` import（`clean` 命令会 NameError）
- `FakePageController.text_content` 是同步方法，`await` 一个 str 抛 TypeError 被 bare except 吞掉 → `_check_success` 永远返回 False
- `Orchestrator.run()` 的 `except Exception as e:` 行被误删，留下引用未定义 `e` 的死代码

### 工具链

- 新增 [uv](https://docs.astral.sh/uv/) 支持（`uv venv` + `uv pip install`）
- `pyproject.toml`：
  - `[tool.ruff.lint]` 迁移（消除 deprecated 警告）
  - `[tool.coverage.run]` omit `main.py`（CLI 入口）
  - `[tool.coverage.report]` `fail_under = 60`、`show_missing = true`
- `.github/workflows/ci.yml`：启用 lint job + 覆盖率门槛

### 不变的部分

- 投递行为与 v1.0 完全一致（characterization 测试全 green 证明）
- CLI 接口不变（`python -m src.main start` / `stats` / `sessions` / `account`）
- 配置不变（`.env` / `accounts/` 多账户）
- `simulation/*` 仍依赖 Playwright `Page`（Mouse 抽象超出 v2.0 范围，留待 v2.1）

## [upstream-v0.1.0] — 2026-07-20 — 初始版本

- 自动识别 Quick Apply / 快速申请按钮
- 自动跳过普通申请（跳外部网站的职位）
- 自动处理 Cover Letter 页面（选择 "Don't include a cover letter"）
- 多账户隔离支持（独立浏览器 profile / cookies / 数据库记录）
- 完整的反检测策略（指纹伪装 + Bezier 鼠标 + 拟人打字 + 时序随机化）
- 投递历史记录和统计（SQLite）
