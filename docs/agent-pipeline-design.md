# Multi-Agent Requirements Pipeline — Design Spec (v0.1)

Scope of this document: agents **1 (Discovery)**, **2 (Requirements)**, **4 (Validator, deterministic + scoped LLM checks)** — the vertical slice we agreed to build first. Agents 3 (Artifacts) and 5 (Test Designer) get a short placeholder section at the end so the contracts stay extensible, and get their own detailed spec once the slice works and is evaluated.

---

## 0. Domain for the synthetic case (assumption — confirm or change)

**Chosen domain: Expense Reimbursement Request.** Reasoning: it has everything needed to exercise the pipeline (multiple stakeholders, an approval workflow with a real state machine, money with business rules, an audit need) without touching anything confidential, and it is close enough to the banking-flow thinking you already show in case 01 that the two portfolio pieces reinforce each other on a review.

Rough shape, so the schemas below make sense:

> *"Employees submit expense reports for reimbursement. Reports above a threshold need manager approval before Finance processes payment. Some categories (travel, client entertainment) have per-category limits and require a receipt above a certain amount."*

This is deliberately underspecified — the missing pieces (thresholds, currencies, what happens on rejection, who can override a limit) are exactly what Agent 1 should turn into open questions rather than invent. If you want a different domain, say so before we write code; the schemas are domain-agnostic, only the raw request text changes.

---

## 1. Shared conventions

- **Provenance discipline**, reused from case 06: every stakeholder, assumption, and requirement is either grounded in the input (`FACT`), a labeled deduction (`INFERENCE`, with a one-clause reason), or turned into an explicit open question instead of being guessed. There is no `UNKNOWN` marker on output items — `UNKNOWN` becomes an `open_question` / `open_item`, never a value written into a field.
- **All agent I/O is structured YAML**, not prose. An agent's entire response is one YAML document, nothing else — this is what makes Agent 4's checks mechanical instead of another LLM judgment call.
- **IDs are stable and referenced, never repeated as free text.** `FR-014` means the same object everywhere in the pipeline; nothing downstream re-describes a requirement without citing its ID.
- **Every run is a folder**, not an in-place mutation: `runs/<timestamp>/01-discovery.yaml`, `02-requirements.yaml`, `03-validation.yaml`, `answers.yaml`. Plain files, git-diffable, and the human-in-the-loop step (below) is just editing a file.

---

## 2. Pipeline shape

```text
raw_request.txt
      |
      v
 [Agent 1: Discovery]  (LLM call)
      |
      v
 01-discovery.yaml
      |
      |  <-- HUMAN CHECKPOINT: analyst answers/edits open_questions -->
      v
 answers.yaml  +  01-discovery.yaml
      |
      v
 [Agent 2: Requirements]  (LLM call)
      |
      v
 02-requirements.yaml
      |
      v
 [Agent 4a: Deterministic rule engine]  (plain Python, no LLM)
      |
      v
 candidate contradiction pairs (pre-filtered by shared actor/entity)
      |
      v
 [Agent 4b: Scoped LLM pairwise check]  (LLM call per pair)
      |
      v
 03-validation.yaml
```

The human checkpoint after Agent 1 is not optional scaffolding — it is the point of the design. A real analyst does not let Requirements get written against unanswered questions, and Agent 2's rules below make it structurally unable to do that (see "status: DRAFT" rule).

---

## 3. Agent 1 — Discovery

### Output schema (`01-discovery.yaml`)

```yaml
discovery:
  project_name: string
  raw_request: string          # verbatim copy of the input, for traceability
  stakeholders:
    - id: "STK-01"
      name: string              # role name, e.g. "Employee"
      interest: string          # what they need from the system
      marker: FACT | INFERENCE
      reason: string             # required if marker == INFERENCE, else omit
  scope:
    in_scope: [string]
    out_scope: [string]
  assumptions:
    - id: "ASM-01"
      text: string
      marker: INFERENCE          # assumptions are inferences by definition
      reason: string
  open_questions:
    - id: "OQ-01"
      question: string
      why_it_matters: string     # which future FR/NFR area this blocks
  glossary:
    - term: string
      definition: string
      marker: FACT | INFERENCE
```

### System prompt

```text
You are the Discovery Agent in a requirements-engineering pipeline.
Read the raw business request and produce ONLY a YAML document matching
the Discovery Output schema below. No text before or after the YAML.

Schema:
<paste the schema above>

Rules:
- Every stakeholder, assumption, and glossary term is marked FACT (stated
  explicitly in the request) or INFERENCE (a reasonable deduction you are
  making — you must give a one-clause reason). Never mark something FACT
  if it is not literally stated.
- Do not invent stakeholders, business rules, thresholds, or numbers that
  are not in the request and not a clearly labeled inference.
- If something is unclear or missing, put it in open_questions. Do not
  guess a value to fill a field instead.
- Every open question must state which future requirement area it blocks
  (why_it_matters), not just that something is unclear.
- If the request is unambiguous on a point, do not manufacture a question
  about it just to have more questions.
- IDs are sequential per section: STK-01, STK-02, ... ASM-01, ... OQ-01, ...

Raw request:
{raw_request}

Output the YAML now.
```

