"""Code coverage in CI: the tools are pinned, the configuration is in pyproject.toml and CI enforces a minimum.

Local `pytest` stays fast (no coverage); `pytest --cov` measures it with the same settings CI uses.
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text()


def test_the_coverage_tools_are_pinned_for_the_tests():
    requirements = (ROOT / "tests" / "requirements.txt").read_text()

    assert re.search(r"^pytest-cov==\d+(\.\d+)+$", requirements, re.MULTILINE)
    assert re.search(r"^coverage==\d+(\.\d+)+$", requirements, re.MULTILINE)


def test_only_the_bot_code_is_measured_with_branches():
    run = PYPROJECT["tool"]["coverage"]["run"]

    assert run["source"] == ["src"]
    assert run["branch"] is True


def test_a_minimum_is_enforced():
    minimum = PYPROJECT["tool"]["coverage"]["report"]["fail_under"]

    assert 30 <= minimum < 100


def test_ci_measures_coverage_and_shows_it_in_the_job_summary():
    test_job = CI.split("jobs:", 1)[1]

    assert re.search(r"run:\s*pytest\b[^\n]*--cov\b", test_job)
    assert "$GITHUB_STEP_SUMMARY" in test_job


def test_a_plain_pytest_run_does_not_measure_coverage():
    """So the daily run stays about as fast as it is now"""
    addopts = (ROOT / "pytest.ini").read_text()

    assert "--cov" not in addopts
