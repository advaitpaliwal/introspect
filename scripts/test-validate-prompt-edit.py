#!/usr/bin/python3
"""Wiring test for the held-out prompt-edit gate (scripts/validate-prompt-edit.py).

Runs the gate in --dry-run so no Codex is invoked, and asserts it discovers the
held-out tasks, scores the introspected arm, and reports a pass rate. Also
validates the held-out task manifest is well-formed and disjoint in id from the
core/hook suites (so the reflector cannot overfit the gate)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GATE = REPO / "scripts" / "validate-prompt-edit.py"
HELDOUT = REPO / "bench" / "codex-introspect-heldout.jsonl"
CORE = REPO / "bench" / "codex-introspect-core.jsonl"
HOOK = REPO / "bench" / "codex-introspect-hook.jsonl"


def fail(message: str) -> None:
    raise SystemExit(f"test-validate-prompt-edit: {message}")


def load_ids(path: Path) -> set[str]:
    ids = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        task = json.loads(line)
        ids.add(task["id"])
    return ids


def main() -> None:
    # Manifest is well-formed and every task is tagged held_out.
    heldout_ids = set()
    for line in HELDOUT.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        task = json.loads(line)
        if task.get("split") != "held_out":
            fail(f"held-out task {task.get('id')} missing split=held_out")
        if not task.get("turns") or not task.get("score_command"):
            fail(f"held-out task {task.get('id')} missing turns/score_command")
        heldout_ids.add(task["id"])
    if len(heldout_ids) < 2:
        fail("expected at least 2 held-out tasks")

    # Disjoint from the suites the reflector curates against.
    overlap = heldout_ids & (load_ids(CORE) | load_ids(HOOK))
    if overlap:
        fail(f"held-out ids overlap curated suites (overfit risk): {overlap}")

    # Dry-run wiring: gate runs, scores the introspect arm, exits 0.
    proc = subprocess.run(
        ["/usr/bin/python3", str(GATE), "--dry-run", "--arms", "codex_introspect"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        fail(f"dry-run gate exited {proc.returncode}: {proc.stderr.strip()}")
    if "task success, independent of trigger rate" not in proc.stdout:
        fail(f"gate did not report the separated signal: {proc.stdout.strip()}")
    if f"{len(heldout_ids)}/{len(heldout_ids)}" not in proc.stdout:
        fail(f"gate did not score all held-out tasks: {proc.stdout.strip()}")

    print("test-validate-prompt-edit: ok")


if __name__ == "__main__":
    main()
