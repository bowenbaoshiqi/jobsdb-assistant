# Career-Ops Native Profile Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the confirmed ai-job-search CV extraction and interview result into one immutable canonical profile and a private, deterministic career-ops-native profile bundle.

**Architecture:** Extend the candidate-profile checkpoint with typed evidence-backed CV data and per-dimension interview synthesis, while Python injects the original interview answers. A deterministic projector writes `cv.md`, `config/profile.yml`, `modes/_profile.md`, and a hash manifest; evaluation tasks consume those paths rather than interpreting custom profile JSON.

**Tech Stack:** Python 3.11+, Pydantic v2, PyYAML, SQLite JSON payloads, Typer, pytest, uv, ruff

**Execution status (2026-07-27):** Tasks 1–6 are complete using the recorded
RED/GREEN commits. The private profile update, explicit confirmation, native
bundle generation, and runtime wiring verification also completed.

## Global Constraints

- Do not modify either pinned integration checkout.
- Keep ai-job-search pinned at `aa7c7073990492c9111fbdda48f6adde24a1d91b`.
- Keep career-ops pinned at `01bf8b469ad5177a9c30230bc00509ead8e006c2`.
- Preserve exact raw interview answers and explicit skip statuses.
- Do not add custom career-ops weights, score fusion, or new score rules.
- Keep all generated candidate bundles below ignored `workspace/`.
- Existing profile v1 remains historical; a complete bundle requires an explicit profile update and confirmation.
- Preserve at least 80% total test coverage.

---

### Task 1: Define canonical CV and interview synthesis contracts

**Files:**
- Create: `src/domain/candidate_cv.py`
- Modify: `src/domain/candidate.py`
- Modify: `src/domain/__init__.py`
- Test: `tests/unit/test_candidate_canonical_profile.py`

**Interfaces:**
- Produces: `SourcedText`, `CandidateExperience`, `CandidateEducation`, `CandidateCv`, `IntentSynthesis`, and `CareerOpsIntentFields`.
- Extends: `CandidateProfileProposal` and `CandidateProfile` with `canonical_cv`, `interview_answers`, and `intent_syntheses`.
- Preserves: legacy JSON payloads remain readable through defaults.

- [ ] **Step 1: Add failing canonical-profile tests**

Create synthetic tests covering:

```python
def test_sourced_text_requires_evidence() -> None:
    with pytest.raises(ValidationError, match="evidence"):
        SourcedText(value="Built an AI platform", evidence=[])


def test_answered_intent_requires_matching_hash() -> None:
    answer = InterviewAnswer(status="answered", value="Large companies")
    synthesis = IntentSynthesis(
        dimension="must_haves",
        answer_hash="0" * 64,
        summary="Prefers mature large organizations.",
        target_field="must_haves",
    )
    with pytest.raises(ValueError, match="answer hash mismatch"):
        validate_intent_syntheses(
            {InterviewDimension.MUST_HAVES: answer},
            [synthesis],
        )


def test_legacy_profile_json_remains_readable() -> None:
    profile = CandidateProfile.model_validate(LEGACY_PROFILE_PAYLOAD)
    assert profile.canonical_cv is None
    assert profile.interview_answers == {}
```

Also test exact dimension coverage, non-empty synthesis for `answered`,
explicit skip handling, and immutable confirmed models.

- [ ] **Step 2: Run the tests and capture RED**

Run:

```bash
uv run pytest tests/unit/test_candidate_canonical_profile.py -q
```

Expected: collection failure because `src.domain.candidate_cv` does not exist.

- [ ] **Step 3: Commit the RED checkpoint**

```bash
git add tests/unit/test_candidate_canonical_profile.py
git commit -m "test: define canonical candidate profile contract"
```

- [ ] **Step 4: Implement the minimal typed domain**

Use frozen Pydantic models. `SourcedText` has a non-empty value and at least
one existing `FactEvidence`. `CandidateCv` contains optional sourced identity
fields plus ordered experience, education, categorized skills, projects,
certifications, publications, awards, languages, headline, and summary.

