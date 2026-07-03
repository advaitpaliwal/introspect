#!/usr/bin/python3
"""Regression checks for the Codex/Introspect benchmark harness."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "scripts" / "benchmark-codex-introspect.py"


def fail(message: str) -> None:
    raise SystemExit(f"test-benchmark-runner: {message}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="introspect-benchmark-runner-") as tmp:
        temp = Path(tmp)
        auth = temp / "auth"
        auth.mkdir()
        (auth / "auth.json").write_text('{"OPENAI_API_KEY":"fixture"}\n')
        (auth / "installation_id").write_text("00000000-0000-0000-0000-000000000000\n")
        tasks = temp / "tasks.jsonl"
        tasks.write_text(
            json.dumps(
                {
                    "id": "absolute-output-paths",
                    "turns": [{"prompt": "write ok"}],
                    "score_command": "test -f ok.txt",
                }
            )
            + "\n"
        )
        output = Path(".tmp-benchmark-runner-relative-output")
        if (REPO / output).exists():
            subprocess.run(["rm", "-rf", str(REPO / output)], check=True)
        try:
            result = subprocess.run(
                [
                    str(RUNNER),
                    "--tasks",
                    str(tasks),
                    "--auth-source",
                    str(auth),
                    "--output-dir",
                    str(output),
                    "--dry-run",
                ],
                cwd=REPO,
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                fail(result.stderr or result.stdout)
            result_files = sorted((REPO / output).glob("*/tasks/absolute-output-paths/codex/result.json"))
            if len(result_files) != 1:
                fail(f"expected one codex result, found {result_files}")
            payload = json.loads(result_files[0].read_text())
            for key in ("home", "codex_home", "introspect_home", "workspace"):
                value = Path(payload[key])
                if not value.is_absolute():
                    fail(f"{key} must be absolute, got {value}")
            turn = payload["run"]["turns"][0]
            for key in ("stdout", "stderr", "final_message_path"):
                value = Path(turn[key])
                if not value.is_absolute():
                    fail(f"turn {key} must be absolute, got {value}")
        finally:
            subprocess.run(["rm", "-rf", str(REPO / output)], check=False)

    print("test-benchmark-runner: ok")


if __name__ == "__main__":
    main()
