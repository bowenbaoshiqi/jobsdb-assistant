# Career-Ops Native Profile Bundle Design

**Status:** Implemented and verified
**Date:** 2026-07-27  
**Target release:** v0.3.0 completion

## 1. Outcome

`jobsdb-assistant` will use `ai-job-search` to extract a CV and conduct the
candidate interview, store the result in one canonical typed candidate
profile, and deterministically project that profile into the native files
consumed by the pinned `career-ops` fork:

```text
CV + ai-job-search extraction + interactive interview
                         │
                         ▼
              Canonical CandidateProfile
                         │
                         ▼
              CareerOpsProfileAdapter
                  ├── cv.md
                  ├── config/profile.yml
                  ├── modes/_profile.md
                  └── projection-manifest.json
                         │
                         ▼
                 career-ops native modes
```

The two forks remain unmodified, read-only integrations pinned to their
current commit SHAs.

## 2. Current Gap

The current evaluation adapter embeds a custom `CandidateProfile` JSON object
in each evaluation task. The active Agent reads career-ops scoring
instructions and interprets that JSON ad hoc.

This is not career-ops' native data boundary. The pinned fork declares these
files as its candidate sources of truth:

- `cv.md`, always;
- `config/profile.yml`, always;
- `modes/_profile.md`, always;
- optional supporting sources such as `article-digest.md`,
  `writing-samples/`, and interview-prep files when they actually exist.

Because the main application does not currently generate the three required
files, career-ops-native fields such as `target_roles`, `compensation`,
`location`, `culture_screen`, North Star archetypes, and narrative can be
absent even when the user supplied equivalent information in conversation.

## 3. Design Principles

1. Python, not Agent memory, owns candidate state.
2. User answers are preserved exactly and cannot be discarded by an Agent
   summary.
3. The Agent performs one bounded synthesis pass; it is not repeatedly asked
   to improve an unconstrained narrative.
4. The career-ops projection is deterministic and contains no new inference.
5. Missing, `not_provided`, and `no_preference` values remain explicit and
   are never guessed.
6. career-ops consumes its native file format and keeps its native scoring.
7. All candidate files remain private runtime data below ignored
   `workspace/`.

## 4. Canonical Candidate Profile

The existing free-form profile is expanded into two typed sections.

### 4.1 Evidence-backed CV data

`CandidateCv` contains:

- identity and contact fields, each optional;
- professional headline and summary;
- ordered work experience with role, employer, dates, location, and bullets;
- ordered education;
- categorized technical and domain skills;
- projects;
- certifications;
- publications;
- awards;
- languages;
- quantified proof points.

Every factual leaf must retain source evidence. Unsupported fields are absent,
not inferred.

### 4.2 Candidate intent

`CandidateIntent` contains exactly the interview dimensions:

- behavioral style;
- career goals;
- next-role motivators;
- must-haves;
- deal-breakers;
- salary expectations;
- references policy.

Each item stores:

- stable dimension ID;
- answer status: `answered`, `not_provided`, or `no_preference`;
- exact raw answer when answered;
- SHA-256 of the raw answer;
- one Agent-generated structured synthesis;
- the canonical profile field into which it was incorporated.

Python writes the raw answer and hash. The Agent may only supply the synthesis.
For every answered dimension, a non-empty synthesis and correct target field
are mandatory. Missing or mismatched dimensions make the proposal invalid.

The canonical profile is immutable after confirmation. An update creates the
next profile version.

## 5. One-Pass ai-job-search Synthesis

After the user completes the interview:

1. Python creates a follow-up task containing the evidence-backed CV
   extraction and the complete typed answer set.
2. The Agent reads only the pinned ai-job-search onboarding capabilities and
   returns:
   - the typed `CandidateCv`;
   - a synthesis for every answered intent dimension;
   - target-role archetypes and evidence-backed proof-point selection.
3. Python validates dimension coverage and answer hashes.
4. Python injects the exact raw answers into `CandidateIntent`; the Agent
   cannot rewrite them.
5. The complete proposal is shown to the user.
6. Explicit confirmation creates the immutable profile.

Normal operation uses one synthesis call. A schema-invalid result may receive
one bounded correction attempt. There is no open-ended quality loop.

## 6. Career-Ops Native Projection

The bundle root is:

```text
workspace/career-ops-profiles/<profile-content-hash>/
```

The directory is prepared atomically and is immutable once complete.

### 6.1 `cv.md`

Rendered deterministically from `CandidateCv`:

- summary;
- experience;
- education;
- skills;
- projects;
- certifications;
- publications;
- awards;
- languages.

Bullets and metrics retain the confirmed wording. The renderer does not
tailor, embellish, or add keywords for a particular JD.

### 6.2 `config/profile.yml`

Rendered using the pinned career-ops schema:

- `candidate`: confirmed identity and available contact data;
- `target_roles.primary`: confirmed target roles;
- `target_roles.archetypes`: confirmed role direction, level, and fit;
- `narrative.headline`: confirmed professional headline;
- `narrative.superpowers`: evidence-backed core strengths;
- `narrative.proof_points`: confirmed quantified achievements;
- `compensation`: only when answered;
- `location`: confirmed geography, flexibility, and constraints;
- `language.output`: confirmed output language;
- `culture_screen.require`: structural must-haves that career-ops natively
  evaluates as culture criteria.