Define:

```python
class IntentTargetField(StrEnum):
    BEHAVIORAL_STYLE = "behavioral_style"
    CAREER_GOALS = "career_goals"
    NEXT_ROLE_MOTIVATORS = "next_role_motivators"
    MUST_HAVES = "must_haves"
    DEAL_BREAKERS = "deal_breakers"
    SALARY_EXPECTATIONS = "salary_expectations"
    REFERENCES = "references"


class IntentSynthesis(BaseModel):
    model_config = ConfigDict(frozen=True)
    dimension: InterviewDimension
    answer_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    summary: str | None = None
    target_field: IntentTargetField
    target_roles: tuple[str, ...] = ()
    role_archetypes: tuple[str, ...] = ()
    culture_requirements: tuple[str, ...] = ()
    compensation_target: str | None = None
    compensation_minimum: str | None = None
    compensation_currency: str | None = None
```

Add a pure validator that recomputes each raw answer SHA-256, requires the
exact answered dimension set, and requires `target_field.value ==
dimension.value`.

- [ ] **Step 5: Run canonical-profile tests and capture GREEN**

Run:

```bash
uv run pytest tests/unit/test_candidate_canonical_profile.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit the GREEN checkpoint**

```bash
git add src/domain/candidate_cv.py src/domain/candidate.py src/domain/__init__.py tests/unit/test_candidate_canonical_profile.py
git commit -m "feat: add canonical candidate profile contract"
```

### Task 2: Make ai-job-search synthesis complete and Python-owned

**Files:**
- Modify: `src/adapters/candidate_profile.py`
- Modify: `src/application/candidate_onboarding.py`
- Modify: `src/storage/candidate_repository.py`
- Modify: `tests/unit/test_candidate_profile_adapter.py`
- Modify: `tests/unit/test_candidate_onboarding.py`
- Modify: `tests/integration/test_candidate_repository.py`

**Interfaces:**
- Consumes: `CandidateCv`, complete validated interview answers, and `IntentSynthesis`.
- Produces: a `CandidateProfileProposal` whose raw answers are injected by Python.
- Changes: candidate profile contract to `candidate-profile.v3`.

- [ ] **Step 1: Add failing synthesis and persistence tests**

Guarantee:

```python
def test_agent_cannot_replace_raw_interview_answers() -> None:
    task = completed_task()
    result = adapter().validate_result(agent_proposal_payload(), task=task)
    assert result.profile.interview_answers == task.answers


def test_proposal_rejects_missing_intent_synthesis() -> None:
    task = completed_task()
    payload = agent_proposal_payload()
    payload["intent_syntheses"].pop()
    with pytest.raises(ValidationError, match="intent synthesis"):
        adapter().validate_result(payload, task=task)


def test_confirmed_profile_persists_canonical_fields(tmp_path: Path) -> None:
    profile = repository_round_trip(complete_proposal())
    assert profile.canonical_cv.experience[0].company.value == "Example"
    assert profile.interview_answers["must_haves"].value == "Large companies"
```

Also prove skipped answers remain explicit and an old confirmed profile loads.

- [ ] **Step 2: Run focused tests and capture RED**

Run:

```bash
uv run pytest tests/unit/test_candidate_profile_adapter.py tests/unit/test_candidate_onboarding.py tests/integration/test_candidate_repository.py -q
```

Expected: failures because the adapter does not accept canonical CV/synthesis
output or inject answers into the proposal.

- [ ] **Step 3: Commit the RED checkpoint**

```bash
git add tests/unit/test_candidate_profile_adapter.py tests/unit/test_candidate_onboarding.py tests/integration/test_candidate_repository.py
git commit -m "test: require complete candidate synthesis persistence"
```

- [ ] **Step 4: Implement one-pass synthesis validation**

Extend `ProfileProposalResult`:

```python
class ProfileProposalResult(BaseModel):
    kind: Literal["proposal"]
    task_id: str
    profile: CandidateProfileProposal
    canonical_cv: CandidateCv
    intent_syntheses: list[IntentSynthesis]
