# Candidate Interview Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent a first-run or source-backed candidate profile from becoming a proposal until Python has validated a complete, explicitly answerable `ai-job-search` interview.

**Architecture:** Add typed interview questions and answers to the candidate adapter contract, then make `CandidateOnboarding` load the persisted task and enforce the interview gate before persisting any result or proposal. Keep conversational wording in the active CC/Codex agent while Python owns the required dimension set, answer completeness, and legal state transitions.

**Tech Stack:** Python 3.11+, Pydantic v2, SQLite, Typer, pytest, uv, ruff

## Global Constraints

- Do not modify either pinned integration checkout.
- Keep the candidate-profile fork pinned at commit `aa7c7073990492c9111fbdda48f6adde24a1d91b`.
- Every required dimension accepts an explicit `not_provided` or `no_preference` answer.
- Every verified candidate fact continues to require source evidence.
- Existing confirmed profiles remain reusable without a new interview.
- Candidate documents, extracted text, answers, and checkpoint payloads remain ignored private runtime data.
- Do not connect this workflow to application execution.
- Preserve at least 80% total test coverage.

---

### Task 1: Define the typed interview contract

**Files:**
- Create: `src/domain/candidate_interview.py`
- Modify: `src/domain/__init__.py`
- Modify: `src/adapters/candidate_profile.py`
- Test: `tests/unit/test_candidate_profile_adapter.py`

**Interfaces:**
- Produces: `InterviewDimension`, `REQUIRED_INTERVIEW_DIMENSIONS`, `InterviewQuestion`, `InterviewAnswer`, and `InterviewAnswerStatus`.
- Produces: `CandidateProfileAdapter.validate_answers(payload: object) -> dict[InterviewDimension, InterviewAnswer]`.
- Changes: `CandidateProfileAdapter.validate_result(payload: object, *, task: CandidateProfileTask)` validates the result against the task's Python-derived `interview_complete`.

- [ ] **Step 1: Add failing adapter tests**

Add tests that construct a v2 task with no answers and guarantee:

```python
def complete_questions() -> list[dict[str, object]]:
    return [
        {
            "dimension": dimension.value,
            "prompt": f"Question for {dimension.value}?",
            "optional": dimension in {
                InterviewDimension.SALARY_EXPECTATIONS,
                InterviewDimension.REFERENCES,
            },
        }
        for dimension in REQUIRED_INTERVIEW_DIMENSIONS
    ]


def test_first_task_requires_all_typed_interview_questions() -> None:
    task = adapter().build_task("profile-run-1", ["cv.pdf"], {})
    result = adapter().validate_result(
        {
            "kind": "questions",
            "task_id": task.task_id,
            "questions": complete_questions(),
        },
        task=task,
    )
    assert {item.dimension for item in result.questions} == set(
        REQUIRED_INTERVIEW_DIMENSIONS
    )


def test_first_task_rejects_immediate_proposal() -> None:
    task = adapter().build_task("profile-run-1", ["cv.pdf"], {})
    with pytest.raises(
        ValidationError,
        match="interview must be completed before proposal",
    ):
        adapter().validate_result(proposal_payload(task.task_id), task=task)
```

Also cover a missing question dimension, a duplicated dimension, an unknown
dimension, a missing answer dimension, an empty `answered` value, and accepted
`not_provided`/`no_preference` statuses.

- [ ] **Step 2: Run adapter tests and capture RED**

Run:

```bash
uv run pytest tests/unit/test_candidate_profile_adapter.py -q
```

Expected: collection or assertion failure because the typed interview contract
and task-aware validation do not exist.

- [ ] **Step 3: Commit the RED checkpoint**

```bash
git add tests/unit/test_candidate_profile_adapter.py
git commit -m "test: require typed candidate interview contract"
```

- [ ] **Step 4: Implement the minimal domain and adapter contract**

Create these types in `src/domain/candidate_interview.py`:

