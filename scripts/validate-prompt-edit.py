#!/usr/bin/python3
"""Held-out evaluator for the reflector, kept OUTSIDE the self-improvement loop.

The reflector optimizes to reduce the wake/trigger rate. If the trigger rate is
also its acceptance signal, it can reward-hack -- edit the prompt in ways that
quiet the classifier without improving how the agent actually behaves. Lilian
Weng's harness-for-self-improvement post is explicit that the evaluator and
permission controls must sit outside the optimizing loop.

This wrapper is that outside evaluator. It runs the A/B benchmark on a HELD-OUT
task suite (behaviors the reflector does not curate directly) and reports the
objective task-success pass rate for the introspected arm. A proposed prompt
edit should only be kept if held-out task success holds or improves; a drop is
a regression to revert, regardless of what the trigger rate did.

It shells out to scripts/benchmark-codex-introspect.py (the real runner) so the
scoring path is identical to the manual benchmark. In --dry-run it exercises the
wiring without invoking Codex.

Exit codes: 0 = pass rate >= --min-pass; 1 = below threshold; 2 = harness error.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BENCHMARK = REPO / "scripts" / "benchmark-codex-introspect.py"
DEFAULT_TASKS = REPO / "bench" / "codex-introspect-heldout.jsonl"


def find_run_dir(stdout: str) -> Path | None:
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("summary:"):
            summary_path = Path(line.split("summary:", 1)[1].strip())
            return summary_path.parent
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Held-out task-success gate for reflector prompt edits")
    parser.add_argument("--tasks", default=str(DEFAULT_TASKS))
    parser.add_argument("--output-dir", default=str(REPO / ".benchmarks" / "heldout-gate"))
    parser.add_argument("--auth-source", default="~/.codex")
    parser.add_argument(
        "--arms",
        default="codex_introspect",
        help="Arms to score for the gate. Default scores only the introspected arm.",
    )
    parser.add_argument(
        "--min-pass",
        type=float,
        default=1.0,
        help="Minimum held-out pass rate for the gated arm to accept the edit.",
    )
    parser.add_argument("--model", default="")
    parser.add_argument("--turn-timeout", type=int, default=240)
    parser.add_argument("--score-timeout", type=int, default=30)
    parser.add_argument("--introspect-wait-timeout", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true", help="Exercise wiring without invoking Codex.")
    args = parser.parse_args(argv)

    gated_arm = args.arms.split(",")[0].strip()
    cmd = [
        "/usr/bin/python3",
        str(BENCHMARK),
        "--tasks", str(args.tasks),
        "--output-dir", str(args.output_dir),
        "--auth-source", args.auth_source,
        "--arms", args.arms,
        "--apply-mode", "proposal",
        "--turn-timeout", str(args.turn_timeout),
        "--score-timeout", str(args.score_timeout),
        "--introspect-wait-timeout", str(args.introspect_wait_timeout),
    ]
    if args.model:
        cmd.extend(["--model", args.model])
    if args.dry_run:
        cmd.append("--dry-run")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        print(f"validate-prompt-edit: cannot run benchmark: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(proc.stdout)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        print(f"validate-prompt-edit: benchmark exited {proc.returncode}", file=sys.stderr)
        return 2

    run_dir = find_run_dir(proc.stdout)
    if run_dir is None:
        print("validate-prompt-edit: could not locate benchmark run dir", file=sys.stderr)
        return 2
    results_path = run_dir / "results.jsonl"
    if not results_path.exists():
        print(f"validate-prompt-edit: no results at {results_path}", file=sys.stderr)
        return 2

    total = 0
    passed = 0
    for line in results_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("arm") != gated_arm:
            continue
        total += 1
        if row.get("score", {}).get("passed"):
            passed += 1

    if total == 0:
        print(f"validate-prompt-edit: no results for arm {gated_arm!r}", file=sys.stderr)
        return 2

    rate = passed / total
    kind = "dry-run wiring" if args.dry_run else "held-out task success"
    print(
        f"validate-prompt-edit: {kind} for {gated_arm}: {passed}/{total} = {rate:.2f} "
        f"(min {args.min_pass:.2f}) -- this is task success, independent of trigger rate"
    )
    if rate + 1e-9 < args.min_pass:
        print("validate-prompt-edit: BELOW THRESHOLD -- revert the prompt edit", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
