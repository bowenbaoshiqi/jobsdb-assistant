"""
CLI entry point

Provides command line interface for controlling the job application assistant.
"""

import json
import os
import shutil
from collections import Counter
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config.settings import get_config
from src.accounts.registry import Account, AccountRegistry
from src.doctor import CheckStatus, run_checks
from src.jobsdb.search import normalize_keyword
from src.monitor.logger import configure_logger
from src.orchestrator import Orchestrator
from src.storage.database import Database
from src.version import __version__

app = typer.Typer(
    name="jobsdb-assistant",
    help="JobsDB 简历智能投递助手",
    no_args_is_help=True,
    invoke_without_command=True,
)

account_app = typer.Typer(help="多账户管理器")
app.add_typer(account_app, name="account")
workflow_app = typer.Typer(help="候选人画像与职位评分工作流")
app.add_typer(workflow_app, name="workflow")
dashboard_app = typer.Typer(help="本地职位审核 Dashboard")
app.add_typer(dashboard_app, name="dashboard")
agent_app = typer.Typer(help="统一 Agent 工作协议")
app.add_typer(agent_app, name="agent")

console = Console()


def _build_candidate_evaluation_workflow():
    from src.application.runtime import build_workflow

    return build_workflow()


def _build_material_generation_service():
    from src.application.runtime import build_material_generation_service

    return build_material_generation_service()


def _build_agent_work_coordinator():
    from src.application.agent_runtime import build_agent_work_coordinator

    return build_agent_work_coordinator()


def _print_json(payload: dict) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))


@agent_app.command("start")
def agent_start(
    port: int = typer.Option(8765, "--port", min=1, max=65535),
    source: list[Path] = typer.Option([], "--source"),  # noqa: B008
    update_profile: bool = typer.Option(False, "--update-profile"),
) -> None:
    """启动或恢复一个仅暴露不透明工作 ID 的 Agent 会话。"""
    now = datetime.now(UTC)
    coordinator = _build_agent_work_coordinator()
    session = coordinator.start(now=now)
    coordinator.prepare_profile(
        source_documents=tuple(str(path) for path in source),
        update=update_profile,
        now=now,
    )
    _print_json({
        "protocol_version": 1,
        "state": "active",
        "session": session.id,
        "dashboard_url": f"http://127.0.0.1:{port}",
    })


@agent_app.command("next")
def agent_next(
    session: str = typer.Option(..., "--session"),
    wait: int = typer.Option(30, "--wait", min=0, max=30),
) -> None:
    """等待并领取唯一的下一项 Agent 工作。"""
    result = _build_agent_work_coordinator().next(
        session,
        wait_seconds=wait,
    )
    _print_json(result.model_dump(mode="json"))


@agent_app.command("submit")
def agent_submit(
    session: str = typer.Option(..., "--session"),
    work_id: str = typer.Option(..., "--work-id"),
    result: Path = typer.Option(..., "--result"),  # noqa: B008
) -> None:
    """按不透明 work_id 校验并提交 Agent 结果。"""
    record = _build_agent_work_coordinator().submit(
        session_id=session,
        work_id=work_id,
        result_path=result,
        now=datetime.now(UTC),
    )
    _print_json({
        "protocol_version": 1,
        "state": record.status.value,
        "work_id": record.id,
        "result_hash": record.result_hash,
    })


@agent_app.command("fail")
def agent_fail(
    session: str = typer.Option(..., "--session"),
    work_id: str = typer.Option(..., "--work-id"),
    error: Path = typer.Option(..., "--error"),  # noqa: B008
) -> None:
    """记录一项隔离失败并允许队列继续。"""
    record = _build_agent_work_coordinator().fail(
        session_id=session,
        work_id=work_id,
        error_message=error.read_text(encoding="utf-8"),
        now=datetime.now(UTC),
    )
    _print_json({
        "protocol_version": 1,
        "state": record.status.value,
        "work_id": record.id,
    })


