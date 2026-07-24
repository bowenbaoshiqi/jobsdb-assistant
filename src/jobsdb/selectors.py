"""
选择器集中管理

所有 JobsDB HK 的 CSS/XPath 选择器统一放在这里。
便于维护和更新，当 JobsDB DOM 结构变化时只需修改此文件。

优先级：data-automation > class > XPath
"""

# =============================================================================
# 通用元素
# =============================================================================

# Cookie 同意弹窗
COOKIE_BANNER = '[data-automation="CookieBanner"]'
COOKIE_ACCEPT_BUTTON = 'button:has-text("Accept")'

# 弹窗/模态框关闭按钮
MODAL_CLOSE = '[data-automation="modal-close"], button[aria-label="Close"]'
POPUP_DISMISS = 'button:has-text("Not now"), button:has-text("Skip"), button:has-text("No thanks")'

# 通知授权
NOTIFICATION_PROMPT = '[data-automation="notification-prompt"]'
NOTIFICATION_NO = 'button:has-text("Not now")'

# =============================================================================
# 登录相关
# =============================================================================

# 登录页
LOGIN_LINK = 'a[href*="login"], button:has-text("Sign in")'
LOGIN_EMAIL_INPUT = 'input[type="email"], input[name="email"], input[data-automation="login-email"], input[placeholder*="Email"]'  # noqa: E501
LOGIN_PASSWORD_INPUT = 'input[type="password"], input[name="password"], input[data-automation="login-password"]'  # noqa: E501
LOGIN_SUBMIT_BUTTON = 'button[type="submit"], button:has-text("Sign in"), button:has-text("Log in")'

# 登录后标识
USER_AVATAR = '[data-automation="user-avatar"], [data-automation="account-menu"], img[alt*="profile"]'  # noqa: E501
USER_NAME = '[data-automation="user-name"], [data-automation="user-greeting"]'
LOGOUT_BUTTON = 'a[href*="logout"], button:has-text("Log out")'

# 登录异常
LOGIN_ERROR_MESSAGE = '[data-automation="login-error"], .error-message, [role="alert"]'
REAUTH_REQUIRED = 'text=Please sign in again, text=Session expired'

# =============================================================================
# 首页推荐职位
# =============================================================================

# 推荐区域
RECOMMENDED_JOBS_SECTION = 'section[data-automation="recommended-jobs"], [data-automation="job-list"]'  # noqa: E501
RECOMMENDED_JOBS_HEADER = 'h2:has-text("Recommended"), h2:has-text("Recommend")'

# 职位卡片
JOB_CARD = 'article[data-automation="job-card"], [data-automation="job-list-item"]'
JOB_CARD_TITLE = '[data-automation="job-title"], h3 a[class*="job-title"]'
JOB_CARD_COMPANY = '[data-automation="job-company"], [class*="company-name"]'
JOB_CARD_LOCATION = '[data-automation="job-location"], [class*="job-location"]'
JOB_CARD_SALARY = '[data-automation="job-salary"], [class*="salary"]'
JOB_CARD_DATE = '[data-automation="job-date"], [class*="listing-date"]'
JOB_CARD_LINK = 'a[href*="/job/"]'

# 职位列表
JOB_LIST_CONTAINER = '[data-automation="job-list"], [class*="job-list"]'
LOAD_MORE_BUTTON = 'button:has-text("Load more"), [data-automation="load-more"]'
NEXT_PAGE_BUTTON = 'a[rel="next"], button:has-text("Next")'

# =============================================================================
# 职位详情页
# =============================================================================

# 职位标题和公司
JOB_DETAIL_TITLE = 'h1[data-automation="job-detail-title"], h1[class*="job-title"]'
JOB_DETAIL_COMPANY = (
    '[data-automation="advertiser-name"], '
    '[data-automation="job-detail-company"], '
    '[class*="company-detail"]'
)
JOB_DETAIL_LOCATION = '[data-automation="job-detail-location"], [class*="job-location"]'
JOB_DETAIL_SALARY = '[data-automation="job-detail-salary"], [class*="salary-detail"]'

# 职位描述
JOB_DESCRIPTION = (
    '[data-automation="jobAdDetails"], '
    '[data-automation="job-description"], '
    '[class*="job-description"]'
)
JOB_REQUIREMENTS = '[data-automation="job-requirements"], [class*="job-requirements"]'

# 申请按钮（多种变体）
APPLY_BUTTON = 'button[data-automation="apply-button"], a[data-automation="apply-button"]'
EASY_APPLY_BUTTON = 'button[data-automation="easy-apply"], button:has-text("Easy Apply")'
QUICK_APPLY_BUTTON = 'button:has-text("Quick Apply"), button[data-automation="quick-apply"]'
JOB_DETAIL_APPLY_LINK = 'a[data-automation="job-detail-apply"]'
APPLY_NOW_BUTTON = 'button:has-text("Apply now"), a:has-text("Apply now")'