```

After schema validation, call `validate_intent_syntheses(task.answers, ...)`
and create a copied proposal:

```python
complete_profile = result.profile.model_copy(update={
    "canonical_cv": result.canonical_cv,
    "interview_answers": task.answers,
    "intent_syntheses": tuple(result.intent_syntheses),
})
```

Return a copied `ProfileProposalResult` containing `complete_profile`.
Update repository confirmation to copy all canonical fields. No database
column migration is required because candidate payloads are JSON.

- [ ] **Step 5: Run focused tests and capture GREEN**

Run the same focused command. Expected: all tests pass.

- [ ] **Step 6: Commit the GREEN checkpoint**

```bash
git add src/adapters/candidate_profile.py src/application/candidate_onboarding.py src/storage/candidate_repository.py tests/unit/test_candidate_profile_adapter.py tests/unit/test_candidate_onboarding.py tests/integration/test_candidate_repository.py
git commit -m "feat: preserve complete ai-job-search candidate synthesis"
```

### Task 3: Project the native career-ops profile bundle

**Files:**
- Create: `src/adapters/career_ops_profile.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Test: `tests/unit/test_career_ops_profile_adapter.py`
- Test: `tests/integration/test_career_ops_profile_bundle.py`

**Interfaces:**
- Produces: `CareerOpsProfileBundle` with profile and bundle hashes plus exact file paths.
- Produces: `CareerOpsProfileAdapter.project(profile: CandidateProfile) -> CareerOpsProfileBundle`.
- Writes only below the configured private workspace root.

- [ ] **Step 1: Add failing projector tests**

Use a fully synthetic profile and assert exact content:

```python
def test_projector_writes_native_bundle(tmp_path: Path) -> None:
    bundle = projector(tmp_path).project(complete_profile())
    assert bundle.cv_path.read_text().startswith("# Synthetic Candidate")
    profile_yml = yaml.safe_load(bundle.profile_yml_path.read_text())
    assert profile_yml["target_roles"]["primary"] == ["AI Architect"]
    assert profile_yml["culture_screen"]["require"] == [
        "Mature large organization"
    ]
    assert "## Must-haves" in bundle.profile_md_path.read_text()


def test_projector_is_deterministic(tmp_path: Path) -> None:
    first = projector(tmp_path).project(complete_profile())
    second = projector(tmp_path).project(complete_profile())
    assert first.bundle_hash == second.bundle_hash
    assert first.manifest_path.read_bytes() == second.manifest_path.read_bytes()
```

Also cover missing optional fields, explicit skip statuses, placeholder
rejection, output traversal rejection, manifest field-source entries, and no
writes under either integration checkout.

- [ ] **Step 2: Run projector tests and capture RED**

Run:

```bash
uv run pytest tests/unit/test_career_ops_profile_adapter.py tests/integration/test_career_ops_profile_bundle.py -q
```

Expected: collection failure because the projector does not exist.

- [ ] **Step 3: Commit the RED checkpoint**

```bash
git add tests/unit/test_career_ops_profile_adapter.py tests/integration/test_career_ops_profile_bundle.py
git commit -m "test: define career-ops native profile bundle"
```

- [ ] **Step 4: Add safe YAML support and implement rendering**

Add `PyYAML>=6.0,<7` to runtime dependencies and update `uv.lock`. Use
`yaml.safe_dump(..., sort_keys=False, allow_unicode=True)`.

`CareerOpsProfileAdapter`:

1. requires a confirmed profile with canonical CV and complete intent;
2. renders all content in memory;
3. rejects unresolved placeholder tokens;
4. writes to a temporary sibling directory;
5. computes each file hash and the bundle hash;
6. writes the manifest last;
7. atomically renames the temporary directory to
   `<workspace>/<profile.content_hash>`;