@agent_app.command("stop")
def agent_stop(
    session: str = typer.Option(..., "--session"),
) -> None:
    """停止 Agent 会话并释放未完成的工作租约。"""
    record = _build_agent_work_coordinator().stop(
        session,
        now=datetime.now(UTC),
    )
    _print_json({
        "protocol_version": 1,
        "state": record.status.value,
        "session": record.id,
    })


def _onboarding_payload(outcome) -> dict:
    return {
        "status": outcome.status.value,
        "profile_version": outcome.profile_version,
        "task_id": outcome.task_id,
        "proposal_id": outcome.proposal_id,
        "questions": [
            {
                "dimension": item.dimension.value,
                "prompt": item.prompt,
                "optional": item.optional,
            }
            for item in outcome.questions
        ],
    }


@workflow_app.command("profile-prepare")
def workflow_profile_prepare(
    run_id: str = typer.Option(..., "--run-id"),
    source: list[Path] = typer.Option([], "--source"),  # noqa: B008
    update: bool = typer.Option(False, "--update"),
) -> None:
    """复用现有画像，或创建一个受控画像 AI 任务。"""
    workflow = _build_candidate_evaluation_workflow()
    outcome = workflow.prepare_profile(
        run_id,
        [str(path) for path in source],
        update=update,
    )
    _print_json(_onboarding_payload(outcome))


@workflow_app.command("profile-submit")
def workflow_profile_submit(
    run_id: str = typer.Option(..., "--run-id"),
    task_id: str = typer.Option(..., "--task-id"),
    result: Path = typer.Option(..., "--result"),  # noqa: B008
) -> None:
    """校验 Agent 返回的画像问题或提案。"""
    payload = json.loads(result.read_text(encoding="utf-8"))
    outcome = _build_candidate_evaluation_workflow().submit_profile_result(
        run_id,
        task_id,
        payload,
    )
    _print_json(_onboarding_payload(outcome))


@workflow_app.command("profile-answers")
def workflow_profile_answers(
    run_id: str = typer.Option(..., "--run-id"),
    answers: Path = typer.Option(..., "--answers"),  # noqa: B008
    source: list[Path] = typer.Option([], "--source"),  # noqa: B008
) -> None:
    """提交补充访谈答案并创建下一画像任务。"""
    payload = json.loads(answers.read_text(encoding="utf-8"))
    outcome = _build_candidate_evaluation_workflow().submit_profile_answers(
        run_id,
        [str(path) for path in source],
        payload,
    )
    _print_json(_onboarding_payload(outcome))


@workflow_app.command("profile-confirm")
def workflow_profile_confirm(
    proposal_id: str = typer.Option(..., "--proposal-id"),
) -> None:
    """显式确认画像提案并创建不可变版本。"""
    profile = _build_candidate_evaluation_workflow().confirm_profile(
        proposal_id,
        confirmed_at=datetime.now(UTC),
    )
    _print_json({
        "status": "confirmed",
        "profile_id": profile.id,
        "profile_version": profile.version,
    })


@workflow_app.command("evaluation-prepare")
def workflow_evaluation_prepare(
    run_id: str = typer.Option(..., "--run-id"),
) -> None:
    """为当前未缓存 JobsDB JD 创建原生评分任务。"""
    plan = _build_candidate_evaluation_workflow().prepare_evaluations(run_id)
    _print_json({
        "cached": len(plan.cached),
        "pending": [
            {
                "snapshot_id": item.snapshot_id,
                "task_id": item.task.task_id,
            }
            for item in plan.pending
        ],
    })