### Notes

- `reason` is required exactly when `marker: INFERENCE` — this is a schema-level rule Agent 4 checks deterministically (§5, rule R0).
- Expect roughly 4–8 open questions on the sample request in §0 (missing threshold amount, missing currency, what happens on rejection — resubmit or terminal, whether Finance can override a manager's approval, whether receipts are required below the limit for audit sampling).

---

## 4. Agent 2 — Requirements

### Input

`01-discovery.yaml` + `answers.yaml`:

```yaml
answers:
  - open_question_id: "OQ-01"
    answer: string        # or omitted / null if still unanswered
```

An unanswered question is a **first-class input state**, not an error — Agent 2 must handle it explicitly (see rules).

### Output schema (`02-requirements.yaml`)

```yaml
requirements:
  functional:
    - id: "FR-001"
      title: string
      description: string
      actor: "STK-01"                 # must exist in discovery.stakeholders
      trigger: string
      acceptance_criteria:
        - given: string
          when: string
          then: string
      priority: MUST | SHOULD | COULD
      source: "OQ-01" | "ASM-02" | "raw_request"   # traceability
      status: CONFIRMED | DRAFT       # DRAFT if it depends on an unanswered OQ
  non_functional:
    - id: "NFR-001"
      category: PERFORMANCE | AVAILABILITY | SECURITY | AUDITABILITY | USABILITY
      requirement: string
      metric: string                  # must be measurable, e.g. "p95 <= 2s"
      priority: MUST | SHOULD | COULD
  entities:
    - name: string
      description: string
      attributes:
        - name: string
          type: string
          required: boolean
  state_models:
    - entity: string                  # e.g. "ExpenseReport"
      values: [string]                # e.g. [SUBMITTED, APPROVED, REJECTED, PAID]
      transitions:
        - from: string
          to: string
          trigger: string
          guard: string | null
  open_items:
    - id: "OI-01"
      text: string
      blocks: ["FR-003"]              # which requirements stay DRAFT because of this
```

### System prompt

```text
You are the Requirements Agent. Input: the Discovery YAML and a set of
answers to its open questions (some may be unanswered). Produce ONLY a
YAML document matching the Requirements Output schema. No text before or
after the YAML.

Schema:
<paste the schema above>

Rules:
- Every FR's `actor` must be a stakeholder id that exists in the Discovery
  output. Do not introduce a new actor.
- Every FR has at least one acceptance criterion in Given/When/Then form.
- If a requirement depends on an open question that was NOT answered, do
  not guess the missing value. Write the requirement with status: DRAFT,
  leave the dependent detail as a placeholder in the description (e.g.
  "[pending OQ-03: reimbursement threshold]"), and add an open_item that
  lists it under `blocks`. Never mark a requirement CONFIRMED if it relies
  on an unanswered question.
- Every NFR's `metric` must be a measurable statement, not a vague
  adjective. "The system should be fast" is not acceptable; "p95 response
  time <= 2s under 50 concurrent users" is.
- Reuse entity and field names consistently. Do not introduce a second
  name for a concept that already has one (e.g. do not mix "Expense
  Report" and "Reimbursement Request" for the same entity).
- state_models must only be produced for entities that the discovery
  or the request clearly implies have a lifecycle with distinct states.
- Do not add requirements that are not implied by the discovery output
  or the given answers.

Discovery YAML:
{discovery_yaml}

Answers:
{answers_yaml}

Output the YAML now.
```

---

## 5. Agent 4 — Validator

Two layers, deliberately separated: **deterministic rules** (plain Python — fast, free, 100% reproducible, no LLM call) and a **scoped LLM check** used only for genuinely semantic judgments the code cannot make. This split is the answer to the case-06 lesson: don't ask an LLM to "check everything for consistency" — ask code to check what code can check, and give the LLM a narrow, bounded question for the rest.

### 5a. Deterministic rules (no LLM)

| Rule | Check | Severity |
|---|---|---|
| R0 | Every item marked `INFERENCE` has a non-empty `reason` | ERROR |
| R1 | Every FR's `actor` exists in `discovery.stakeholders` | ERROR |
| R2 | No two requirements share the same `id` | ERROR |
| R3 | Every `MUST`-priority FR has `status: CONFIRMED` only if none of its listed `source` open questions are unanswered in `answers.yaml` | ERROR |
| R4 | Every FR has at least one acceptance criterion | ERROR |
| R5 | Every NFR's `metric` matches a "measurable" pattern (contains a comparison operator or number + unit — regex-based heuristic, e.g. `<=|>=|\d+\s*(ms|s|%|req|users)`) | WARNING (heuristic, can false-positive) |
| R6 | Every `open_question` from Discovery that has no answer in `answers.yaml` appears in some `open_item.blocks` reference, OR was answered | ERROR — a dropped question is the single worst failure mode |
| R7 | Every `from`/`to` in a `state_models.transitions` entry exists in that entity's `values` list | ERROR |
| R8 | Every state in `values` is reachable from at least one transition's `from` (except the initial state) and every state (except terminal ones) has at least one outgoing transition | WARNING |
| R9 | Entity names referenced inside FR `description` text (simple capitalized-phrase match) exist in `entities` | WARNING — heuristic, flags likely-missing entities for human review |

Output of this layer feeds directly into `validation_report.issues` with `rule: "R3"` etc. — no LLM involved, fully unit-testable with seeded-error fixtures (see §6).

### 5b. Scoped LLM check — pairwise contradiction detection

Only run on **candidate pairs** pre-filtered by the deterministic layer (same `actor`, or same `entity` mentioned, or same NFR `category`) — this avoids O(n²) LLM calls over unrelated requirements and avoids the "explain everything at once" hallucination risk.

```text
You are the semantic consistency checker. You will be given exactly two
requirements. Decide only whether they contradict each other. Do not
comment on style, completeness, or anything else. Answer ONLY with YAML:

result: CONSISTENT | CONTRADICTION | UNCLEAR
reason: string   # one sentence, required only if result != CONSISTENT

Requirement A:
{requirement_a_yaml}

Requirement B:
{requirement_b_yaml}
```

Example of what this is meant to catch: FR-003 says "only the direct manager can approve reports over the threshold"; FR-011 (added later, referencing the same actor category) says "Finance can approve any report regardless of amount." Neither rule R0–R9 catches this — it is not a structural violation, it is a business-logic contradiction, which is exactly the class of error that needs a bounded, scoped LLM call rather than a keyword rule.

### Output schema (`03-validation.yaml`)

```yaml
validation_report:
  generated_at: timestamp
  rules_run: [R0, R1, ... ]
  issues:
    - id: "ISS-001"
      severity: ERROR | WARNING
      rule: "R3" | "LLM-pairwise"
      message: string
      refs: ["FR-014", "STK-02"]
  summary:
    errors: int
    warnings: int
```

---

## 6. Evaluation plan (numbers we will actually measure, not TODO-FILL)

Two separate evaluations, matched to the two layers:

**Deterministic layer (R0–R9):** unit tests with seeded-error fixtures. Take one clean `02-requirements.yaml`, produce one mutated copy per rule (e.g. delete an acceptance criterion to trigger R4, rename a transition target to break R7), assert the rule engine flags exactly that issue and nothing else. This should be 100% precision/recall by construction — if it isn't, the rule is buggy, not "the AI got it wrong." This is standard unit testing, cheap to run, goes in the PoC's test suite the same way the outbox tests did.

**LLM pairwise layer:** build ~15–20 requirement pairs by hand (half genuinely contradictory, half consistent-but-related), run them through the scoped prompt, and report real precision/recall — this is small enough to actually run today, unlike the 30-task evaluation we deferred in case 06's `evaluation.md`. This closes that gap with real numbers instead of "not measured."

---

## 7. Agents 3 and 5 — placeholder contracts (detailed spec later)

So the pipeline stays extensible without redesigning the earlier contracts:

- **Agent 3 (Artifacts)** will consume `02-requirements.yaml` only — never free text — and emit Mermaid/PlantUML source where every diagram element carries a comment citing the FR/NFR/entity ID that produced it (e.g. `state APPROVED : from FR-004`). This is what makes Agent 4's future diagram-consistency checks (extending R1–R9) mechanical instead of another LLM judgment call.
- **Agent 5 (Test Designer)** will consume `02-requirements.yaml` + Agent 3's state models, and emit test cases with an explicit `covers: [FR-004, transition SUBMITTED->APPROVED]` field, so coverage of FR/NFR and of state transitions can be computed automatically rather than estimated.

Both get their own schema-and-prompt spec once the 1→2→4 slice is built, tested, and evaluated with real numbers.

---

## 8. Open items before writing code

1. Confirm or change the domain in §0.
2. Confirm the model to target for the LLM calls (affects prompt tuning — e.g. whether we need stricter "no prose" instructions for some models).
3. Decide the orchestrator's shape: a plain CLI script (`python run_pipeline.py --step discovery`) is enough for the PoC; no need for a workflow engine here — that would be ironic given ADR-004's own rule (this pipeline doesn't wait long, has no human-task duration measured in hours, and doesn't need compensation logic).