8. reuses an existing bundle only when every manifest hash matches.

- [ ] **Step 5: Run projector tests and capture GREEN**

Run the same projector command. Expected: all tests pass.

- [ ] **Step 6: Commit the GREEN checkpoint**

```bash
git add src/adapters/career_ops_profile.py pyproject.toml uv.lock tests/unit/test_career_ops_profile_adapter.py tests/integration/test_career_ops_profile_bundle.py
git commit -m "feat: generate native career-ops profile bundle"
```

### Task 4: Make evaluation consume the native bundle

**Files:**
- Modify: `src/adapters/job_evaluation.py`
- Modify: `src/application/evaluate_jobs.py`
- Modify: `src/application/workflow.py`
- Modify: `src/application/runtime.py`
- Modify: `src/domain/evaluation.py`
- Modify: `tests/unit/test_job_evaluation_adapter.py`
- Modify: `tests/unit/test_evaluate_jobs.py`
- Modify: `tests/unit/test_candidate_evaluation_workflow.py`

**Interfaces:**
- Consumes: `CareerOpsProfileBundle`.
- Changes: `JobEvaluationTask` replaces embedded `profile` with profile identity/hash and native bundle references.
- Changes: evaluation cache key includes `bundle_hash` and projection contract version.
- Preserves: native ordered A-F output and overall score.

- [ ] **Step 1: Add failing evaluation-consumption tests**

Assert:

```python
def test_evaluation_task_references_native_profile_bundle() -> None:
    task = adapter().build_task("task-1", profile(), bundle(), [snapshot()])
    assert task.profile_context_paths == [
        bundle().cv_path,
        bundle().profile_yml_path,
        bundle().profile_md_path,
    ]
    assert not hasattr(task, "profile")


def test_projection_change_invalidates_cache() -> None:
    assert cache_key(bundle_hash="a" * 64) != cache_key(
        bundle_hash="b" * 64
    )
```

Also require valid bundle paths/hashes and unchanged A-F result validation.

- [ ] **Step 2: Run evaluation tests and capture RED**

Run:

```bash
uv run pytest tests/unit/test_job_evaluation_adapter.py tests/unit/test_evaluate_jobs.py tests/unit/test_candidate_evaluation_workflow.py -q
```

Expected: failures because tasks still embed the custom profile.

- [ ] **Step 3: Commit the RED checkpoint**

```bash
git add tests/unit/test_job_evaluation_adapter.py tests/unit/test_evaluate_jobs.py tests/unit/test_candidate_evaluation_workflow.py
git commit -m "test: require native career-ops profile consumption"
```

- [ ] **Step 4: Implement bundle-backed evaluation**

Add to `JobEvaluationTask`:

```python
profile_id: str
profile_version: PositiveInt
profile_hash: str
profile_bundle_hash: str
profile_projection_version: str
profile_context_paths: list[str] = Field(min_length=3, max_length=3)
```

Remove the embedded `profile`. Update cache identity with
`profile_bundle_hash` and `profile_projection_version`. Build or verify the
bundle before planning evaluations. If the active profile is legacy and has no
canonical data, raise:

```text
active candidate profile requires explicit update before career-ops evaluation
```

- [ ] **Step 5: Run evaluation tests and capture GREEN**

Run the same evaluation command. Expected: all tests pass.

- [ ] **Step 6: Commit the GREEN checkpoint**

```bash
git add src/adapters/job_evaluation.py src/application/evaluate_jobs.py src/application/workflow.py src/application/runtime.py src/domain/evaluation.py tests/unit/test_job_evaluation_adapter.py tests/unit/test_evaluate_jobs.py tests/unit/test_candidate_evaluation_workflow.py
git commit -m "feat: evaluate jobs from native career-ops profile bundle"
```

### Task 5: Update workflow protocol, skills, and compatibility locks

