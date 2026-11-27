"""Shared paths and a CLI runner for the tests."""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "eval-lift-check" / "scripts"
EVALS_FX = ROOT / "evals" / "fixtures"
FX = ROOT / "tests" / "fixtures"
READING = EVALS_FX / "task-reading-improved"
EXPECTED = json.loads((ROOT / "tests" / "oracle" / "expected.json").read_text())

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import compare  # noqa: E402
import plan_n  # noqa: E402


def run_cli(module, argv, env=None):
    """Run compare/plan_n in-process; returns (exit_code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = module.run(list(map(str, argv)), env={} if env is None else env)
        except SystemExit as exc:  # argparse exits for --help and usage errors
            code = int(exc.code or 0)
    return code, out.getvalue(), err.getvalue()


def compare_json(argv):
    code, out, err = run_cli(compare, [*argv, "--json", "-"])
    assert code == 0, err
    return json.loads(out)