@workflow_app.command("evaluation-submit")
def workflow_evaluation_submit(
    task_id: str = typer.Option(..., "--task-id"),
    result: Path = typer.Option(..., "--result"),  # noqa: B008
) -> None:
    """校验并保存一个 career-ops 原生评分结果。"""
    payload = json.loads(result.read_text(encoding="utf-8"))
    evaluation = (
        _build_candidate_evaluation_workflow().submit_evaluation_result(
            task_id,
            payload,
        )
    )
    from src.dashboard.evaluation_progress import (
        EvaluationProgressStore,
        EvaluationTaskStatus,
    )

    progress_store = EvaluationProgressStore(
        Path("workspace/dashboard/evaluation-progress.json")
    )
    with suppress(KeyError):
        progress_store.mark(task_id, EvaluationTaskStatus.COMPLETED)
        if progress_store.get().status == "completed":
            from src.storage.job_batch_repository import (
                JobBatchRepository,
            )

            database = Database(get_config().storage.database_path)
            current_batch = JobBatchRepository(database).current()
            if current_batch is not None:
                JobBatchRepository(database).mark_scored(
                    current_batch.id
                )
    _print_json({
        "status": "saved",
        "evaluation_id": evaluation.id,
        "snapshot_id": evaluation.job_snapshot_id,
        "overall_score": evaluation.overall_score,
    })


@workflow_app.command("evaluation-next")
def workflow_evaluation_next() -> None:
    """领取当前 Dashboard 批次的下一项评分任务。"""
    from src.dashboard.evaluation_progress import EvaluationProgressStore

    task_id = EvaluationProgressStore(
        Path("workspace/dashboard/evaluation-progress.json")
    ).claim_next()
    if task_id is None:
        _print_json({"status": "drained", "task_id": None})
        return
    _print_json({
        "status": "claimed",
        "task_id": task_id,
        "task_path": f"workspace/ai-tasks/{task_id}/task.json",
    })


@workflow_app.command("report")
def workflow_report() -> None:
    """输出当前画像版本对应的完整评分报告。"""
    typer.echo(_build_candidate_evaluation_workflow().report())


def _material_task_payload(task) -> dict:
    return {
        "task_id": task.id,
        "batch_id": task.batch_id,
        "job_id": task.job_id,
        "material_version": task.target_version,
        "status": task.status.value,
        "error_message": task.error_message,
    }


@workflow_app.command("material-pending")
def workflow_material_pending() -> None:
    """列出所有等待当前 Agent 处理的材料任务。"""
    service = _build_material_generation_service()
    _print_json({
        "pending": [
            _material_task_payload(item)
            for item in service.repository.list_pending()
        ]
    })


@workflow_app.command("material-submit")
def workflow_material_submit(
    task_id: str = typer.Option(..., "--task-id"),
    result: Path = typer.Option(..., "--result"),  # noqa: B008
) -> None:
    """校验并保存一个职位的定制简历和求职信结果。"""
    service = _build_material_generation_service()
    payload = json.loads(result.read_text(encoding="utf-8"))
    package = service.submit(
        service.load_pending(task_id),
        payload,
        completed_at=datetime.now(UTC),
    )
    _print_json({
        "status": "saved",
        "package_id": package.id,
        "job_id": package.job_id,
        "material_version": package.version,
        "review_status": package.review_status.value,
    })


@workflow_app.command("material-progress")
def workflow_material_progress(
    batch_id: str = typer.Option(..., "--batch-id"),
) -> None:
    """输出一个材料批次的稳定任务进度。"""
    tasks = (
        _build_material_generation_service()
        .repository.list_batch(batch_id)
    )
    counts = Counter(item.status.value for item in tasks)
    _print_json({
        "batch_id": batch_id,
        "total": len(tasks),
        "counts": dict(sorted(counts.items())),
        "tasks": [_material_task_payload(item) for item in tasks],
    })


@dashboard_app.command("doctor")
def dashboard_doctor(
    port: int = typer.Option(8765, "--port", min=1, max=65535),
) -> None:
    """检查 Dashboard 依赖、数据库和本地端口。"""
    from src.dashboard.cli import CheckState, run_dashboard_doctor

    results = run_dashboard_doctor(
        database_path=get_config().storage.database_path,
        port=port,
    )
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    for item in results:
        table.add_row(item.name, item.state.value, item.detail)
    console.print(table)
    if any(item.state is CheckState.FAIL for item in results):
        raise typer.Exit(code=1)


