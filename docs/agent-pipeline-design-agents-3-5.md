# Multi-Agent Pipeline — Agents 3 & 5 Spec (v0.1)

Extends `agent-pipeline-design.md` section 7. Read that first — this document assumes the same conventions (structured-YAML-only I/O, FACT/INFERENCE discipline, ID-based traceability, deterministic-over-LLM wherever possible).

## 0. The key design decision: split both agents into a deterministic half and an LLM half

The same lesson from Agent 4 applies here even more strongly: `requirements.yaml` from Agent 2 already contains a fully structured `state_models` block and `acceptance_criteria` per FR. A large share of what Agents 3 and 5 need to produce is a **mechanical transformation of data that already exists and was already validated** — not something that needs an LLM to invent. Asking an LLM to redraw a state diagram from a state machine that's already fully specified is pure hallucination risk for zero benefit.

So each agent is split:

| | Deterministic (no LLM, no hallucination risk) | LLM-assisted (genuine judgment needed) |
|---|---|---|
| **Agent 3 — Artifacts** | ER diagram (from `entities`), state diagram (from `state_models`), process skeleton (from `state_models` + FR triggers, swimlanes assigned by matching `trigger` names to FR `actor`) | Component diagram (system decomposition isn't in the requirements data — needs inference), sequence diagram (interaction *ordering* for a scenario isn't explicit either) |
| **Agent 5 — Test Designer** | One positive test per acceptance criterion, one positive + N negative tests per state transition (negative = every transition NOT in the declared transition list from that `from` state) | Concrete example test data (realistic values), additional boundary/edge cases beyond the literal acceptance criteria |

Every LLM-produced diagram element or test case still **cites the FR/NFR/entity ID it comes from**, directly in the artifact (Mermaid edge labels carry `(FR-004)`-style citations; test cases carry a `covers: [...]` field) — this is what lets Agent 4's extended rules check LLM output the same mechanical way it checks Agent 2's output.

---

## 1. Agent 3a — Deterministic renderer (no LLM)

### Input
`02-requirements.yaml` only (must have zero ERROR-severity issues from Agent 4a — this is a hard precondition, enforced by the orchestrator, not a suggestion: rendering diagrams from unvalidated requirements just propagates the same errors into three more artifacts).

### Output: `03a-deterministic-artifacts.yaml`

```yaml
deterministic_artifacts:
  er_diagram:
    mermaid: string          # Mermaid erDiagram, one block per entity, FK inferred
                              # from attribute names ending in "_id" that match
                              # another entity's lowercased name
  state_diagrams:
    - entity: string
      mermaid: string         # direct transpile of state_models[entity] -- 1:1, lossless
  process_skeleton:
    - entity: string
      mermaid: string         # flowchart with each transition labeled
                               # "{trigger} ({FR-id}) [{actor_name}]"
      unmatched_transitions:  # transitions whose trigger matched no FR -- always
        - trigger: string     # reported, never silently dropped (mirrors R6's
                                # "don't silently drop" principle from Agent 4)
```

### Matching rule (trigger → FR → actor)

For each `state_models[].transitions[]` entry, search `requirements.functional` for an FR whose `trigger` field equals the transition's `trigger` (exact string match — this is why Agent 2's prompt requires the FR `trigger` field to reuse the same trigger vocabulary as future state model triggers; both come from the same agent so this is enforceable). If found, label the edge with that FR's `id` and its actor's name (looked up from `discovery.stakeholders`). If not found, the transition still renders (never silently dropped) but is also listed in `unmatched_transitions` so Agent 4 can flag it (rule R12, §3).

### Why this part needs zero prompt

There is no prompt here — `entity_render.py` is plain Python. This is the point: nothing here can hallucinate, because nothing here decides anything; it only reformats data Agent 2 already produced and Agent 4a already validated.

---

## 2. Agent 3b — LLM-assisted diagrams

