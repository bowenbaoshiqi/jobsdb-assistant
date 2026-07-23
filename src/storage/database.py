import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from loguru import logger

from src.storage.migrations import Migration, MigrationRunner
from src.storage.models import (
    ApplyResult,
    ApplyStatus,
    JobListing,
    SessionRecord,
    SessionStatus,
)


def _mark_legacy_schema(_conn: sqlite3.Connection) -> None:
    """Version marker: legacy tables are created by Database._init_tables."""


class Database:
    """SQLite 数据库操作（多账户隔离）"""

    def __init__(self, db_path: str = "./data/jobsdb.db"):
        self.db_path = db_path
        self.account_alias: Optional[str] = None
        self._init_tables()
        MigrationRunner(self.db_path).apply(
            [Migration(1, "legacy v2 schema baseline", _mark_legacy_schema)]
        )

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def set_account(self, alias: str) -> None:
        """设置当前数据库操作对应的账户别名"""
        self.account_alias = alias

    def _migrate_add_account_id(self, conn, table: str) -> None:
        """为现有表添加 account_id 列（向后兼容迁移）"""
        try:
            cursor = conn.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in cursor.fetchall()]
            if "account_id" not in columns:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN account_id TEXT NOT NULL DEFAULT 'default'"
                )
                logger.info(f"迁移：为 {table} 添加 account_id 列")
        except Exception as e:
            logger.warning(f"迁移 {table} 失败（可能已存在）: {e}")

    def _init_tables(self) -> None:
        """初始化数据库表并执行列迁移"""
        with self._connect() as conn:
            # 职位信息表（共享，不需要 account_id）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT,
                    salary TEXT,
                    url TEXT NOT NULL,
                    posted_date TEXT,
                    job_type TEXT,
                    scraped_at TEXT NOT NULL
                )
            """)

            # 投递记录表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES jobs(id),
                    status TEXT NOT NULL,
                    attempt_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    reason TEXT,
                    applied_at TEXT,
                    session_id TEXT NOT NULL,
                    duration_seconds REAL,
                    screenshot_path TEXT,
                    account_id TEXT NOT NULL DEFAULT 'default'
                )
            """)
            self._migrate_add_account_id(conn, "applications")

            # 会话表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    jobs_attempted INTEGER DEFAULT 0,
                    jobs_succeeded INTEGER DEFAULT 0,
                    jobs_failed INTEGER DEFAULT 0,
                    status TEXT NOT NULL,
                    notes TEXT,
                    account_id TEXT NOT NULL DEFAULT 'default'
                )
            """)
            self._migrate_add_account_id(conn, "sessions")

            # 频率限制日志
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rate_limit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    delay_seconds REAL,
                    account_id TEXT NOT NULL DEFAULT 'default'
                )
            """)
            self._migrate_add_account_id(conn, "rate_limit_log")

            # 验证码事件表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS captcha_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    page_url TEXT NOT NULL,
                    resolution TEXT,
                    screenshot_path TEXT,
                    account_id TEXT NOT NULL DEFAULT 'default'
                )
            """)
            self._migrate_add_account_id(conn, "captcha_events")

            # 创建索引
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_applications_job_id
                ON applications(job_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_applications_session_id
                ON applications(session_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_applications_status
                ON applications(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_applications_account_id
                ON applications(account_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_account_id
                ON sessions(account_id)
            """)

    # ---- account 条件辅助 ----

    def _account_filter(self) -> tuple:
        """返回 (WHERE子句片段, 参数)"""
        alias = self.account_alias or "default"
        return ("account_id = ?", alias)

    # ---- Job 操作 ----

    def save_job(self, job: JobListing) -> None:
        """保存或更新职位信息"""
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO jobs
                (id, title, company, location, salary, url, posted_date, job_type, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.id, job.title, job.company, job.location,
                job.salary, job.url, job.posted_date, job.job_type,
                job.scraped_at.isoformat() if job.scraped_at else datetime.now().isoformat(),
            ))

    def get_job(self, job_id: str) -> Optional[JobListing]:
        """获取职位信息"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_job(row)

    def job_exists(self, job_id: str) -> bool:
        """检查职位是否存在"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            return row is not None

    def get_applied_job_ids(self) -> list[str]:
        """获取已投递过的职位 ID 列表"""
        where_clause, account_id = self._account_filter()
        with self._connect() as conn:
            rows = conn.execute(f"""
                SELECT DISTINCT job_id FROM applications
                WHERE status IN (?, ?) AND {where_clause}
            """, (ApplyStatus.SUBMITTED.value, ApplyStatus.PROCESSING.value, account_id)).fetchall()
            return [row["job_id"] for row in rows]

    # ---- Application 操作 ----

    def record_application(self, app: ApplyResult, session_id: str) -> None:
        """记录投递结果"""
        _, account_id = self._account_filter()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO applications
                (job_id, status, error_message, reason, applied_at,
                 session_id, duration_seconds, screenshot_path, account_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                app.job_id, app.status.value, app.error_message,
                app.reason,
                app.applied_at.isoformat() if app.applied_at else datetime.now().isoformat(),
                session_id, app.duration_seconds, app.screenshot_path,
                account_id,
            ))

    def get_applications_by_session(self, session_id: str) -> list[dict]:
        """获取某会话的所有投递记录"""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM applications WHERE session_id = ?
                ORDER BY applied_at DESC
            """, (session_id,)).fetchall()
            return [dict(row) for row in rows]

    def get_application_count_today(self) -> int:
        """获取今天投递的数量"""
        today = datetime.now().strftime("%Y-%m-%d")
        where_clause, account_id = self._account_filter()
        with self._connect() as conn:
            row = conn.execute(f"""
                SELECT COUNT(*) as count FROM applications
                WHERE applied_at >= ? AND status = ? AND {where_clause}
            """, (f"{today}T00:00:00", ApplyStatus.SUBMITTED.value, account_id)).fetchone()
            return row["count"] if row else 0

    def get_application_count_last_hour(self) -> int:
        """获取最近1小时投递的数量"""
        from datetime import timedelta
        one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
        where_clause, account_id = self._account_filter()
        with self._connect() as conn:
            row = conn.execute(f"""
                SELECT COUNT(*) as count FROM applications
                WHERE applied_at >= ? AND status = ? AND {where_clause}
            """, (one_hour_ago, ApplyStatus.SUBMITTED.value, account_id)).fetchone()
            return row["count"] if row else 0

    # ---- Session 操作 ----

    def start_session(self, session: SessionRecord) -> None:
        """开始新会话"""
        _, account_id = self._account_filter()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO sessions (id, started_at, status, account_id)
                VALUES (?, ?, ?, ?)
            """, (
                session.id,
                session.started_at.isoformat(),
                session.status.value,
                account_id,
            ))

    def end_session(self, session_id: str, status: SessionStatus,
                    notes: Optional[str] = None) -> None:
        """结束会话"""
        with self._connect() as conn:
            # 统计会话数据
            stats = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as success,
                    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as failed
                FROM applications WHERE session_id = ?
            """, (
                ApplyStatus.SUBMITTED.value,
                ApplyStatus.FAILED.value,
                session_id,
            )).fetchone()

            conn.execute("""
                UPDATE sessions SET
                    ended_at = ?,
                    jobs_attempted = ?,
                    jobs_succeeded = ?,
                    jobs_failed = ?,
                    status = ?,
                    notes = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                stats["total"] or 0,
                stats["success"] or 0,
                stats["failed"] or 0,
                status.value,
                notes,
                session_id,
            ))

    def get_recent_sessions(self, limit: int = 10, account: Optional[str] = None) -> list[dict]:
        """获取最近的会话（可按账户过滤）"""
        with self._connect() as conn:
            if account:
                rows = conn.execute("""
                    SELECT * FROM sessions WHERE account_id = ?
                    ORDER BY started_at DESC
                    LIMIT ?
                """, (account, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM sessions
                    ORDER BY started_at DESC
                    LIMIT ?
                """, (limit,)).fetchall()
            return [dict(row) for row in rows]

    # ---- Captcha 操作 ----

    def log_captcha_event(self, page_url: str, resolution: Optional[str] = None,
                         screenshot_path: Optional[str] = None) -> None:
        """记录验证码事件"""
        _, account_id = self._account_filter()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO captcha_events
                    (timestamp, page_url, resolution, screenshot_path, account_id)
                VALUES (?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(), page_url, resolution, screenshot_path, account_id,
            ))

    # ---- Statistics ----

    def get_stats(self, days: int = 7, account: Optional[str] = None) -> dict:
        """获取统计数据（可按账户过滤）"""
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        with self._connect() as conn:
            where_condition = "applied_at >= ?"
            params = [f"{cutoff}T00:00:00"]
            if account:
                where_condition += " AND account_id = ?"
                params.append(account)

            # 总投递数
            total = conn.execute(f"""
                SELECT COUNT(*) as count FROM applications
                WHERE {where_condition}
            """, params).fetchone()["count"]

            # 成功数
            success = conn.execute(f"""
                SELECT COUNT(*) as count FROM applications
                WHERE {where_condition} AND status = ?
            """, [*params, ApplyStatus.SUBMITTED.value]).fetchone()["count"]

            # 失败数
            failed = conn.execute(f"""
                SELECT COUNT(*) as count FROM applications
                WHERE {where_condition} AND status = ?
            """, [*params, ApplyStatus.FAILED.value]).fetchone()["count"]

            # 按日期统计
            daily = conn.execute(f"""
                SELECT
                    substr(applied_at, 1, 10) as date,
                    COUNT(*) as count,
                    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as success
                FROM applications
                WHERE {where_condition}
                GROUP BY substr(applied_at, 1, 10)
                ORDER BY date DESC
            """, [ApplyStatus.SUBMITTED.value, *params]).fetchall()

            return {
                "period_days": days,
                "total": total,
                "success": success,
                "failed": failed,
                "success_rate": (success / total * 100) if total > 0 else 0,
                "daily_breakdown": [
                    {
                        "date": row["date"],
                        "count": row["count"],
                        "success": row["success"],
                    }
                    for row in daily
                ],
            }

    # ---- Helpers ----

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> JobListing:
        """将数据库行转换为 JobListing"""
        return JobListing(
            id=row["id"],
            title=row["title"],
            company=row["company"],
            location=row["location"],
            salary=row["salary"],
            url=row["url"],
            posted_date=row["posted_date"],
            job_type=row["job_type"],
            scraped_at=datetime.fromisoformat(row["scraped_at"]),
        )