@dashboard_app.command("start")
def dashboard_start(
    port: int = typer.Option(8765, "--port", min=1, max=65535),
    no_browser: bool = typer.Option(False, "--no-browser"),
) -> None:
    """启动仅监听 127.0.0.1 的本地审核 Dashboard。"""
    from src.dashboard.cli import start_dashboard

    try:
        start_dashboard(port=port, open_browser=not no_browser)
    except RuntimeError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(code=1) from exc


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="显示详细日志"),
    version: bool = typer.Option(
        False,
        "--version",
        is_eager=True,
        help="显示版本并退出",
    ),
):
    """JobsDB Assistant."""
    if version:
        console.print(f"jobsdb-assistant {__version__}", markup=False)
        raise typer.Exit()

    config = get_config()

    # Configure logs
    log_level = "DEBUG" if verbose else config.monitoring.log_level
    configure_logger(
        log_level=log_level,
        log_file=config.monitoring.log_file,
        log_rotation=config.monitoring.log_rotation,
        log_retention=config.monitoring.log_retention,
    )


@app.command()
def doctor() -> None:
    """检查本机运行环境，不输出凭证或私有路径。"""
    results = run_checks()
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("检查项")
    table.add_column("状态")
    table.add_column("详情")
    icons = {
        CheckStatus.PASS: "[green]PASS[/green]",
        CheckStatus.WARN: "[yellow]WARN[/yellow]",
        CheckStatus.FAIL: "[red]FAIL[/red]",
    }
    for result in results:
        table.add_row(result.name, icons[result.status], result.detail)
    console.print(table)
    if any(result.status is CheckStatus.FAIL for result in results):
        raise typer.Exit(code=1)


@app.command()
def discover(
    keyword: str = typer.Option(
        ...,
        "--keyword",
        "-k",
        help="单一 JobsDB 搜索关键词（地区默认为香港）",
    ),
) -> None:
    """从公开页面发现并保存 JobsDB 香港职位，不登录、不投递。"""
    try:
        normalized_keyword = normalize_keyword(keyword)
    except ValueError as exc:
        raise typer.BadParameter(
            str(exc),
            param_hint="--keyword",
        ) from exc

    config = get_config()
    resolved = Account(
        alias="public-discovery",
        email="",
        password="",
    )

    import asyncio

    orchestrator = Orchestrator(config, account=resolved)
    report = asyncio.run(
        orchestrator.discover(normalized_keyword, limit=50)
    )
    if "error" in report:
        console.print(
            f"[bold red]Discovery failed: {report['error']}[/bold red]"
        )
        raise typer.Exit(code=1)
    _print_discovery_result(report)


@app.command()
def start(
    account: Optional[str] = typer.Option(
        None, "--account", "-a",
        help="指定账户别名"
    ),
    max_jobs: int = typer.Option(
        None, "--max-jobs", "-m",
        help="本次投递最大职位数",
    ),
    headless: bool = typer.Option(
        False, "--headless", "-h",
        help="无头模式（不显示浏览器窗口）",
    ),
    login_mode: Optional[str] = typer.Option(
        None, "--login-mode",
        help="登录模式: auto(自动填密码,需凭证) / manual(等用户手动登录,无需凭证)。"
             "覆盖 config.login.mode",
    ),
):
    """启动简历投递"""
    config = get_config()

    # 登录模式覆盖(CLI 旗标优先于 config.login.mode)— 必须在解析账户前,
    # 因为 manual 模式下 resolve_active 用 allow_placeholder 兜底(无需凭证)
    if login_mode:
        config.login.mode = login_mode  # pydantic validator 校验 auto|manual
    # manual 模式必须有头(用户要在浏览器窗口手动登录)
    if config.login.mode == "manual":
        config.browser.headless = False

    # If headless mode is specified, update the configuration
    if headless:
        config.browser.headless = True

    # 解析账户
    registry = AccountRegistry()
    # manual 模式不要求凭证:无账户时返回占位(持久化 profile 即凭证)
    resolved = registry.resolve_active(
        account,
        allow_placeholder=(config.login.mode == "manual"),
    )

    # Display startup information
    console.print(Panel.fit(
        f"[bold green]JobsDB Resume Assistant[/bold green]\n"
        f"Account: [cyan]{resolved.alias}[/cyan] ({AccountRegistry.mask_email(resolved.email)})\n"
        f"Target: {config.jobsdb.homepage_url}\n"
        f"Max jobs: {max_jobs or config.scheduler.max_applies_per_session}\n"
        f"Headless: {config.browser.headless}\n"
        f"Login mode: [yellow]{config.login.mode}[/yellow]"
        + (" (manual 需在浏览器窗口登录)" if config.login.mode == "manual" else ""),
        title="Starting",
        border_style="green",
    ))

    # Run the Orchestrator
    import asyncio

    async def run():
        orchestrator = Orchestrator(config, account=resolved, max_jobs=max_jobs)
        result = await orchestrator.run()
        return result

    try:
        result = asyncio.run(run())

        # Display results
        if "error" in result:
            console.print(f"[bold red]Error: {result['error']}[/bold red]")
        else:
            _print_result_table(result)

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"[bold red]Fatal error: {e}[/bold red]")
        raise


