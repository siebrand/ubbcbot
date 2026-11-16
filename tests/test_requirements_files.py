"""The requirements files: two, pinned, consistent, and every doc, script and workflow that names one names a real file.

src/requirements.txt is what the Lambdas run with (sam build reads it from CodeUri src/), tests/requirements.txt adds
the development tools. Both pin boto3 and botocore, so those pins must match or installing the two together fails.
"""

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKIPPED_DIRECTORIES = {
    "test_env",
    "setup_venv",
    "venv",
    ".git",
    ".idea",
    ".aws-sam",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
}
TEXT_SUFFIXES = {".md", ".sh", ".yml", ".yaml", ".toml", ".py", ".cfg", ".ini", ".txt"}
REQUIREMENTS = ["src/requirements.txt", "tests/requirements.txt"]
PIN = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?==([^\s;#]+)")
REFERENCE = re.compile(r"(?<![\w./-])((?:[\w.-]+/)+[\w.-]*requirements[\w.-]*\.txt)")


def _repository_files():
    for directory, subdirectories, files in os.walk(ROOT):
        subdirectories[:] = [name for name in subdirectories if name not in SKIPPED_DIRECTORIES]
        for name in files:
            yield Path(directory) / name


def _pins(relative_path: str) -> dict[str, str]:
    pins = {}
    for line in (ROOT / relative_path).read_text().splitlines():
        match = PIN.match(line.strip())
        if match:
            pins[match.group(1).lower().replace("_", "-")] = match.group(2)
    return pins


class TestTheFiles:
    def test_there_are_two_requirements_files(self):
        found = sorted(
            str(path.relative_to(ROOT))
            for path in _repository_files()
            if re.fullmatch(r".*requirements.*\.txt", path.name)
        )

        assert found == REQUIREMENTS

    @pytest.mark.parametrize("path", REQUIREMENTS)
    def test_every_requirement_is_pinned_to_an_exact_version(self, path):
        for line in (ROOT / path).read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                assert PIN.match(stripped), f"{path}: '{stripped}' is not pinned with =="

    def test_the_pins_that_both_files_have_are_identical(self):
        source, tests = _pins("src/requirements.txt"), _pins("tests/requirements.txt")
        shared = source.keys() & tests.keys()

        assert {"boto3", "botocore"} <= shared
        assert {name: (source[name], tests[name]) for name in shared if source[name] != tests[name]} == {}


def _references() -> dict[str, set[str]]:
    """Every path to a requirements file that a doc, script or workflow mentions: {path: files that mention it}"""
    found: dict[str, set[str]] = {}
    for path in _repository_files():
        if path.suffix not in TEXT_SUFFIXES:
            continue
        for reference in REFERENCE.findall(path.read_text(errors="ignore")):
            found.setdefault(reference, set()).add(str(path.relative_to(ROOT)))
    return found


REFERENCES = _references()


class TestReferences:
    def test_the_scan_finds_the_references(self):
        assert len(REFERENCES) >= 2
        assert {"src/requirements.txt", "tests/requirements.txt"} <= set(REFERENCES)

    @pytest.mark.parametrize("reference", sorted(REFERENCES))
    def test_a_mentioned_requirements_file_exists(self, reference):
        assert (ROOT / reference).is_file(), f"{reference} is mentioned in {sorted(REFERENCES[reference])}"


class TestDependabot:
    DEPENDABOT = (ROOT / ".github" / "dependabot.yml").read_text()

    def test_every_pip_directory_has_a_requirements_file(self):
        directories = re.findall(r'package-ecosystem:\s*"pip"\s+directory:\s*"([^"]+)"', self.DEPENDABOT)

        assert sorted(directories) == ["/src", "/tests"]
        for directory in directories:
            assert (ROOT / directory.lstrip("/") / "requirements.txt").is_file(), directory

    def test_every_requirements_file_is_watched(self):
        directories = set(re.findall(r'package-ecosystem:\s*"pip"\s+directory:\s*"([^"]+)"', self.DEPENDABOT))

        assert {"/" + path.rsplit("/", 1)[0] for path in REQUIREMENTS} == directories
