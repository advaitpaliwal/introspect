#!/usr/bin/python3
"""Tests for the addressable playbook view (hooks/playbook.py)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "hooks" / "playbook.py"


def fail(message: str) -> None:
    raise SystemExit(f"test-playbook: {message}")


def load():
    spec = importlib.util.spec_from_file_location("introspect_playbook", MODULE)
    if spec is None or spec.loader is None:
        fail(f"cannot load {MODULE}")
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass field-type resolution (which looks up
    # sys.modules[cls.__module__] under `from __future__ import annotations`)
    # works on Python 3.9.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SAMPLE = """# AGENTS.md

## Mission

- First rule about goals and shipping the deliverable first.
- Second rule with a continuation.
  It spans two lines and a sub-point.
  - a nested bullet

## Voice and reporting

- Be direct, no flattery, no padding, say the point first.
"""


def main() -> None:
    pb_mod = load()

    pb = pb_mod.parse_playbook(SAMPLE)
    if len(pb.rules) != 3:
        fail(f"expected 3 rules, got {len(pb.rules)}: {[r.id for r in pb.rules]}")

    ids = [r.id for r in pb.rules]
    if ids != ["mission.01", "mission.02", "voice-and-reporting.01"]:
        fail(f"unexpected rule ids: {ids}")

    # continuation lines fold into the owning rule
    second = pb.rules[1]
    if "nested bullet" not in second.text or "spans two lines" not in second.text:
        fail("continuation lines were not folded into the rule")

    # budget breach is detected and reported as nonzero-worthy
    over = pb_mod.lint_playbook(pb, total_budget=5)
    if not over.over_budget:
        fail("tiny budget should report over_budget")
    if over.ok:
        fail("over-budget report must not be ok")

    # a comfortable budget with no dupes is ok
    fine = pb_mod.lint_playbook(pb, total_budget=10000)
    if not fine.ok:
        fail(f"clean small playbook should be ok: {fine.render()}")

    # near-duplicate detection
    dup_text = SAMPLE + "\n## Extra\n\n- Be direct, no flattery, no padding, say the point first.\n"
    dpb = pb_mod.parse_playbook(dup_text)
    drep = pb_mod.lint_playbook(dpb, total_budget=10000)
    if not drep.duplicates:
        fail("identical rule in two sections should be flagged as duplicate")

    # over-long detection
    long_rule = "- " + " ".join(["word"] * 200) + "\n"
    lpb = pb_mod.parse_playbook("## S\n\n" + long_rule)
    lrep = pb_mod.lint_playbook(lpb, total_budget=10000)
    if not lrep.over_long:
        fail("a 200-word rule should be flagged over-long")

    # the live default template parses and is within budget (sanity on real shape)
    template = REPO / "templates" / "default-AGENTS.md"
    if template.exists():
        tpb = pb_mod.parse_playbook(template.read_text(encoding="utf-8"))
        if not tpb.rules:
            fail("default template should parse into rules")

    print("test-playbook: ok")


if __name__ == "__main__":
    main()