Generator or model-routing preferences such as `spend_tier` are not candidate
facts and are not invented by this projection. career-ops defaults remain in
effect unless the user separately configures them.

### 6.3 `modes/_profile.md`

Rendered from confirmed intent and narrative:

- North Star roles and archetypes;
- career goals;
- next-role motivators;
- professional narrative;
- behavioral and collaboration style;
- must-haves;
- deal-breakers;
- proof-point framing;
- writing style, when confirmed;
- references policy.

It does not contain procedural instructions that belong in `_custom.md`.

### 6.4 Optional native sources

The projection does not create empty or fabricated optional sources. It emits
`article-digest.md`, writing samples, voice DNA, or interview story-bank files
only in a later capability when equivalent user-provided sources have been
validated. Their absence is native career-ops behavior.

## 7. Projection Manifest and Completeness

`projection-manifest.json` is a private Python audit file, not a career-ops
input. It records:

- canonical profile ID, version, and content hash;
- candidate-profile integration SHA;
- career-ops integration SHA;
- projection contract version;
- output file paths and SHA-256 hashes;
- source field for every emitted profile.yml key and Markdown section;
- interview dimension and raw-answer hash for each synthesized intent section;
- explicit omitted fields with reason:
  `missing`, `not_provided`, or `no_preference`.

Bundle generation fails if:

- an answered intent dimension is not represented;
- an emitted factual value lacks evidence;
- an output contains an unresolved placeholder;
- a file hash does not match the manifest;
- the target directory escapes the private workspace root.

## 8. Evaluation Consumption

`JobEvaluationTask` stops asking the Agent to interpret the custom profile
JSON. It carries:

- confirmed profile ID and version;
- canonical profile hash;
- bundle hash and projection contract version;
- exact private paths to `cv.md`, `config/profile.yml`, and
  `modes/_profile.md`;
- the existing pinned career-ops capability paths;
- one immutable JD snapshot.

The jobsdb-assistant skill instructs the Agent to load the native bundle in
career-ops' documented order. career-ops then applies its existing A-F and
overall scoring without custom weights or score fusion.

The evaluation cache key adds the bundle hash and projection contract version.
Changing candidate data or mapping behavior invalidates only affected cached
evaluations.

## 9. Privacy and Fork Isolation

- Bundles and manifests are ignored private runtime data.
- No candidate content is written below `integrations/`.
- No bundle is committed, uploaded by CI, logged in full, or included in test
  evidence.
- Synthetic fixtures are used for tests.
- Contact fields required by later application modes may exist in the private
  bundle, but evaluation reports never display them.
- Integration validation continues to reject a wrong-SHA fork; bundle
  generation never writes into an integration checkout.

## 10. Compatibility and Upgrade Strategy

The projection contract is versioned independently from both forks.

For the current pinned career-ops SHA, golden compatibility tests verify:

- supported top-level `profile.yml` keys;
- required Markdown sections;
- absence of placeholders;
- deterministic output and file hashes;
- task paths and bundle hashes;
- unchanged native A-F result validation.

When career-ops is upgraded, the lock SHA and projection contract are changed
on a dedicated branch. Golden projection tests must pass before merge.

An existing confirmed profile without typed interview intent is not silently
backfilled. The current incomplete v1 remains historical. The user explicitly
runs profile update, reviews the complete proposal, and confirms v2; only then
is the native bundle generated and used for new evaluations.

## 11. Error Handling

- Invalid Agent synthesis remains a failed private checkpoint and does not
  modify the active profile.
- Projection failure prevents new evaluation tasks and provides an actionable
  field/path error.
- A missing or damaged bundle is rebuilt only from the same confirmed
  canonical profile and pinned projection version.
- A bundle hash mismatch stops evaluation rather than silently regenerating
  different content.
- One job-evaluation failure does not affect other jobs or the profile bundle.

## 12. Testing

### Domain and onboarding

- raw answers survive Agent synthesis byte-for-byte;
- every answered dimension requires a synthesis and correct mapping;
- explicit skip statuses remain explicit;
- unsupported factual fields are rejected;
- confirmed profiles are immutable.

### Projection

- deterministic synthetic `cv.md`;
- safe deterministic `profile.yml`;
- deterministic `_profile.md`;
- full manifest source mapping and hashes;
- missing/not-provided/no-preference handling;
- atomic private output and traversal rejection;
- fork directories remain unchanged.

### Evaluation

- tasks contain only native bundle references plus profile identity/hash;
- bundle changes invalidate evaluation cache;
- career-ops native A-F output remains unchanged;
- reporting and application execution behavior remain unchanged.

### Regression

Run focused tests first, then lint, all non-E2E tests, branch coverage,
privacy guard, skill validation, and diff checks. Total coverage remains at
least 80%.

## 13. Non-Goals

- Modifying either fork.
- Changing career-ops dimensions, weights, or overall score.
- Generating tailored application materials in this change.
- Building the Dashboard in this change.
- Inferring optional candidate information.
- Creating optional career-ops source files without matching user evidence.