```python
class InterviewDimension(StrEnum):
    BEHAVIORAL_STYLE = "behavioral_style"
    CAREER_GOALS = "career_goals"
    NEXT_ROLE_MOTIVATORS = "next_role_motivators"
    MUST_HAVES = "must_haves"
    DEAL_BREAKERS = "deal_breakers"
    SALARY_EXPECTATIONS = "salary_expectations"
    REFERENCES = "references"


REQUIRED_INTERVIEW_DIMENSIONS = tuple(InterviewDimension)


class InterviewAnswerStatus(StrEnum):
    ANSWERED = "answered"
    NOT_PROVIDED = "not_provided"
    NO_PREFERENCE = "no_preference"


class InterviewQuestion(BaseModel):
    model_config = ConfigDict(frozen=True)
    dimension: InterviewDimension
    prompt: str = Field(min_length=1)
    optional: bool = False


class InterviewAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: InterviewAnswerStatus
    value: str | None = None

    @model_validator(mode="after")
    def require_value_when_answered(self) -> "InterviewAnswer":
        if self.status is InterviewAnswerStatus.ANSWERED:
            if self.value is None or not self.value.strip():
                raise ValueError("answered interview value must not be empty")
        return self
```

Update `CandidateProfileTask.answers` to use structured answers and add
`interview_complete: bool`, derived only by `build_task`. Validate that a
questions result contains every required dimension exactly once. Reject
proposal results when `task.interview_complete` is false. `validate_answers`
must reject missing and unknown dimensions and return normalized enum-keyed
answers.

- [ ] **Step 5: Run adapter tests and capture GREEN**

Run:

```bash
uv run pytest tests/unit/test_candidate_profile_adapter.py -q
```

Expected: all adapter tests pass.

- [ ] **Step 6: Commit the GREEN checkpoint**

```bash
git add src/domain/candidate_interview.py src/domain/__init__.py src/adapters/candidate_profile.py tests/unit/test_candidate_profile_adapter.py
git commit -m "fix: enforce typed candidate interview contract"
```

### Task 2: Enforce legal onboarding transitions

**Files:**
- Modify: `src/application/candidate_onboarding.py`
- Modify: `src/application/workflow.py`
- Test: `tests/unit/test_candidate_onboarding.py`
- Test: `tests/unit/test_candidate_evaluation_workflow.py`

**Interfaces:**
- Consumes: `CandidateProfileAdapter.validate_result(..., task=task)` and `validate_answers`.
- Produces: `OnboardingOutcome.questions: tuple[InterviewQuestion, ...]`.
- Preserves: `submit_answers(run_id, source_documents, answers)` while validating structured answers and deriving interview completion in Python.

- [ ] **Step 1: Add failing onboarding state tests**

Replace the former immediate-proposal happy path with:

```python
def test_first_cv_run_rejects_proposal_before_interview(tmp_path: Path) -> None:
    onboarding = service(tmp_path)
    task = onboarding.ensure_profile("run-1", ["cv.pdf"])
    with pytest.raises(
        ValidationError,
        match="interview must be completed before proposal",
    ):
        onboarding.submit_result(
            "run-1",
            task.task_id,
            proposal_payload(task.task_id),
        )
    assert onboarding.profiles.get_active() is None


def test_complete_interview_then_proposal_can_be_confirmed(
    tmp_path: Path,
) -> None:
    onboarding = service(tmp_path)
    first = onboarding.ensure_profile("run-1", ["cv.pdf"])
    questions = onboarding.submit_result(
        "run-1",
        first.task_id,
        questions_payload(first.task_id),
    )
    assert questions.status is OnboardingStatus.NEEDS_ANSWERS
    follow_up = onboarding.submit_answers(
        "run-1",
        ["cv.pdf"],
        complete_answers_payload(),
    )
    review = onboarding.submit_result(
        "run-1",
        follow_up.task_id,
        proposal_payload(follow_up.task_id),
    )
    assert review.status is OnboardingStatus.WAITING_FOR_USER
```