**Files:**
- Modify: `integrations/manifest.json`
- Modify: `tests/unit/test_integration_manifest.py`
- Modify: `.agents/skills/jobsdb-assistant/SKILL.md`
- Modify: `.claude/skills/jobsdb-assistant/SKILL.md`
- Modify: `tests/unit/test_workflow_cli.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Changes: candidate contract to `candidate-profile.v3`.
- Changes: evaluation contract to `career-ops-native-profile-bundle.v2`.
- Preserves: both fork URLs and commit SHAs.

- [ ] **Step 1: Add failing protocol tests**

Assert both new contract versions and unchanged SHAs. Assert evaluation task
instructions list `profile_context_paths` and require the career-ops native
loading order:

```text
config/profile.yml → modes/_shared.md → modes/_profile.md → modes/oferta.md → cv.md
```

- [ ] **Step 2: Run protocol tests and capture RED**

Run:

```bash
uv run pytest tests/unit/test_integration_manifest.py tests/unit/test_workflow_cli.py -q
```

Expected: contract-version and protocol assertion failures.

- [ ] **Step 3: Commit the RED checkpoint**

```bash
git add tests/unit/test_integration_manifest.py tests/unit/test_workflow_cli.py
git commit -m "test: define native profile bundle workflow protocol"
```

- [ ] **Step 4: Update locks, skills, and docs**

Update contract versions only. Both skills must:

- require canonical CV and per-dimension synthesis in a completed profile
  proposal;
- explain that Python injects raw answers;
- read exactly the bundle paths in each evaluation task;
- never recreate or edit a profile bundle;
- retain career-ops native scoring without custom weights.

- [ ] **Step 5: Run protocol tests and capture GREEN**

Run the same protocol command. Expected: all tests pass.

- [ ] **Step 6: Commit the GREEN checkpoint**

```bash
git add integrations/manifest.json tests/unit/test_integration_manifest.py .agents/skills/jobsdb-assistant/SKILL.md .claude/skills/jobsdb-assistant/SKILL.md tests/unit/test_workflow_cli.py README.md CHANGELOG.md
git commit -m "feat: expose native career-ops profile workflow"
```

### Task 6: Full regression, evidence, and private v2 update checkpoint

**Files:**
- Create: `docs/testing/2026-07-27-career-ops-profile-bundle.tdd.md`
- Modify: `docs/superpowers/plans/2026-07-27-career-ops-profile-bundle.md`
- Private runtime only: `workspace/`
- Private runtime only: configured SQLite database under `data/`

**Interfaces:**
- Produces: complete test evidence and a new private profile-update interview checkpoint.

- [ ] **Step 1: Run full verification**

Run:

```bash
uv run ruff check src tests
uv run pytest -m "not e2e" -q
uv run pytest -m "not e2e" --cov=src --cov-branch --cov-report=term -q
uv run python scripts/privacy_guard.py
git diff --check
```

Expected: all checks pass and total coverage is at least 80%.

- [ ] **Step 2: Validate skills**

Run the installed skill validator against both repository skill copies.
Expected: both pass without modifying the skills.

- [ ] **Step 3: Write factual TDD evidence**

Record design/plan links, every RED/GREEN commit and command, focused and full
results, coverage, privacy, known warnings, and bundle privacy guarantees.
Do not include candidate content or private paths beyond generic workspace
patterns.

- [ ] **Step 4: Commit evidence**

```bash
git add docs/testing/2026-07-27-career-ops-profile-bundle.tdd.md docs/superpowers/plans/2026-07-27-career-ops-profile-bundle.md
git commit -m "docs: record native career-ops profile bundle evidence"
```

- [ ] **Step 5: Start the explicit private profile update**

Run:

```bash
uv run python -m src.main workflow profile-prepare \
  --run-id career-ops-profile-v2-20260727 \
  --update \
  --source /Users/ian/AI_Project/resume_bowen/Bowen_Bao_resume_v2.pdf
```

Service the typed interview task according to the updated skill. Stop at the
explicit user-answer or profile-confirmation checkpoint. Do not confirm on the
user's behalf.
