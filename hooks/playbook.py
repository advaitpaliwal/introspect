#!/usr/bin/python3
"""Addressable playbook view of an AGENTS.md-style prompt.

The Introspect reflector used to improve the prompt by appending prose to the
nearest bullet. Over three weeks that grew the live prompt ~48x (328 -> 15k+
words) while the correction rate stayed flat: classic context collapse, where
new rules compete with old ones for the model's attention and multi-topic
run-on bullets bury the constraint that actually matters.

This module turns the freeform markdown into a set of *addressable atomic
rules* so the reflector can curate incrementally (edit / merge / prune a
specific rule by id) instead of appending, and so a lint gate can flag the two
failure modes ACE warns about: an over-long multi-topic rule, and a near
duplicate of an existing rule. It is pure text tooling: no model calls, no
network, deterministic.

CLI:
    python3 hooks/playbook.py lint <file>   # report + nonzero exit on breach
    python3 hooks/playbook.py ids  <file>    # list rule ids + one-line digests
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Budgets. A rule past WORDS_PER_RULE_SOFT is almost always several rules
# fused into one run-on and should be split. TOTAL_WORDS_BUDGET is the whole
# playbook ceiling the reflector must curate within rather than grow past.
WORDS_PER_RULE_SOFT = 80
TOTAL_WORDS_BUDGET = 6000
DUPLICATE_JACCARD = 0.55

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "than", "that", "this",
    "these", "those", "is", "are", "was", "were", "be", "been", "being", "to",
    "of", "in", "on", "for", "with", "as", "at", "by", "it", "its", "not", "no",
    "do", "dont", "does", "not", "you", "your", "user", "when", "what", "which",
    "who", "them", "they", "their", "into", "over", "from", "so", "just", "only",
}


@dataclass
class Rule:
    section: str
    section_slug: str
    index: int  # 1-based within section
    text: str  # full rule text incl. continuation/sub-bullets, markdown stripped of leading "- "
    start_line: int

    @property
    def id(self) -> str:
        return f"{self.section_slug}.{self.index:02d}"

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    def digest(self, limit: int = 90) -> str:
        one = " ".join(self.text.split())
        return one if len(one) <= limit else one[: limit - 1].rstrip() + "…"


@dataclass
class Playbook:
    rules: list[Rule] = field(default_factory=list)
    preamble: str = ""

    @property
    def word_count(self) -> int:
        return sum(r.word_count for r in self.rules)


def slugify(heading: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", heading.strip().lower()).strip("-")
    return base or "section"


def parse_playbook(text: str) -> Playbook:
    """Split markdown into sections (## headings) and top-level bullets.

    A rule is one top-level "- " bullet plus any indented continuation lines or
    sub-bullets beneath it, until the next top-level bullet or heading.
    """
    lines = text.splitlines()
    pb = Playbook()
    section = "Preamble"
    section_slug = "preamble"
    per_section_counts: dict[str, int] = {}
    current: list[str] | None = None
    current_start = 0

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        body = "\n".join(current).rstrip()
        if body.strip():
            per_section_counts[section_slug] = per_section_counts.get(section_slug, 0) + 1
            pb.rules.append(
                Rule(
                    section=section,
                    section_slug=section_slug,
                    index=per_section_counts[section_slug],
                    text=body,
                    start_line=current_start,
                )
            )
        current = None

    for i, raw in enumerate(lines, 1):
        heading = re.match(r"^##\s+(.*)$", raw)
        if heading:
            flush()
            section = heading.group(1).strip()
            section_slug = slugify(section)
            continue
        if re.match(r"^#\s+", raw):  # H1 title
            flush()
            continue
        bullet = re.match(r"^-\s+(.*)$", raw)
        if bullet:
            flush()
            current = [bullet.group(1)]
            current_start = i
            continue
        if current is not None:
            # continuation line (indented text or sub-bullet) belongs to the rule
            current.append(raw)
        else:
            pb.preamble += raw + "\n"
    flush()
    return pb


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / len(a | b)


@dataclass
class LintReport:
    total_words: int
    total_budget: int
    over_long: list[tuple[str, int]]  # (rule_id, word_count)
    duplicates: list[tuple[str, str, float]]  # (id_a, id_b, score)
    rule_count: int

    @property
    def over_budget(self) -> bool:
        return self.total_words > self.total_budget

    @property
    def ok(self) -> bool:
        return not self.over_budget and not self.duplicates

    def render(self) -> str:
        out = [
            f"playbook: {self.rule_count} rules, {self.total_words} words "
            f"(budget {self.total_budget})",
        ]
        if self.over_budget:
            out.append(
                f"  OVER BUDGET by {self.total_words - self.total_budget} words "
                f"-- consolidate or prune, do not append"
            )
        if self.over_long:
            out.append(f"  {len(self.over_long)} over-long rule(s) (>{WORDS_PER_RULE_SOFT}w, split candidates):")
            for rid, wc in self.over_long[:20]:
                out.append(f"    {rid}: {wc}w")
        if self.duplicates:
            out.append(f"  {len(self.duplicates)} near-duplicate pair(s) (>={DUPLICATE_JACCARD} jaccard, merge candidates):")
            for a, b, s in self.duplicates[:20]:
                out.append(f"    {a} ~ {b}  ({s:.2f})")
        if self.ok and not self.over_long:
            out.append("  ok")
        return "\n".join(out)


def lint_playbook(
    pb: Playbook,
    *,
    total_budget: int = TOTAL_WORDS_BUDGET,
    words_per_rule: int = WORDS_PER_RULE_SOFT,
    duplicate_threshold: float = DUPLICATE_JACCARD,
) -> LintReport:
    over_long = [(r.id, r.word_count) for r in pb.rules if r.word_count > words_per_rule]
    over_long.sort(key=lambda x: x[1], reverse=True)

    token_sets = [(r.id, _tokens(r.text)) for r in pb.rules]
    duplicates: list[tuple[str, str, float]] = []
    for i in range(len(token_sets)):
        id_a, ta = token_sets[i]
        for j in range(i + 1, len(token_sets)):
            id_b, tb = token_sets[j]
            score = jaccard(ta, tb)
            if score >= duplicate_threshold:
                duplicates.append((id_a, id_b, score))
    duplicates.sort(key=lambda x: x[2], reverse=True)

    return LintReport(
        total_words=pb.word_count,
        total_budget=total_budget,
        over_long=over_long,
        duplicates=duplicates,
        rule_count=len(pb.rules),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Addressable playbook view of an AGENTS.md prompt")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_lint = sub.add_parser("lint", help="report budget / over-long / duplicate issues")
    p_lint.add_argument("file")
    p_lint.add_argument("--budget", type=int, default=TOTAL_WORDS_BUDGET)
    p_lint.add_argument("--strict", action="store_true", help="also fail on over-long rules")
    p_ids = sub.add_parser("ids", help="list rule ids with one-line digests")
    p_ids.add_argument("file")
    args = parser.parse_args(argv)

    path = Path(args.file)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"playbook: cannot read {path}: {exc}", file=sys.stderr)
        return 2
    pb = parse_playbook(text)

    if args.cmd == "ids":
        for r in pb.rules:
            print(f"{r.id}\t{r.word_count}w\t{r.digest()}")
        return 0

    report = lint_playbook(pb, total_budget=args.budget)
    print(report.render())
    if report.over_budget or report.duplicates:
        return 1
    if args.strict and report.over_long:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