def _print_discovery_result(report: dict) -> None:
    """Print a discovery summary without rendering JD content."""
    console.print(Panel.fit(
        f"[bold blue]JobsDB Discovery[/bold blue]\n"
        f"Keyword: [cyan]{report['keyword']}[/cyan]\n"
        f"Found: {report['found']} · Captured: {report['captured']}",
        border_style="blue",
    ))

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Result")
    table.add_column("Count", justify="right")
    table.add_row("New", str(report["new"]))
    table.add_row("Unchanged", str(report["unchanged"]))
    table.add_row("Changed", str(report["changed"]))
    table.add_row(
        "Quick Apply",
        str(report["apply_types"]["quick_apply"]),
    )
    table.add_row("Apply", str(report["apply_types"]["apply"]))
    table.add_row("Unknown", str(report["apply_types"]["unknown"]))
    table.add_row("Failed details", str(len(report["failures"])))
    console.print(table)


@app.command()
def stats(
    days: int = typer.Option(
        7, "--days", "-d",
        help="统计最近多少天",
    ),
    account: Optional[str] = typer.Option(
        None, "--account", "-a",
        help="按账户过滤",
    ),
):
    """查看投递统计"""
    config = get_config()
    db = Database(config.storage.database_path)
    if account:
        db.set_account(account)

    stats_data = db.get_stats(days, account=account)

    console.print(Panel.fit(
        f"[bold blue]投递统计（最近 {days} 天）[/bold blue]",
        border_style="blue",
    ))

    # Total count
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("指标", style="dim")
    table.add_column("数值", justify="right")

    table.add_row("总投递数", str(stats_data["total"]))
    table.add_row("成功数", str(stats_data["success"]))
    table.add_row("失败数", str(stats_data["failed"]))
    table.add_row("成功率", f"{stats_data['success_rate']:.1f}%")

    console.print(table)

    # Daily details
    if stats_data["daily_breakdown"]:
        console.print("\n[bold]每日明细:[/bold]")
        daily_table = Table(show_header=True, header_style="bold cyan")
        daily_table.add_column("日期")
        daily_table.add_column("投递数", justify="right")
        daily_table.add_column("成功数", justify="right")

        for day in stats_data["daily_breakdown"]:
            daily_table.add_row(
                day["date"],
                str(day["count"]),
                str(day["success"]),
            )

        console.print(daily_table)


@app.command()
def sessions(
    limit: int = typer.Option(
        10, "--limit", "-l",
        help="显示最近多少条会话",
    ),
    account: Optional[str] = typer.Option(
        None, "--account", "-a",
        help="按账户过滤",
    ),
):
    """查看会话历史"""
    config = get_config()
    db = Database(config.storage.database_path)
    if account:
        db.set_account(account)

    sessions_data = db.get_recent_sessions(limit, account=account)

    console.print(Panel.fit(
        f"[bold blue]会话历史（最近 {limit} 条）[/bold blue]",
        border_style="blue",
    ))

    if not sessions_data:
        console.print("[dim]暂无会话记录[/dim]")
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("会话ID", style="dim")
    table.add_column("开始时间")
    table.add_column("结束时间")
    table.add_column("状态", justify="center")
    table.add_column("投递数", justify="right")
    table.add_column("成功", justify="right")
    table.add_column("失败", justify="right")
    table.add_column("账户", justify="center")

    for session in sessions_data:
        table.add_row(
            session["id"],
            session["started_at"],
            session.get("ended_at", "—") or "—",
            session["status"],
            str(session.get("jobs_attempted", 0)),
            str(session.get("jobs_succeeded", 0)),
            str(session.get("jobs_failed", 0)),
            session.get("account_id", "default"),
        )

    console.print(table)


