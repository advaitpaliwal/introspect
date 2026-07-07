# Reflector Redesign Status

Started: 2026-07-07
Understanding: 55/100 (read reflector prompt/loop/runner selection; NOT yet read classifier, benchmark harness, trigger-stats, scanner event schema, surface-diff structure)

## Goal

Rebuild the Introspect reflector from "append another prose rule to AGENTS.md" into the self-improving-harness discipline described in Lilian Weng's 2026-07-04 "harness for self-improvement" post. Three concrete changes:

1. **Failure clustering / weakness mining** — before proposing an edit, cluster wake events into root-cause patterns, not per-event surface fixes. Today ~2/3 of reflections conclude "no_change — already covered," which is the symptom of instance-patching.
2. **ACE-style incremental playbook curation** — represent AGENTS.md as a structured playbook (bullet = id + description), curate it incrementally, and cut rules that never re-fire. Today it grew 4k→15k words in 3 weeks by appending; correction rate went 14%→16% (flat/worse) = context collapse.
3. **Held-out eval gate outside the loop** — every proposed edit must pass a held-in + held-out eval before it's accepted, and the evaluator must not be the same trigger-rate signal the loop optimizes (reward-hacking guard).

## Evidence baseline (from live runtime, 2026-07-06/07)
- AGENTS.md: 4225 words (2026-06-16) → 15390 words (2026-07-06), 238 commits.
- Reflections: 1120 runs, 373 made changes, 747 no-op (67% no-op).
- Trigger rate: prompt b2e206b 3/19=15.8% vs prior ca536bb 7/49=14.3% (flat).

## Constraints
- AGENTS.md in ~/.introspect is the LIVE global prompt governing all the user's Codex/Claude sessions AND this agent. It is git-tracked in ~/.introspect — snapshot before any rewrite.
- The reflector runs continuously on the user's machine. Keep it working through every slice.
- Claude runner is logged out; Codex is the active runner (already handled, committed 4cc780b).
- Verify with the existing gate suite (10 deterministic tests) + a behavior probe each slice.

## Plan (shippable slices)
- [ ] S0: Deep-read classifier, benchmark harness, trigger-stats, scanner schema, surface-diff. Raise understanding to 85+. Write design.
- [ ] S1: ACE playbook representation + incremental curator; consolidate live AGENTS.md into playbook form. (Biggest lever.)
- [ ] S2: Failure clustering in reflector batching.
- [ ] S3: Held-out eval gate outside the loop.

## S0 findings (understanding now 75/100)

### Wake classifier (hooks/intent_classifier.py, repetition_pressure.py)
- Trigger = logistic-regression model (word/char n-grams) at `~/.introspect/models/wake-logreg-v2-round4.json`, threshold 0.40 (sensitive). Binary score>=threshold. Review tier at 0.30.
- Event schema is rich: event_id, session_id, cwd, transcript_path:line, snippet, matched words, classifier.explanations (top features), wake_reason (classifier|repetition_pressure).
- NO root-cause/topical clustering today. Dedup is by event_count_key; repetition_pressure re-triggers low-score msgs seen 2+ times in 30min via Jaccard similarity (0.46) within a project scope. So similarity infra EXISTS (repetition_pressure feature-hashing + Jaccard) and can be reused for clustering.

### Eval harness (scripts/benchmark-codex-introspect.py)
- A/B runner: arm `codex` (plain) vs `codex_introspect` (with hooks). Each task scored pass/fail by a `score_command` exit code in `success_exit_codes`. This `passed` signal is OBJECTIVE and independent of trigger rate = the evaluator-outside-the-loop the redesign needs. It exists; it just isn't wired to accept/reject.
- Invoke: `python3 scripts/benchmark-codex-introspect.py --tasks <jsonl> --output-dir <dir> --auth-source ~/.codex --arms codex,codex_introspect --apply-mode proposal ...`. Emits results.jsonl + summary.md with per-task pass + hook events.
- Timing: ~2-3 min/task/arm; core suite (4 tasks) ~8-12 min. TOO SLOW for a per-edit inline gate that runs continuously.
- Tasks: bench/codex-introspect-{smoke(1),core(4),hook(2)}.jsonl. NO held-in/held-out split, no tags today — must add.
- Design consequence: inline per-edit gate = fast behavior probes (single Codex `exec` question against candidate prompt, ~seconds, already used by reflector). Full A/B benchmark = periodic held-out regression, run on a candidate before it's kept, not on every wake.

## Commit log
- (none yet for redesign)
