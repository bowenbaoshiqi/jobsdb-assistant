# Candidate Interview Gate Design

**Status:** Approved design, pending written-spec review  
**Date:** 2026-07-24  
**Target release:** v0.3.0 corrective change

## 1. Problem

The v0.3 candidate-profile checkpoint accepts either `questions` or a
`proposal`, but Python does not enforce when each result is legal. During the
first real single-CV run, the agent returned a proposal immediately. That
output was schema-valid but violated the pinned `ai-job-search` Path B
workflow, which requires follow-up questions for gaps before profile
generation.

Supporting questions is insufficient. The deterministic Python workflow must
prevent a first-run CV import from becoming a proposal until the required
interview dimensions have been answered or explicitly skipped.

## 2. Outcome

For a first-run single-CV import:

1. Python creates a profile task that requires an interview.
2. The agent extracts only evidence-backed CV facts and returns questions
   mapped to required interview dimensions.
3. Python validates that every required dimension is represented.
4. The user answers each question or explicitly declines to provide a value.
5. Python creates a follow-up profile task containing those answers.
6. The agent may then return a proposal.
7. Python validates the proposal and waits for explicit user confirmation.
8. Only a confirmed profile can be used for job evaluation.

The two pinned forks remain unmodified. The candidate adapter continues to use
the locked `ai-job-search` capability files.

## 3. Required Interview Dimensions

The fixed first-run dimensions are:

- `behavioral_style`: preferred working, decision, communication, and team
  style;
- `career_goals`: target direction and role scope;
- `next_role_motivators`: what the candidate wants from the next role;
- `must_haves`: non-negotiable requirements;
- `deal_breakers`: conditions or environments to avoid;
- `salary_expectations`: optional compensation expectations;
- `references`: optional professional references.

Every dimension must receive an answer. The answer may explicitly be
`not_provided` or `no_preference`; these are complete answers, not missing
answers. Python must not infer a private or behavioral value from silence.

The already supplied search keyword remains valid input for `target_roles`,
but it does not satisfy the broader `career_goals` interview dimension.

## 4. Selected Architecture

### 4.1 Python owns interview completeness

Python defines the dimension IDs, validates question coverage, stores answers,
and decides whether a proposal is legal. This keeps workflow advancement
deterministic.

### 4.2 Agent owns conversational wording

The agent reads the pinned `ai-job-search` onboarding instructions and the
source CV, then writes concise, candidate-aware questions for the required
dimensions. Python does not hard-code awkward questionnaire copy.

### 4.3 Contract changes

The `questions` result becomes a collection of typed items:

```json
{
  "kind": "questions",
  "task_id": "profile-...",
  "questions": [
    {
      "dimension": "behavioral_style",
      "prompt": "What working and communication style helps you perform best?",
      "optional": false
    }
  ]
}
```

The answer payload is keyed by dimension rather than question text:

```json
{
  "behavioral_style": {
    "status": "answered",
    "value": "..."
  },
  "salary_expectations": {
    "status": "not_provided"
  }
}
```

Allowed answer statuses are `answered`, `not_provided`, and `no_preference`.
`answered` requires a non-empty value. The two explicit skip statuses do not.

The follow-up task carries the validated structured answers and an
`interview_complete` state derived by Python. The agent cannot set this state.

## 5. State and Validation Rules

### 5.1 First task

When a first-run task has one or more source documents and no interview
answers:

- `questions` is the only legal result;
- all required dimensions must occur exactly once;
- unknown, duplicated, or missing dimensions are rejected;
- a proposal is rejected before any proposal is persisted.

### 5.2 Answer submission

- answers must cover every required dimension exactly once;
- empty `answered` values are rejected;
- explicit skip statuses are accepted;
- raw question wording is not used as a persistence key;
- successful validation creates the follow-up agent task.

### 5.3 Follow-up task

When all interview dimensions are complete:

- a proposal is legal;
- another `questions` result may be allowed only for evidence clarification,
  but it cannot erase or replace validated interview answers;
- every verified profile fact still requires source evidence;
- the proposal remains inactive until explicit user confirmation.

### 5.4 Other onboarding paths

- An existing active profile remains reusable without a new interview.
- An explicit profile update follows the same interview gate when new source
  documents are supplied.
- Interview-only onboarding, with no source document, uses the same dimension
  contract and begins with questions.
- No behavior changes are introduced for discovery, evaluation, reporting, or
  application execution.

## 6. Error Handling and Recovery

Contract violations return actionable validation errors naming the missing,
duplicate, or invalid dimensions. They do not create a proposal or active
profile.

The current unconfirmed real-run proposal is treated as invalid runtime state.
After the corrective code is verified, its private checkpoint/proposal state
will be retired using a narrowly scoped recovery operation, and the same
resume will start a new run through the interview gate.

No source PDF, extracted text, checkpoint payload, or candidate answers may be
committed or printed in public test evidence.

## 7. Compatibility

The result contract changes from question strings to typed question items and
structured answers. This is an intentional corrective contract revision.
Repository-local CC and Codex skill instructions and CLI examples must be
updated together.

The manifest's pinned fork SHA does not change. The main-project adapter
contract version must change so cached or resumed v1 checkpoint payloads are
not mistaken for the corrected protocol.

Existing confirmed candidate profiles remain readable. Only unfinished
candidate onboarding checkpoints use the revised contract.

## 8. Test Design

### Unit guarantees

- First-run CV task rejects an immediate proposal.
- First-run task rejects incomplete, duplicate, and unknown question
  dimensions.
- Complete typed questions transition to `needs_answers`.
- Answers reject missing dimensions and empty `answered` values.
- `not_provided` and `no_preference` count as completed answers.
- A proposal is accepted only after Python-derived interview completion.
- Verified facts without evidence remain rejected.
- Existing active profiles are reused without new tasks.
- Explicit updates with new source documents require the interview gate.

### Integration and CLI guarantees

- Profile prepare, question submit, answer submit, proposal submit, and
  confirmation form one resumable workflow.
- CLI JSON exposes typed questions without leaking source document contents.
- Old unfinished v1 result payloads fail with an actionable contract-version
  message.
- Job evaluation cannot start without a confirmed profile.

### Regression

Run the focused onboarding and workflow tests first, then the full unit,
integration, lint, privacy, and coverage gates. Overall coverage remains at
least 80%.

## 9. Non-Goals

- Modifying either fork.
- Adding a model provider or API key.
- Generating tailored resumes or cover letters.
- Connecting profile evaluation to application execution.
- Inferring sensitive preferences from the CV.
- Building a general-purpose survey engine.
