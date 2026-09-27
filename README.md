# Requirements Pipeline — Agents 1, 2, 3, 4, 5 (Proof of Concept)

Companion project for [Case 06 — AI-assisted system analysis](https://github.com/konstantin-kuzovkin/architecture-portfolio/blob/main/06-ai-assisted-system-analysis/README.md)
in the main portfolio: a working, tested implementation of a multi-agent
requirements pipeline for the kind of system-analysis automation that case
describes.

The full pipeline from `docs/agent-pipeline-design.md` and
`agent-pipeline-design-agents-3-5.md`: **Discovery → Requirements →
Artifacts → Test Design → Validate**, with a human checkpoint after
Discovery. Agents 3 and 5 each split into a deterministic half (no LLM,
mechanically derived from already-validated data) and an LLM half
(genuine judgment: component/sequence diagrams, example test data and
edge cases) — see the design doc for the reasoning.

## What is real here and what isn't

This was built in a sandbox with **no network access**, so nothing in this
repository has made a real call to an LLM. Two things follow from that,
and both matter if you're evaluating this as a portfolio piece:

1. **Every deterministic layer is fully real and fully tested:** the rule
   engine (Agent 4a, rules R0–R9), the ER/state/process-skeleton renderer
   (Agent 3a), the acceptance-criteria and state-transition test generator
   (Agent 5a), and the citation/coverage checks over artifacts and tests
   (Agent 4, rules R10–R17). 39 unit tests total, seeded-error and
   correctness methodology, all passing, zero LLM calls involved. Run
   `python3 -m unittest discover -s tests -v` yourself.
2. **Agent 1, Agent 2, Agent 3b, Agent 5b, and the LLM half of Agent 4
   (4b) are wired up and ready to run against a real model, but have not
   been run against one yet.** `demo.py` proves the full orchestration and
   validation logic work end to end, using hand-written recorded fixtures
   instead of live model calls -- that is explicitly *not* a claim about
   model output quality. The fixtures for Agent 3b and 5b each contain two
   deliberately planted mistakes (a hallucinated citation, a
   covers/content mismatch, a bad cross-reference) specifically so the
   demo proves the extended validator catches them. To get real agent
   output and real evaluation numbers, run this yourself with an API key
   (see "Running for real" below). `eval/run_eval.py --dry-run` proves the
   evaluation harness's arithmetic is correct; it does not measure a model.

If you publish this in your portfolio, keep that distinction explicit —
it is exactly the mistake that was corrected in the `evaluation.md` of the
"AI-assisted system analysis" case: don't let a demo that proves the
plumbing works get read as a claim about model accuracy.

## Quick start (offline, no API key needed)

```bash
python3 demo.py                                # narrated walkthrough, all 5 agents, fixture LLM output
python3 -m unittest discover -s tests -v        # 39 tests across every deterministic layer
python3 eval/run_eval.py --dry-run              # sanity-checks the eval harness's math only
```

## Running for real

```bash
pip install anthropic pyyaml
export ANTHROPIC_API_KEY=sk-...

python3 run_pipeline.py discovery --request raw_request.txt --out runs/demo1
# edit runs/demo1/answers.yaml by hand -- this is the human checkpoint
python3 run_pipeline.py requirements --run-dir runs/demo1
python3 run_pipeline.py validate     --run-dir runs/demo1     # R0-R9 + LLM pairwise
python3 run_pipeline.py artifacts    --run-dir runs/demo1     # Agent 3: diagrams
python3 run_pipeline.py testdesign   --run-dir runs/demo1     # Agent 5: test cases
python3 run_pipeline.py validate     --run-dir runs/demo1     # re-run: adds R10-R17

python3 eval/run_eval.py            # real precision/recall for the pairwise checker
```

## What this proves and what it deliberately doesn't

| Proven by a real, run test | Not attempted here |
|---|---|
| The rule engine catches each of R0–R17's violation class, on clean baselines that produce zero false positives | Prompt tuning / iteration against a real model's actual failure modes -- fixtures are hand-written to be plausible, not observed |
| The ER/state-diagram renderer is a faithful, lossless transpile, and terminal-state detection is computed from the real transition graph, not guessed from state names (a real bug caught and fixed during development) | Rendering diagrams for a domain messier than this one synthetic example -- e.g. multiple interacting entities, cross-entity state dependencies |
| The state-transition test generator produces exactly one positive test per declared transition and one negative test per (state, disallowed-trigger) pair, with no gaps and no duplicate ids | Running the generated test suite against an actual implementation -- these are test *specifications*, not executable tests (unlike `outbox-poc`, which is executable) |
| The eval harness's precision/recall math is correct | Real accuracy numbers for the LLM layers (requires you to run it with a key) |
| The orchestration (discovery → human checkpoint → requirements → artifacts → testdesign → validate) runs end to end without crashing, on realistic fixture data | Any claim that Agent 1/2/3b/5b's real prompts produce YAML this clean on the first try -- that needs real runs to know |
| Six deliberately planted mistakes across the whole run (unanswered-question violation, entity-naming drift, hallucinated diagram citation, covers/content mismatch, hallucinated test citation, bad test cross-reference) are all caught | A claim that R0–R17 catch every possible mistake class -- they catch the ones designed in; a real run will surface failure modes not yet anticipated |

## Layout

```
pipeline/
  llm_client.py             LLMClient interface + AnthropicLLMClient (real) + FixtureLLMClient (offline replay)
  yaml_io.py                 shared YAML parse/dump helpers
  agent1_discovery.py         prompt + schema + run()
  agent2_requirements.py      prompt + schema + run() (FR/NFR/entities/state_models/state_triggers)
  agent3a_deterministic.py    ER + state diagrams + process skeleton -- no LLM
  agent3b_llm_diagrams.py     component diagram + sequence diagram -- LLM
  agent3_artifacts.py         combines 3a + 3b
  agent4a_rules.py            R0-R17: requirements (R0-R9) + artifacts (R10-R13) + tests (R14-R17)
  agent4b_semantic.py         scoped pairwise LLM contradiction check + candidate-pair pre-filter
  agent4_validator.py         combines 4a + 4b (+ optional artifact/test rules) into one validation_report
  agent5a_deterministic.py    acceptance-criterion + state-transition test cases -- no LLM
  agent5b_llm_testdata.py     example test data + edge cases -- LLM
  agent5_testdesign.py        combines 5a + 5b
fixtures/                     hand-recorded YAML used only by demo.py, clearly not live output;
                               artifacts_llm_fixture.yaml and tests_llm_fixture.yaml each contain
                               2 deliberate mistakes for the demo to catch
tests/
  test_rules_seeded_errors.py       14 tests, R0-R9
  test_rules_r10_r17.py             12 tests, R10-R17 (artifact/test citation rules)
  test_agent3a_deterministic.py      7 tests, diagram renderer correctness
  test_agent5a_deterministic.py      6 tests, test generator correctness
eval/
  pairwise_pairs.yaml         16 hand-labeled requirement pairs (8 contradiction, 8 consistent)
  run_eval.py                  real evaluation runner (or --dry-run harness smoke test)
run_pipeline.py                CLI orchestrator for real runs (5 subcommands)
demo.py                        offline end-to-end walkthrough, all 5 agents
raw_request.txt                 the sample business request (expense reimbursement domain)
```

See [`docs/agent-pipeline-design.md`](docs/agent-pipeline-design.md) and
[`docs/agent-pipeline-design-agents-3-5.md`](docs/agent-pipeline-design-agents-3-5.md)
for the full schemas, prompts, and rule tables with rationale.
