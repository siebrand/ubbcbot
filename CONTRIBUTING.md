# Contributing to UBBC Bot

Thanks for your interest in improving UBBC Bot — a Telegram beer-ordering bot
built on AWS serverless (SAM, Lambda, DynamoDB, API Gateway).

## Getting started

```bash
python3 -m venv test_env
source test_env/bin/activate
pip install -r src/requirements.txt -r tests/requirements.txt
pre-commit install
```

There is no local bot runtime — the `test` stack on AWS is the development
environment. See the [README](README.md) for bot and deployment setup.

## Development workflow

1. Create a branch off `main`.
2. Make your change, keeping it focused and small.
3. Run the checks below locally.
4. Open a pull request against `main` with a clear description.

## Running the checks

```bash
# Tests (uses moto, no real AWS)
AWS_DEFAULT_REGION=eu-north-1 AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing \
  PYTHONPATH=src python -m pytest

# Lint + format (also run automatically by the pre-commit hook and in CI)
ruff check .
ruff format --check .
```

CI runs the test suite and the lint/format checks on every pull request; both
must pass before merge.

## Coding standards

- Python 3.14; follow the existing structure (handlers, services, repositories).
- Line length 120; formatting and import order are handled by `ruff format` and
  `ruff` (rules `E,F,W,I,UP,B,SIM,C4`).
- Use `logger`, never `print`.
- All user-facing text goes through `self._t(key, user_id, **params)`; keys must
  exist in **both** `src/translations/en.json` and `src/translations/nl.json`
  with no duplicates. Group messages are always Dutch.
- Escape user-supplied strings (`_escape_html`) in any `parse_mode="HTML"`
  message.
- When changing a command, update all references together: command router,
  callback handler / admin panel, help text, translations, `setup-commands.sh`,
  and the README.
- Secrets live only in SSM Parameter Store; never commit tokens or credentials.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`,
`fix:`, `docs:`, `refactor:`, `chore:`, `ci:`, `style:`, `test:`. Explain what
changed and why; call out any breaking changes or migration steps.

## Reporting issues

Use the issue templates. For security issues, do **not** open a public issue —
follow [SECURITY.md](SECURITY.md).