### Input
`02-requirements.yaml` + `03a-deterministic-artifacts.yaml` (so the LLM sees the entities and states already established, and doesn't reinvent them — it only adds component structure and interaction order).

### Output schema (`03b-llm-artifacts.yaml`)

```yaml
llm_artifacts:
  component_diagram:
    mermaid: string      # Mermaid graph/flowchart; every node and edge label that
                          # represents a requirement cites it: "handles report
                          # submission (FR-001)"
    covers: ["FR-001", "NFR-001", ...]     # every FR/NFR id cited anywhere in the diagram
  sequence_diagram:
    scenario: string                        # one sentence: which flow this illustrates
    covers: ["FR-002", "FR-004", ...]       # FRs whose trigger/acceptance criteria this sequence enacts
    mermaid: string
```

### System prompt

```text
You are the Artifacts Agent (LLM half). You will be given validated
requirements and already-generated entity/state diagrams. Produce ONLY a
YAML document matching the schema below. No text before or after the YAML.

Schema:
<paste schema above>

Rules:
- Do not redraw the ER diagram or state diagram -- they already exist and
  are correct by construction. Your job is the component diagram (system
  decomposition: which components exist and how they connect) and one
  sequence diagram (the interaction order for one representative scenario).
- Every node or edge in the component diagram that implements a
  requirement must cite that requirement's ID directly in its Mermaid
  label text, e.g. |"submits report (FR-001)"|. Do not cite an ID that
  is not in the given requirements.
- The sequence diagram must pick ONE scenario (state which one in
  `scenario`) and its `covers` list must be the FRs whose trigger or
  acceptance criteria that scenario actually enacts -- not every FR in
  the system.
- If you are not confident a component is implied by the requirements
  (rather than a reasonable but unstated architectural choice, e.g. "a
  message queue"), you may still include it, but do not cite a
  requirement ID next to it -- an uncited element is understood as your
  own architectural judgment, not something the requirements demanded.
- Valid Mermaid syntax only. No prose commentary inside the mermaid block.

Requirements:
{requirements_yaml}

Deterministic artifacts already produced:
{deterministic_artifacts_yaml}

Output the YAML now.
```

---

## 3. Agent 4 extension — rules R10–R13 (artifact validation)

All still deterministic, still no LLM — they check the *citations* the LLM artifacts made against data that is known to be true, which is a mechanical string/set operation, not a judgment call.

| Rule | Check | Severity |
|---|---|---|
| R10 | Every FR/NFR id cited inline in `component_diagram.mermaid` or `sequence_diagram.mermaid` (regex `\(FR-\d+\)` / `\(NFR-\d+\)`) exists in `requirements.functional`/`non_functional` | ERROR — a cited ID that doesn't exist is a hallucinated citation, the most serious failure mode for this agent |
| R11 | Every id in `covers` for either LLM artifact actually appears inline in that artifact's own `mermaid` text (catches a `covers` list that doesn't match what was actually drawn) | ERROR |
| R12 | Every `deterministic_artifacts.process_skeleton[].unmatched_transitions` entry is surfaced as an issue (never silently rendered-and-forgotten) | WARNING |
| R13 | Every `MUST`-priority `CONFIRMED` FR is cited by at least one of: process_skeleton, component_diagram, sequence_diagram | WARNING — a MUST requirement with zero diagram representation is a coverage gap worth a human look, not necessarily wrong |

---

## 4. Agent 5a — Deterministic test generator (no LLM)

### Input
`02-requirements.yaml` (validated, same precondition as Agent 3a).

### Output: `05a-deterministic-tests.yaml`

```yaml
deterministic_tests:
  - id: "TC-001"
    type: POSITIVE
    covers: ["FR-001"]
    source: acceptance_criterion            # or "transition"
    given: string           # copied from the FR's acceptance_criteria
    when: string
    then: string
  - id: "TC-014"
    type: NEGATIVE
    covers: ["Expense Report"]              # entity name, for transition-sourced cases
    source: transition
    given: "Expense Report is in state PAID"
    when: "manager_rejects is attempted"     # a trigger NOT in PAID's declared transitions
    then: "the transition is rejected (INVALID_STATE_TRANSITION); state remains PAID"
```

### Generation rules

- One `POSITIVE` test per `acceptance_criteria` entry across all FRs, `source: acceptance_criterion`, `covers: [FR-id]`.
- One `POSITIVE` test per declared state transition, `source: transition`, `covers: [entity name]`, given/when/then built directly from `from`/`trigger`/`to`.
- One `NEGATIVE` test per **disallowed** transition: for every state in `values`, for every trigger that appears somewhere in the entity's transitions but is not a valid outgoing trigger from that state, generate a rejection test case. This is exactly the same idea already proven in the `outbox-poc`'s `test_invalid_transition_is_rejected` — here it's generated systematically instead of hand-written once.