@app.command()
def validate():
    """验证配置"""
    config = get_config()

    console.print(Panel.fit(
        "[bold yellow]配置验证[/bold yellow]",
        border_style="yellow",
    ))

    # Check jobsDB configuration
    if not config.jobsdb.email or not config.jobsdb.password:
        console.print("[red]✗[/red] JobsDB email 或 password 未配置")
        console.print("  请在 .env 文件中设置 JOBSDB_EMAIL 和 JOBSDB_PASSWORD")
    else:
        console.print(f"[green]✓[/green] JobsDB email: {config.jobsdb.email[:3]}***")

    # Check data directory
    import os
    dirs_to_check = [
        ("数据目录", "./data"),
        ("浏览器 profile", config.browser.user_data_dir),
        ("数据库", config.storage.database_path),
    ]

    for name, path in dirs_to_check:
        if os.path.exists(path) or os.path.exists(os.path.dirname(path)):
            console.print(f"[green]✓[/green] {name}: {path}")
        else:
            console.print(f"[red]✗[/red] {name}: {path} (不存在)")

    # Check accounts
    registry = AccountRegistry()
    accounts = registry.list_all()
    if accounts:
        console.print("\n[bold]已配置账户:[/bold]")
        for acc in accounts:
            console.print(f"  [green]✓[/green] {acc.alias} ({AccountRegistry.mask_email(acc.email)})")  # noqa: E501
    else:
        console.print("\n[dim]未在 accounts/ 下注册额外账户[/dim]")

    console.print("\n[dim]提示：运行 `python -m src.main start` 开始投递[/dim]")
    console.print("[dim]提示：运行 `python -m src.main account add <alias>` 添加账户[/dim]")


@app.command()
def reset(
    profile: bool = typer.Option(
        False, "--profile", "-p",
        help="重置浏览器 profile",
    ),
    database: bool = typer.Option(
        False, "--database", "-d",
        help="重置数据库",
    ),
    all_data: bool = typer.Option(
        False, "--all", "-a",
        help="重置所有数据（包括 profile 和数据库）",
    ),
    account: Optional[str] = typer.Option(
        None, "--account",
        help="仅重置指定账户的 profile",
    ),
):
    """重置数据（危险操作！）"""

    if all_data:
        profile = True
        database = True

    if not profile and not database:
        console.print("[yellow]请指定要重置的内容：--profile / --database / --all[/yellow]")
        return

    if all_data:
        confirm = typer.confirm("确定要重置所有数据吗？此操作不可恢复！")
    else:
        confirm = typer.confirm("确定要重置选中的数据吗？")

    if not confirm:
        console.print("[dim]已取消[/dim]")
        return

    config = get_config()

    if profile:
        if account:
            profile_dir = Path(config.browser.user_data_dir) / account
        else:
            profile_dir = Path(config.browser.user_data_dir)
        if profile_dir.exists():
            shutil.rmtree(profile_dir)
            console.print(f"[green]✓[/green] 已清除浏览器 profile: {profile_dir}")

    if database:
        db_path = config.storage.database_path
        if os.path.exists(db_path):
            os.remove(db_path)
            console.print(f"[green]✓[/green] 已清除数据库: {db_path}")

    console.print("[green]重置完成[/green]")


# ---- Account subcommand group ----

