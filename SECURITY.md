# Security Policy

## Supported versions

UBBC Bot is deployed continuously from the `main` branch. Only the current
`main` is supported; please make sure a report reproduces against the latest
`main` before submitting.

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, report them privately via one of:

- GitHub's [private vulnerability reporting][gh-report] (Security → Report a
  vulnerability), or
- email to **siebrand at kitano dot nl** with the subject prefixed `SECURITY:`.

Please include:

- a description of the vulnerability and its impact,
- steps to reproduce (a proof of concept if possible),
- the affected component (e.g. webhook, an admin command, an IAM policy), and
- any suggested remediation.

## What to expect

- Acknowledgement of your report as soon as reasonably possible.
- An assessment and, where confirmed, a fix prioritized by severity.
- Coordination with you on disclosure timing; please give us reasonable time to
  remediate before any public disclosure.

## Scope

In scope: the bot code in this repository, its AWS infrastructure definition (`template.yaml`), and the deployment
scripts.

Out of scope: vulnerabilities in third-party dependencies (report those
upstream), and anything requiring access to the single hard-coded admin account.

[gh-report]: https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability
