# JobsDB Assistant Integration Design

Date: 2026-07-23
Status: Approved for implementation planning

## 1. Objective

Extend `jobsdb-auto-apply` v2.0 into a local, human-approved JobsDB job-search assistant.
JobsDB remains the only discovery channel. The system will:

1. fetch approximately 50 JobsDB listings and their complete job descriptions;
2. incrementally deduplicate and evaluate them using the capabilities of `career-ops`;
3. present all evaluated jobs in a local HTML Dashboard;
4. generate an English tailored CV and a short English cover letter only for jobs selected by the user;
5. run reviewer, ATS, PDF, and factual-consistency checks;
6. require a second user approval for the generated application package;
7. execute each approved job individually:
   - `Quick Apply`: run the existing JobsDB browser automation;
   - `Apply`: open the JobsDB job-detail page for manual navigation to the employer site;
8. preserve an auditable history of the JD, evaluation, approved materials, and application result.

The first release is interactive. It does not include scheduling, GitHub Actions, cloud
deployment, or unattended background AI calls. The user starts and keeps open a Claude Code
or Codex session until the requested workflow is complete.

## 2. Confirmed Product Decisions

- The v2.0 Python repository is the main and only product repository.
- JobsDB is the sole source of job discovery.
- Claude Code and Codex receive equal first-class support.
- The current agent session performs AI work; no separate API key is required in v1.
- All fetched jobs remain visible. Low-score or disqualified jobs are folded and clearly
  labelled rather than deleted.
- Jobs are evaluated before the user selects them.
- Application materials are generated only after first-level selection.
- Every selected job receives:
  - a tailored English CV;
  - an English cover letter of 100–300 words, targeting approximately 180–220 words;
  - an independent reviewer report;
  - PDF, ATS, and factual-consistency checks.
- Materials require second-level approval.
- The user can approve, abandon, or request a versioned regeneration with written feedback.
- Approval adds a job to the execution list; it does not immediately submit the application.
- Every execution-list row has its own action:
  - Quick Apply: `Start automatic application`;
  - Apply: `Open JobsDB job detail`.
- `Apply` is the correct product term. It must not be renamed “Standard Apply.”
- `Apply` is a manual execution mode, not a skip or failure.
- Job type changes affect only final execution. They do not change evaluation or material
  generation.

## 3. Architectural Approach

Use a modular Python monolith with native external capability adapters.

```text
One Python application
├── JobsDB discovery and browser execution
├── Local Dashboard and API
├── SQLite system of record
├── CandidateProfileAdapter
├── JobEvaluationAdapter
└── ApplicationMaterialAdapter
```

An adapter is not a long-running service. The Python application is the only persistent local
process. External adapters run on demand and return when their task is complete.

The two upstream projects are not translated line by line into Python. Their relevant original
capabilities, prompts, templates, and native runtimes are retained behind thin, versioned JSON
wrappers. Unrelated channels and trackers are not imported.

## 4. Capability Ownership

| Capability | Source | Integration |
|---|---|---|
| JobsDB discovery and full-JD capture | Current repository | Extend |
| Quick Apply browser state machine | Current repository | Preserve and adapt |
| Apply manual assistance | New main-repo module | Implement |
| Browser ports, fakes, DI, login profile | Current repository | Preserve |
| SQLite | Current repository | Extend schema and repositories |
| Candidate onboarding/profile | `ai-job-search` | `CandidateProfileAdapter` |
| Job evaluation and ranking | `career-ops` | `JobEvaluationAdapter` |
| CV/cover-letter generation | `ai-job-search` | `ApplicationMaterialAdapter` |
| Reviewer, PDF, ATS, facts checks | `ai-job-search` | `ApplicationMaterialAdapter` |
| Local Dashboard | New main-repo module | Implement |
| Shared Claude/Codex workflow | New skill | Implement |

Do not import:

- `career-ops` multi-board discovery, auto-apply implementation, tracker, TUI, or Dashboard;
- `ai-job-search` Danish portals, scrape/rank commands, Gmail/Notion synchronization, outcome
  tracker, HTML report, or upskill workflow.

## 5. Proposed Repository Layout

```text
src/
├── domain/
│   ├── candidate.py
│   ├── job.py
│   ├── evaluation.py
│   ├── material.py
│   └── application.py
├── ports/
│   ├── candidate_profile.py
│   ├── job_evaluation.py
│   └── application_material.py
├── adapters/
│   ├── candidate_profile/
│   ├── job_evaluation/
│   └── application_material/
├── application/
│   ├── discover_jobs.py
│   ├── evaluate_jobs.py
│   ├── generate_materials.py
│   └── execute_application.py
├── browser/                       # existing
├── jobsdb/                        # existing and extended
├── dashboard/
├── storage/
└── orchestrator.py

integrations/
├── job-evaluation/                # pinned career-ops fork/release
└── application-material/          # pinned ai-job-search fork/release

.agents/skills/jobsdb-assistant/SKILL.md
.claude/skills/jobsdb-assistant/    # committed thin Claude entry only
.codex/skills/jobsdb-assistant/     # committed thin Codex entry only
workspace/                          # JDs, evaluations, materials, screenshots
data/                               # SQLite and browser profiles; never committed
```

The integration sources should be maintained as pinned forks or releases. They must retain
their licence and attribution. Avoid Git submodules in the first release.

## 6. Adapter Contracts

### 6.1 CandidateProfilePort

The profile adapter retains the `ai-job-search` onboarding paths:

- import a structured documents folder;
- paste/import one CV;
- conduct an interactive interview.

It produces a versioned profile containing verified facts, target roles, preferences,
exclusions, writing style, source documents, and optional STAR examples.

Generated materials may change wording, order, and emphasis. They may not change companies,
titles, dates, projects, skills, or metrics without a verified source update.

### 6.2 JobEvaluationPort

Input binds:

- schema version;
- JobsDB job ID;
- immutable JD snapshot and content hash;
- candidate-profile version;
- evaluation-engine and prompt versions.

Output includes:

- overall score;
- dimension scores;
- recommendation;
- strengths;
- gaps;
- risks and hard-condition flags;
- evidence tied to the JD and profile;
- concise report summary.

The native `career-ops` wrapper accepts batch JSON and emits batch JSON. One process handles a
batch and controls bounded concurrency; the main application must not launch one service per
job.

### 6.3 ApplicationMaterialPort

Input binds the approved job snapshot, evaluation, profile version, material prompt version,
and optional regeneration feedback.

Output is a manifest containing:

- package version;
- English CV source and PDF;
- English cover-letter source and PDF;
- cover-letter word count;
- reviewer result;
- ATS result;
- factual-consistency result;
- file paths and SHA-256 hashes.

Materials cannot advance to second-level approval unless required files exist, their hashes
match, the reviewer and facts checks pass, and the ATS/PDF checks satisfy configured policy.

### 6.4 Exchange Rules

- Use versioned JSON contracts validated by Pydantic.
- Preserve raw adapter input and output for diagnosis.
- Adapters cannot write application status directly to SQLite.
- Adapters cannot read one another’s private directories.
- The Python application owns all state transitions.
- Pin adapter implementation and prompt versions in every result.

## 7. Domain Data Model

### CandidateProfile

- version;
- verified facts and evidence;
- goals, preferences, and exclusions;
- writing style;
- source-document references;
- created timestamp.

### Job

- JobsDB job ID;
- canonical JobsDB URL;
- title, company, location;
- `apply_type`: `quick_apply | apply | unknown`;
- first/last seen timestamps;
- current snapshot.

### JobSnapshot

- job ID;
- full JD text;
- content hash;
- captured timestamp;
- active/expired status.

### JobEvaluation

- job snapshot and profile version;
- adapter, engine, and prompt versions;
- scores, recommendation, strengths, gaps, risks, and evidence;
- raw-output reference.

### ApplicationPackage

- job, evaluation, and profile references;
- package version;
- CV and cover-letter artifacts;
- reports and hashes;
- approval eligibility.

### ApplicationTask

- approved package;
- execution mode: `automatic | manual`;
- status and timestamps.

### ApplicationAttempt

- task and attempt number;
- current browser step;
- result or error code;
- screenshots;
- actual submitted file hashes.

## 8. Incremental Discovery