@account_app.command("list")
def account_list():
    """List all accounts"""
    registry = AccountRegistry()
    accounts = registry.list_all()

    console.print(Panel.fit(
        f"[bold blue]账户列表（共 {len(accounts)} 个）[/bold blue]",
        border_style="blue",
    ))

    if not accounts:
        console.print("[dim]暂无注册账户[/dim]")
        console.print("[dim]请使用 `python -m src.main account add <alias>` 添加[/dim]")
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("别名")
    table.add_column("邮箱")
    table.add_column("活跃", justify="center")

    active_alias = registry.get_active_alias()
    for acc in accounts:
        is_active = "✓" if acc.alias == active_alias else ""
        masked_email = AccountRegistry.mask_email(acc.email)
        table.add_row(acc.alias, masked_email, is_active)

    console.print(table)


@account_app.command("add")
def account_add(
    alias: str = typer.Argument(..., help="账户别名（唯一）"),
    email: str = typer.Option(..., "--email", "-e", help="JobsDB 邮箱"),
    password: Optional[str] = typer.Option(
        None, "--password", "-p",
        help="密码（不传则交互式输入）",
    ),
) -> None:
    """Add a new account"""
    registry = AccountRegistry()

    # Check if duplicate
    if registry.get(alias):
        console.print(f"[red]✗[/red] 账户 {alias} 已存在")
        raise typer.Exit(code=1)

    if not password:
        password = typer.prompt("请输入密码", hide_input=True)

    account = Account(alias=alias, email=email, password=password)
    registry.save(account)
    console.print(f"[green]✓[/green] 账户 {alias} 已添加")


@account_app.command("remove")
def account_remove(
    alias: str = typer.Argument(..., help="账户别名"),
    force: bool = typer.Option(False, "--force", "-f", help="强制删除，不确认"),
) -> None:
    """Delete an account"""
    registry = AccountRegistry()

    if not registry.get(alias):
        console.print(f"[red]✗[/red] 账户 {alias} 不存在")
        raise typer.Exit(code=1)

    if not force:
        confirmed = typer.confirm(f"确定删除账户 {alias} 吗？此操作不可恢复！")
        if not confirmed:
            console.print("[dim]已取消[/dim]")
            return

    registry.delete(alias)
    console.print(f"[green]✓[/green] 已删除账户 {alias}")


@account_app.command("use")
def account_use(
    alias: str = typer.Argument(..., help="账户别名"),
) -> None:
    """Switch active account"""
    registry = AccountRegistry()
    try:
        registry.set_active(alias)
        console.print(f"[green]✓[/green] 活跃账户已切换为 {alias}")
    except ValueError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(code=1) from e


@account_app.command("show")
def account_show() -> None:
    """Show current active account"""
    registry = AccountRegistry()
    active = registry.get_active_alias()

    if not active:
        # Try to infer from .env
        config = get_config()
        if config.jobsdb.email:
            console.print(f"当前使用 .env 默认账户: {AccountRegistry.mask_email(config.jobsdb.email)}")  # noqa: E501
        else:
            console.print("[dim]未指定活跃账户[/dim]")
        return

    acc = registry.get(active)
    if not acc:
        console.print(f"[yellow]活跃账户 {active} 已被删除[/yellow]")
        return

    console.print(Panel.fit(
        f"[bold blue]当前活跃账户[/bold blue]\n"
        f"别名: {acc.alias}\n"
        f"邮箱: {AccountRegistry.mask_email(acc.email)}",
        border_style="blue",
    ))


def _print_result_table(result: dict) -> None:
    """Print the result table"""
    table = Table(show_header=True, header_style="bold green")
    table.add_column("指标")
    table.add_column("数值", justify="right")

    table.add_row("处理职位数", str(result.get("total", 0)))
    table.add_row("投递成功", str(result.get("success", 0)))
    table.add_row("投递失败", str(result.get("failed", 0)))
    table.add_row("跳过（已投递）", str(result.get("skipped", 0)))
    table.add_row("成功率", f"{result.get('success_rate', 0)}%")

    console.print(Panel(table, title="投递结果", border_style="green"))


if __name__ == "__main__":
    app()