This part needs no prompt, for the same reason as Agent 3a: it only reformats already-validated structured data.

---

## 5. Agent 5b — LLM-assisted test data & edge cases

### Input
`02-requirements.yaml` + `05a-deterministic-tests.yaml`.

### Output schema (`05b-llm-tests.yaml`)

```yaml
llm_tests:
  example_data:
    - test_id: "TC-001"                     # must reference a deterministic_tests id
      data: {employee_id: "EMP-1042", amount: "612.40", currency: "USD", category: "travel"}
  edge_cases:
    - id: "TC-201"
      type: EDGE | NEGATIVE
      covers: ["FR-002"]                     # must be an existing FR/NFR/entity id
      given: string
      when: string
      then: string
      reason: string                          # why this is a meaningful edge case, one sentence
```

### System prompt

```text
You are the Test Designer Agent (LLM half). You are given validated
requirements and a set of already-generated deterministic test case
skeletons. Produce ONLY a YAML document matching the schema below.

Schema:
<paste schema above>

Rules:
- For `example_data`: invent realistic, concrete example values for each
  deterministic test case's `given`/`when` fields (e.g. actual amounts,
  IDs, categories) -- these are illustrative examples, not real user data.
  Every test_id must match an id that exists in the deterministic test
  list given to you.
- For `edge_cases`: propose additional boundary and negative cases the
  deterministic list does not already cover -- e.g. a value exactly at a
  stated threshold, a value one unit below/above it, an empty/missing
  required field, a duplicate submission. Every edge case's `covers` must
  cite an FR, NFR, or entity id that exists in the given requirements. Do
  not invent a business rule that is not implied by the requirements --
  if a genuinely useful edge case cannot be derived from anything given
  (e.g. "what if two currencies are mixed" when the requirements assume a
  single currency), do not include it.
- Give a one-sentence `reason` for every edge case: why this is worth
  testing, not just that it exists.

Requirements:
{requirements_yaml}

Deterministic test skeletons:
{deterministic_tests_yaml}

Output the YAML now.
```

---

## 6. Agent 4 extension — rules R14–R16 (test validation)

| Rule | Check | Severity |
|---|---|---|
| R14 | Every `covers` id across deterministic and LLM test cases exists in requirements (FR/NFR id or entity name) | ERROR |
| R15 | Every `example_data.test_id` and every `edge_cases` entry referencing a `test_id` exists among the deterministic test ids | ERROR |
| R16 | Every `MUST`-priority `CONFIRMED` FR has at least one covering test case (deterministic or LLM) | WARNING |
| R17 | Every declared state transition has at least one covering test case | WARNING — this should in practice never fire, since 5a generates one by construction; if it fires, it means 5a itself has a bug, which is a useful self-check |

---

## 7. Evaluation plan for this pair

Same split as Agent 4: the deterministic halves (3a, 5a) get seeded-error/regression unit tests with 100% expected pass, same methodology as `test_rules_seeded_errors.py`. The LLM halves (3b, 5b) get real, run evaluation once built:

- **Agent 3b:** hand-build 5–8 requirement sets with a known "right" component decomposition (or at least a known-wrong one to seed), check citation validity (R10/R11) catches injected bad citations — this is really testing the *validator* against seeded LLM mistakes, the same pattern as the R0–R9 seeded tests, just applied to artifact output instead of requirements output.
- **Agent 5b:** the interesting metric is not "did it get the right answer" (there often isn't one right edge case) but **coverage and validity**: of N edge cases proposed, what fraction cite a real requirement (R14 catches invalid ones automatically) and, on manual review, how many are genuinely useful vs. redundant with the deterministic list. This is closer to a precision judgment than the crisp CONTRADICTION/CONSISTENT labels used for Agent 4b, so it is reported as a qualitative sample review rather than forced into a single accuracy number.

---

## 8. What stays true from the earlier design

- All I/O is still structured YAML, still ID-referenced, still FACT/INFERENCE-disciplined where judgment is involved.
- The orchestrator is still a plain CLI, extended with two more steps (`artifacts`, `testdesign`), still no workflow engine — the same ADR-004 reasoning applies.
- Numbers are never fabricated in this document or the code that follows it: where something needs to be measured, it says so and gets a real runner, not a placeholder.