# 所有可能的申请按钮（按优先级排序）
ALL_APPLY_BUTTONS = [
    JOB_DETAIL_APPLY_LINK,
    QUICK_APPLY_BUTTON,
    EASY_APPLY_BUTTON,
    APPLY_NOW_BUTTON,
    APPLY_BUTTON,
]

# 已申请标记
ALREADY_APPLIED_BADGE = '[data-automation="applied-badge"], span:has-text("Applied"), span:has-text("已申请")'  # noqa: E501

# =============================================================================
# 申请表单
# =============================================================================

# 模态框/申请表单
APPLY_MODAL = '[data-automation="apply-modal"], [role="dialog"]'
APPLY_FORM = 'form[data-automation="application-form"], [class*="application-form"]'

# 步骤指示器（多步表单）
STEP_INDICATOR = '[data-automation="step-indicator"], [class*="step-progress"]'
STEP_CURRENT = '[data-automation="step-current"], [class*="current-step"]'
STEP_TOTAL = '[data-automation="step-total"]'

# 简历选择
RESUME_SELECTION = '[data-automation="resume-selection"]'
DEFAULT_RESUME_RADIO = 'input[value="default"], input[type="radio"][checked]'
RESUME_DROPDOWN = 'select[data-automation="resume-select"]'

# 附加问题
ADDITIONAL_QUESTIONS = '[data-automation="additional-questions"], [class*="additional-question"]'
QUESTION_INPUT = 'input[data-automation="question-answer"], textarea[class*="question"]'
QUESTION_SELECT = 'select[data-automation="question-select"]'

# 求职信
COVER_LETTER_SECTION = '[data-automation="cover-letter"]'
COVER_LETTER_TEXTAREA = 'textarea[data-automation="cover-letter-text"], textarea[placeholder*="cover letter"]'  # noqa: E501

# 提交按钮
SUBMIT_APPLICATION_BUTTON = 'button[data-automation="submit-application"], button[type="submit"]:has-text("Submit")'  # noqa: E501
# 最终提交按钮(review 页专有,e2e 2026-07-22 实测文案 "Submit application")。
# 优先于 SUBMIT_APPLICATION_BUTTON:后者可能误命中向导顶部 "Review and submit" 步骤指示按钮。
SUBMIT_APPLICATION_FINAL = 'button[type="submit"]:has-text("Submit application"), button:has-text("Submit application")'  # noqa: E501
CONFIRM_SUBMIT_BUTTON = 'button:has-text("Confirm"), button:has-text("Submit application")'

# 下一步
NEXT_STEP_BUTTON = 'button[data-automation="next-step"], button:has-text("Next")'
CONTINUE_BUTTON = 'button[data-automation="continue"], button:has-text("Continue")'
BACK_BUTTON = 'button[data-automation="back"], button:has-text("Back")'

# =============================================================================
# 提交结果
# =============================================================================

# 成功确认
SUCCESS_MESSAGE = '[data-automation="success-message"], div:has-text("Application submitted"), div:has-text("successfully submitted")'  # noqa: E501
SUCCESS_MODAL = '[data-automation="success-modal"], [role="dialog"]:has-text("success")'

# 失败/错误
ERROR_MESSAGE = '[data-automation="error-message"], .error-message, [role="alert"]'
FORM_VALIDATION_ERROR = '[data-automation="validation-error"], [class*="field-error"]'

# 继续浏览
CONTINUE_BROWSING_BUTTON = 'button:has-text("Continue browsing"), a:has-text("Back to jobs")'
CLOSE_SUCCESS_MODAL = 'button[aria-label="Close"], [data-automation="close-success"]'

# =============================================================================
# 验证码相关（检测用）
# =============================================================================

RECAPTCHA_IFRAME = 'iframe[src*="recaptcha"], iframe[src*="google.com/recaptcha"]'
HCAPTCHA_IFRAME = 'iframe[src*="hcaptcha"], iframe[src*="hcaptcha.com"]'
CAPTCHA_CHALLENGE = '[data-automation="captcha"], .g-recaptcha, .h-captcha'
VERIFY_HUMAN_PROMPT = 'text=verify you are human, text=prove you are not a robot, text=security check'  # noqa: E501

# =============================================================================
# 辅助选择器
# =============================================================================

# 加载状态
LOADING_SPINNER = '[data-automation="loading"], .spinner, [class*="loading"]'
SKELETON_LOADER = '[data-automation="skeleton"], [class*="skeleton"]'

# 空状态
NO_JOBS_MESSAGE = 'text=No jobs found, text=No recommended jobs'
EMPTY_STATE = '[data-automation="empty-state"]'