- Fetch approximately 50 JobsDB results and capture complete JDs.
- A matching job ID and unchanged content hash reuses the existing evaluation.
- A matching job ID with changed JD content creates a new snapshot and evaluation.
- Submitted jobs remain visible but cannot create another application task.
- Ignored and rejected jobs are folded by default.
- New jobs are highlighted and evaluated.
- All jobs remain searchable and selectable unless submission safeguards block them.

## 9. State Model

```text
DISCOVERED
→ NORMALIZED
→ EVALUATING
→ EVALUATED
→ WAITING_FIRST_APPROVAL

WAITING_FIRST_APPROVAL
├── SELECTED
│   → GENERATING_MATERIALS
│   → MATERIALS_READY
│   → WAITING_SECOND_APPROVAL
├── IGNORED
└── DEFERRED

WAITING_SECOND_APPROVAL
├── APPROVED → QUEUED
├── REVISION_REQUESTED
│   → GENERATING_MATERIALS
│   → new package version
└── ABANDONED

QUEUED
├── quick_apply
│   → AUTO_APPLYING
│   → SUBMITTED
│   → MANUAL_ACTION_REQUIRED
│   → RETRYABLE_FAILURE
│   → PERMANENT_FAILURE
└── apply
    → MANUAL_APPLY_READY
    → MANUAL_APPLY_IN_PROGRESS
    → SUBMITTED_MANUALLY
    → ABANDONED
```

If a Quick Apply listing changes to Apply at execution time, the system changes only the
execution mode and routes it to the manual flow. It does not force the Quick Apply state
machine.

## 10. Dashboard Design

The Dashboard is a local web application bound to `127.0.0.1`. SQLite is its only source of
state.

### 10.1 Global Header

- navigation: job report, material review, execution list, application history;
- current-run counts;
- profile and evaluation-rule versions;
- actions to update the profile and start job analysis.

### 10.2 Job Report and First Approval

- filters for Quick Apply, Apply, new/seen/ignored jobs, score, and risk;
- default sort by overall score;
- row summary with job/company, key judgement, score, apply type, and status;
- expanded view with dimensions, strengths, gaps, risks, evidence, full JD, and JobsDB URL;
- multi-select action: generate CV and cover letter.

Low-score and hard-risk jobs remain visible but are folded and clearly labelled.

### 10.3 Material Generation and Second Approval

- per-job generation progress;
- CV PDF preview and change summary;
- English cover-letter preview and word count;
- reviewer, ATS, and facts results;
- actions: abandon, regenerate with feedback, approve package.

Regeneration creates a new immutable package version and retains prior versions.

### 10.4 Per-Job Execution

Each approved job has its own action button.

- Quick Apply: `Start automatic application`.
- Apply: `Open JobsDB job detail`.
- Both: `View materials`.

The Apply button opens the JobsDB job-detail page, not a guessed or pre-extracted employer URL.
The user follows the JobsDB Apply link and completes the employer workflow manually.

### 10.5 History

- submitted/failed/manual status;
- approved and actually used material versions;
- confirmation screenshot and URL where available;
- resume and cover-letter hashes;
- retry or manual-recovery action;
- manual `mark submitted`/`abandon` controls for Apply jobs.

## 11. Shared Claude Code and Codex Skill

Use one canonical skill:

```text
.agents/skills/jobsdb-assistant/SKILL.md
```

Claude Code and Codex receive thin platform entries that reference the same workflow and
contracts. Supported intents include:

- start today’s job analysis;
- update my candidate profile;
- continue material generation;
- resume the previous task;
- show pending applications.

The v1 workflow is interactive:

```text
doctor/environment check
→ start local service
→ validate JobsDB login
→ discover and evaluate jobs
→ wait for first approval
→ generate and validate materials
→ wait for second approval
→ perform the selected per-job action
→ report results
```

The active agent session executes the adapter workflows. The user expects to keep Claude Code
or Codex open until the requested task finishes. Headless drivers may be added later behind
the same ports.

The repository currently ignores `.agents/` and `.claude/` wholesale. Before the shared skill
is added, narrow those rules using explicit allow-list exceptions for only the canonical skill
and thin platform entries. All other local agent settings remain ignored. Never commit
machine-specific agent configuration, transcripts, caches, approvals, or local paths.