Assert that rejected results are not written to `result.json`, structured
answers appear in the follow-up task, active-profile reuse still returns
`ready`, and explicit source-backed updates repeat the gate.

- [ ] **Step 2: Run onboarding and workflow tests and capture RED**

Run:

```bash
uv run pytest tests/unit/test_candidate_onboarding.py tests/unit/test_candidate_evaluation_workflow.py -q
```

Expected: failures because onboarding does not load the task or enforce the
typed interview state.

- [ ] **Step 3: Commit the RED checkpoint**

```bash
git add tests/unit/test_candidate_onboarding.py tests/unit/test_candidate_evaluation_workflow.py
git commit -m "test: define mandatory onboarding interview transitions"
```

- [ ] **Step 4: Implement minimal state enforcement**

In `submit_result`, read and validate `task.json` before accepting a result:

```python
task = self.adapter.validate_task(self.checkpoints.read_task(task_id))
result = self.adapter.validate_result(payload, task=task)
self.checkpoints.submit_result(task_id, encoded)
```

This ordering ensures invalid results are not persisted. In `submit_answers`,
normalize the full answer set through `validate_answers` before creating the
follow-up task. The follow-up task receives the structured answers, and
`build_task` derives `interview_complete=True`.

- [ ] **Step 5: Run onboarding and workflow tests and capture GREEN**

Run:

```bash
uv run pytest tests/unit/test_candidate_onboarding.py tests/unit/test_candidate_evaluation_workflow.py -q
```

Expected: all focused state-machine tests pass.

- [ ] **Step 6: Commit the GREEN checkpoint**

```bash
git add src/application/candidate_onboarding.py src/application/workflow.py tests/unit/test_candidate_onboarding.py tests/unit/test_candidate_evaluation_workflow.py
git commit -m "fix: gate candidate proposals on completed interview"
```

### Task 3: Update CLI, skills, and contract version

