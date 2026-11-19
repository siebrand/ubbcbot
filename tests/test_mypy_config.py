"""mypy checks the bodies of functions without annotations (audit 3, B6).

Without check_untyped_defs a call to a method that no longer exists passes the type check when it sits in a function
without annotations: the "order for" flow failed that way for seven months (audit 3, A0).
"""

import tomllib
from pathlib import Path

import pytest

mypy_api = pytest.importorskip("mypy.api")

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "pyproject.toml"


def test_untyped_function_bodies_are_checked():
    assert tomllib.loads(CONFIG.read_text())["tool"]["mypy"]["check_untyped_defs"] is True


def test_a_call_to_a_missing_method_in_an_untyped_function_is_an_error(tmp_path):
    source = tmp_path / "gone.py"
    source.write_text(
        "class A:\n    def ok(self) -> int:\n        return 1\n\n\ndef untyped(a):\n    return A().gone()\n"
    )

    stdout, _stderr, status = mypy_api.run(["--config-file", str(CONFIG), "--no-incremental", str(source)])

    assert status == 1
    assert 'has no attribute "gone"' in stdout
