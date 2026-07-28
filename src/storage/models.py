from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class ApplyStatus(str, Enum):
    """投递状态"""
    QUEUED = "queued"           # 排队中
    PROCESSING = "processing"   # 处理中
    SUBMITTED = "submitted"     # 已提交
    FAILED = "failed"           # 失败
    SKIPPED = "skipped"         # 跳过（已投递过）
    CAPTCHA = "captcha"         # 遇到验证码
    READY_FOR_REVIEW = "ready_for_review"


class SessionStatus(str, Enum):
    """会话状态"""
    ACTIVE = "active"
    COMPLETED = "completed"
    ABORTED = "aborted"


@dataclass
class JobListing:
    """职位信息"""
    id: str                      # JobsDB 职位 ID
    title: str                   # 职位标题
    company: str                 # 公司名称
    location: Optional[str] = None
    salary: Optional[str] = None
    url: Optional[str] = None
    posted_date: Optional[str] = None
    job_type: Optional[str] = None  # 全职/兼职/合同
    scraped_at: Optional[datetime] = None

    def __post_init__(self):
        if self.scraped_at is None:
            self.scraped_at = datetime.now()


@dataclass
class ApplyResult:
    """投递结果"""
    status: ApplyStatus
    job_id: Optional[str] = None
    error_message: Optional[str] = None
    reason: Optional[str] = None  # 跳过时："already_applied" 等
    applied_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    screenshot_path: Optional[str] = None

    def __post_init__(self):
        if self.applied_at is None:
            self.applied_at = datetime.now()

    def is_success(self) -> bool:
        return self.status == ApplyStatus.SUBMITTED

    def is_final(self) -> bool:
        """是否为终态（不需要重试的）"""
        return self.status in (
            ApplyStatus.SUBMITTED,
            ApplyStatus.FAILED,
            ApplyStatus.SKIPPED,
            ApplyStatus.CAPTCHA,
        )


@dataclass
class SessionRecord:
    """会话记录"""
    id: str                      # UUID
    started_at: datetime
    ended_at: Optional[datetime] = None
    jobs_attempted: int = 0
    jobs_succeeded: int = 0
    jobs_failed: int = 0
    status: SessionStatus = SessionStatus.ACTIVE
    notes: Optional[str] = None
