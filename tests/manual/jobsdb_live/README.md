# JobsDB 真实网站人工诊断脚本

这里的脚本用于人工检查 JobsDB HK 真实页面的 DOM 和 Quick Apply
向导。它们不是自动化测试，不会被常规 `pytest` 或 CI 执行。

## 安全边界

- 使用 `data/browser_profile/` 中现有的真实登录状态。
- 会打开真实职位并可能点击 Quick Apply 和 Continue。
- 当前脚本不会点击最终 Submit。
- 生成的截图和 HTML 保存在已忽略的 `data/` 下，可能包含个人资料，
  不得提交到 public 仓库。
- 默认职位 ID 可能过期；运行前应传入一个当前有效的测试职位 ID。

## 脚本用途

- `probe_apply_buttons.py`：诊断职位详情页 Apply/Quick Apply 按钮选择器。
- `probe_apply_wizard.py`：人工走到 Review 页，但不提交。
- `probe_cover_letter.py`：检查求职信步骤的 DOM、截图和 HTML。
- `probe_profile_stuck.py`：排查 Profile 页 Continue 卡住的原因。
- `probe_cover_click.py`：专项检查“不附求职信”和 Continue 行为。

## 运行方式

从项目根目录执行，例如：

```bash
uv run python tests/manual/jobsdb_live/probe_apply_wizard.py JOB_ID
uv run python tests/manual/jobsdb_live/probe_profile_stuck.py JOB_ID
```

运行前必须确认目标职位仅用于人工诊断，并在浏览器到达 Review 页后停止。
这些脚本可能推进真实申请向导，只能由了解风险的开发者在前台观察运行；
任何情况下都不得点击最终 Submit。