## 12. Error Handling and Safety

- Invalid adapter output: archive it, attempt one structured repair, then require review.
- Interrupted CLI/model work: persist the state and allow resume.
- Expired JobsDB login: pause the affected task and request manual login.
- CAPTCHA: require manual action; do not bypass it.
- Changed/unknown JobsDB UI: capture screenshot, URL, state, and diagnostic DOM context.
- Failed PDF, ATS, reviewer, or factual check: block second-level approval.
- File hash mismatch: block upload and submission.
- Duplicate or already submitted job: block task creation.
- Apply listing: manual mode, never classify it as an automatic failure.
- Every automatic Quick Apply requires explicit approval of one immutable package version.
- Keep credentials, browser profiles, candidate data, generated materials, and screenshots
  outside Git.

### 12.1 Public-Repository Privacy Baseline

Privacy is an initial acceptance gate, not a later cleanup task:

- the public repository is created before development, but no source push occurs until the
  baseline audit passes;
- ignore `data/`, `workspace/`, `accounts/` except a synthetic example, browser profiles,
  cookies, sessions, SQLite files, logs, screenshots, generated CVs and cover letters, source
  documents, `.env*` except `.env.example`, and local agent settings;
- examples and tests use synthetic names, emails, employers, histories, and credentials only;
- CI runs secret scanning and a privacy-path guard on every push and pull request;
- the privacy guard fails if a sensitive runtime path or document format becomes tracked;
- diagnostic bundles must redact email addresses, candidate facts, cookies, tokens, URLs with
  secrets, and form answers;
- `upstream` is fetch-only locally to prevent accidental pushes to the source project;
- no job data, profile data, materials, screenshots, or browser state may be uploaded as CI
  artifacts in v1.

The existing “select the last valid dropdown option” fallback is unsafe for material facts such
as work authorization, salary, experience, and notice period. Replace it with semantic,
profile-backed answers. Unknown required fields must request manual action.

## 13. Testing Strategy

### Unit

- domain validation and state transitions;
- JSON contracts and Pydantic validation;
- evaluation import;
- material-manifest and hash validation;
- approval and duplicate-submission safeguards;
- semantic application-answer mapping.

### Integration

- JobEvaluationAdapter wrapper;
- CandidateProfileAdapter and ApplicationMaterialAdapter wrappers;
- SQLite repositories and migrations;
- Dashboard API.

### Browser

- existing Fake PageController state-machine tests;
- JobsDB snapshot/characterization tests;
- real-login E2E tests remain opt-in and excluded by default.

### Acceptance

1. discover approximately 50 JobsDB jobs and complete JDs;
2. incrementally evaluate new or changed jobs;
3. render all results in the local Dashboard;
4. select jobs and generate versioned English packages;
5. perform second-level approval or feedback regeneration;
6. automatically execute one approved Quick Apply;
7. open the JobsDB detail page for one approved Apply;
8. record materials and results without duplicate submission.

## 14. Out of Scope for v1

- scheduled daily execution;
- GitHub Actions or cloud deployment;
- multi-user support;
- unattended API/headless agent driver;
- job discovery outside JobsDB;
- automatic application on external employer websites;
- Gmail, Notion, Telegram, or email synchronization;
- contact discovery, outreach, negotiation, and upskill modules;
- reimplementation of upstream adapter capabilities in Python.

## 15. Implementation Constraints

- Preserve the v2.0 BrowserPort, Fake implementations, factory DI, and application state
  machine.
- Extend rather than replace the existing tested Quick Apply path.
- Use migrations for all SQLite changes.
- Maintain a single system of record and a single Dashboard.
- Preserve existing untracked probe scripts; they are outside this design’s scope.
- Do not implement product changes until an implementation plan has been reviewed.

## 16. Completion Criteria

The first release is complete when:

- Claude Code and Codex can start the same skill-driven workflow;
- no scheduler or extra API key is required;
- interrupted workflows resume from persisted state;
- every evaluation and material package is versioned and auditable;
- no Quick Apply submits without second-level package approval;
- every execution-list job has an independent action;
- Apply opens the JobsDB detail page and remains a manual workflow;
- application materials cannot introduce unsupported candidate facts;
- automated and manual submissions record the approved material version and result.
