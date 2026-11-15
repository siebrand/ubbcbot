# Static analysis

The project runs the same static analysis tools locally and in CI.

| Tool                                                        | Checks                                  | Config                                  | CI workflow                            | Blocking                  |
|-------------------------------------------------------------|-----------------------------------------|-----------------------------------------|----------------------------------------|---------------------------|
| [ruff](https://docs.astral.sh/ruff/) `check`                | Lint rules, import order                | `[tool.ruff]` in `pyproject.toml`       | `lint.yml` (via pre-commit)            | Yes                       |
| ruff `format`                                               | Formatting                              | `[tool.ruff]` in `pyproject.toml`       | `lint.yml` (via pre-commit)            | Yes                       |
| [mypy](https://mypy.readthedocs.io/)                        | Type errors                             | `[tool.mypy]` in `pyproject.toml`       | `static-analysis.yml` job `mypy`       | **No** (advisory, see below) |
| [bandit](https://bandit.readthedocs.io/)                    | Security issues in `src/`               | `[tool.bandit]` in `pyproject.toml`     | `static-analysis.yml` job `bandit`     | Yes                       |
| [pip-audit](https://github.com/pypa/pip-audit)              | Known CVEs in pinned dependencies       | `requirements.txt` files                | `static-analysis.yml` job `pip-audit`  | Yes                       |
| `python -m compileall`                                      | Syntax errors                           |                                         | `lint.yml`                             | Yes                       |
| [CodeQL](https://codeql.github.com/)                        | Data-flow security and quality queries  | `.github/workflows/codeql.yml`          | `codeql.yml`                           | Reports to GitHub Security tab |

`static-analysis.yml` and `codeql.yml` also run weekly (Monday 05:00 UTC), so new
advisories for pinned dependencies show up even without a push.

## Run locally

Install the tools once (they are pinned in `tests/requirements.txt`):

```bash
python3 -m venv test_env
source test_env/bin/activate
pip install -r src/requirements.txt -r tests/requirements.txt
```

Run everything CI runs:

```bash
scripts/static-analysis.sh
```

Run selected checks (`ruff`, `format`, `mypy`, `bandit`, `audit`, `compile`):

```bash
scripts/static-analysis.sh ruff format
scripts/static-analysis.sh bandit
```

The script exits non-zero if a blocking check fails. mypy findings are printed but
do not fail the run unless you set `STRICT_MYPY=1`:

```bash
STRICT_MYPY=1 scripts/static-analysis.sh mypy
```

Or run the tools directly:

```bash
ruff check .            # add --fix to apply safe fixes
ruff format .           # rewrites files; use --check to only report
mypy src
bandit -r src -c pyproject.toml
pip-audit -r src/requirements.txt -r tests/requirements.txt
```

`pre-commit install` additionally runs ruff and ruff-format on every commit. The
hook revisions in `.pre-commit-config.yaml` are kept current by Dependabot (weekly
PR); `pre-commit autoupdate` does the same by hand.

## Keeping the local venv current

The versions of ruff, mypy, bandit and pip-audit are pinned in
`tests/requirements.txt`, and Dependabot bumps them. `scripts/sync-venv.sh` installs
the pins when the venv is behind. It runs automatically:

- at the start of every `scripts/static-analysis.sh` run, and
- after `git pull`, merge and rebase, through the `post-merge` and `post-rewrite`
  hooks (installed by `pre-commit install`; re-run it once after pulling this
  change).

It uses the active virtualenv, otherwise `./test_env`. If neither exists it does
nothing, so it never modifies the system Python. `scripts/static-analysis.sh` also
puts `./test_env` on the `PATH` when no venv is active, so activating it first is
optional. Set `SKIP_VENV_SYNC=1` to turn the sync off. Run it manually with
`scripts/sync-venv.sh`.

The ruff pre-commit hook has its own version (`rev` in `.pre-commit-config.yaml`),
also bumped by Dependabot. The two ruff versions can differ briefly between
the Dependabot PRs for each file.

`pip-audit` queries the PyPI vulnerability service, so it needs network access.

## mypy is advisory

mypy currently reports 61 errors in 21 files (mostly `None` defaults on typed
parameters and missing return statements). They pre-date this setup, so the `mypy`
CI job has `continue-on-error: true`: it shows the findings without failing the
pull request.

To make mypy blocking once the errors are fixed:

1. Remove `continue-on-error: true` from the `mypy` job in
   `.github/workflows/static-analysis.yml`.
2. Make `scripts/static-analysis.sh` fail on mypy by default (remove the
   `STRICT_MYPY` branch).

## Suppressing findings

Prefer fixing the finding. When a finding is a false positive:

- **ruff**: `# noqa: <rule>` on the line, or `per-file-ignores` in `pyproject.toml`.
- **mypy**: `# type: ignore[<code>]` on the line (unused ignores are reported).
- **bandit**: `# nosec <test id>` on the line, or add the id to `skips` in
  `[tool.bandit]` with a comment explaining why. `B105` and `B311` are skipped
  globally for the reasons listed there.
- **pip-audit**: `--ignore-vuln <ID>` in the command, with a comment on why the
  advisory does not apply.

## Adding a tool

1. Pin it in `tests/requirements.txt` (Dependabot keeps it current).
2. Put its configuration in `pyproject.toml`.
3. Add a job to `.github/workflows/static-analysis.yml` and a check to
   `scripts/static-analysis.sh` so local and CI runs stay identical.
4. Update the table above.