**Files:**
- Modify: `src/main.py`
- Modify: `tests/unit/test_workflow_cli.py`
- Modify: `.agents/skills/jobsdb-assistant/SKILL.md`
- Modify: `.claude/skills/jobsdb-assistant/SKILL.md`
- Modify: `integrations/manifest.json`
- Modify: `tests/unit/test_integration_manifest.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: typed `InterviewQuestion` output and structured answers.
- Produces: machine-readable question objects with `dimension`, `prompt`, and `optional`.
- Changes: candidate adapter contract version from `candidate-profile.v1` to `candidate-profile.v2`; fork URL and SHA remain unchanged.

- [ ] **Step 1: Add failing CLI and manifest tests**

Assert `_onboarding_payload` emits:

```json
{
  "questions": [
    {
      "dimension": "behavioral_style",
      "prompt": "How do you prefer to work?",
      "optional": false
    }
  ]
}
```

Assert the manifest declares `candidate-profile.v2` while retaining
`aa7c7073990492c9111fbdda48f6adde24a1d91b`.

- [ ] **Step 2: Run CLI and manifest tests and capture RED**

Run:

```bash
uv run pytest tests/unit/test_workflow_cli.py tests/unit/test_integration_manifest.py -q
```

Expected: failures because questions are serialized as strings and the
manifest still declares v1.

- [ ] **Step 3: Commit the RED checkpoint**

```bash
git add tests/unit/test_workflow_cli.py tests/unit/test_integration_manifest.py
git commit -m "test: define candidate interview CLI protocol"
```

- [ ] **Step 4: Implement CLI, skill, manifest, and documentation changes**

Serialize each question explicitly:

```python
"questions": [
    {
        "dimension": item.dimension.value,
        "prompt": item.prompt,
        "optional": item.optional,
    }
    for item in outcome.questions
],
```

Update both skill copies to require typed questions on the first task, collect
answers keyed by dimension, accept explicit skip statuses, and forbid a
proposal until the follow-up task reports `interview_complete: true`. Update
the manifest contract version only; do not change the fork commit. Document
the corrective behavior in README and CHANGELOG without candidate data.

- [ ] **Step 5: Run CLI and manifest tests and capture GREEN**

Run:

```bash
uv run pytest tests/unit/test_workflow_cli.py tests/unit/test_integration_manifest.py -q
```

Expected: all focused protocol tests pass.

- [ ] **Step 6: Commit the GREEN checkpoint**

```bash
git add src/main.py tests/unit/test_workflow_cli.py .agents/skills/jobsdb-assistant/SKILL.md .claude/skills/jobsdb-assistant/SKILL.md integrations/manifest.json tests/unit/test_integration_manifest.py README.md CHANGELOG.md
git commit -m "fix: expose mandatory candidate interview workflow"
```

### Task 4: Full regression, privacy, and evidence

**Files:**
- Create: `docs/testing/2026-07-24-candidate-interview-gate.tdd.md`
- Modify: `docs/superpowers/plans/2026-07-24-candidate-interview-gate.md`

**Interfaces:**
- Consumes: all preceding implementation and test guarantees.
- Produces: factual RED/GREEN, coverage, privacy, and commit evidence.

- [ ] **Step 1: Run focused and full verification**

Run:

```bash
uv run ruff check src tests
uv run pytest -m "not e2e" -q
uv run pytest -m "not e2e" --cov=src --cov-branch --cov-report=term-missing -q
uv run python scripts/privacy_guard.py
git diff --check
```

Expected: lint, non-E2E suite, coverage of at least 80%, privacy guard, and
diff checks all pass. Existing documented dependency warnings may remain but
must be recorded exactly.

- [ ] **Step 2: Write the TDD evidence report**

Record:

- the source design and implementation plan;
- each user journey;
- the exact RED and GREEN commands and outcomes;
- unit versus integration guarantees;
- total statement and branch coverage;
- privacy result;
- checkpoint commit IDs;
- any intentional gaps.

Do not include source PDF text, candidate answers, raw checkpoint payloads, or
private contact details.

- [ ] **Step 3: Re-run documentation and repository checks**

Run:

```bash
rg -n "TBD|TODO|FIXME" docs/testing/2026-07-24-candidate-interview-gate.tdd.md docs/superpowers/plans/2026-07-24-candidate-interview-gate.md
git diff --check
git status --short
```

Expected: no placeholders or whitespace errors; only known user-owned probe
scripts may remain untracked.

- [ ] **Step 4: Commit final evidence**

```bash
git add docs/testing/2026-07-24-candidate-interview-gate.tdd.md docs/superpowers/plans/2026-07-24-candidate-interview-gate.md
git commit -m "docs: record candidate interview gate evidence"
```

### Task 5: Resume the private real-world run

**Files:**
- Private runtime only: `workspace/ai-tasks/`
- Private runtime only: configured SQLite database under `data/`

**Interfaces:**
- Consumes: corrected `candidate-profile.v2` onboarding flow.
- Produces: a new typed interview checkpoint for the supplied resume; no
  tracked artifacts.

- [ ] **Step 1: Verify the earlier proposal is inactive**

Use the repository query APIs or read-only SQLite inspection to confirm that
`profile-proposal-manual-ai-architect-20260724` is unconfirmed and no active
candidate profile exists. Do not delete broad runtime directories.

- [ ] **Step 2: Start a new run ID**

Run:

```bash
uv run python -m src.main workflow profile-prepare \
  --run-id manual-ai-architect-interview-20260724 \
  --source /Users/ian/AI_Project/resume_bowen/Bowen_Bao_resume_v2.pdf
```

Expected: `waiting_for_agent` with a new task ID and contract v2 task.

- [ ] **Step 3: Service the question checkpoint**

Read only the task's pinned capability paths and supplied PDF. Write a typed
questions result containing every required dimension exactly once, submit it,
and expect `needs_answers`.

- [ ] **Step 4: Present the interview to the user**

Ask the questions conversationally. Stop at the explicit user-input checkpoint.
Do not fabricate answers, confirm a profile, discover jobs, or start
evaluations before the user responds.
