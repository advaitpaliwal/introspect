#!/usr/bin/env python3
"""Test source selection with all installation commands stubbed; no installation."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallerSourceTests(unittest.TestCase):
    def run_installer(self, **overrides):
        # No real mkdir/git/chmod/ln runs, and no user HOME/config is inherited.
        script = """
git() { printf 'git'; printf ' <%s>' "$@"; printf '\\n'; }
mkdir() { :; }
chmod() { :; }
ln() { :; }
source "$1"
"""
        return subprocess.check_output(
            ["bash", "-c", script, "test-installer-source", str(ROOT / "install.sh")],
            text=True,
            env={"PATH": os.environ["PATH"], "HOME": "/nonexistent/introspect-source-test", **overrides},
        )

    def test_default_public_continuing_repository(self):
        output = self.run_installer()
        self.assertIn(
            "git <clone> <--depth=1> <https://github.com/advaitpaliwal/introspect.git> "
            "</nonexistent/introspect-source-test/.introspect/runtime>", output
        )

    def test_custom_source_runtime_and_prefix_preserved(self):
        output = self.run_installer(
            INTROSPECT_REPO_URL="https://example.test/custom.git",
            INTROSPECT_RUNTIME_DIR="/nonexistent/custom-runtime",
            PREFIX="/nonexistent/custom-prefix",
        )
        self.assertIn(
            "git <clone> <--depth=1> <https://example.test/custom.git> </nonexistent/custom-runtime>",
            output,
        )
        self.assertIn("/nonexistent/custom-prefix/bin/introspect", output)

    def test_readme_and_public_maintainer_display(self):
        readme = (ROOT / "README.md").read_text()
        self.assertIn("https://raw.githubusercontent.com/advaitpaliwal/introspect/main/install.sh", readme)
        self.assertIn("git clone https://github.com/advaitpaliwal/introspect.git", readme)
        plugin = json.loads((ROOT / "plugins/introspect/.codex-plugin/plugin.json").read_text())
        self.assertEqual(plugin["author"]["name"], "Advait Paliwal")
        self.assertEqual(plugin["interface"]["developerName"], "Advait Paliwal")
        self.assertEqual(plugin["license"], "MIT")


if __name__ == "__main__":
    unittest.main()
