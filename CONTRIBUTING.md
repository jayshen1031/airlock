# Contributing

Airlock is intentionally narrow: terminal-first independent code review and a
bounded repair loop. Please discuss changes that expand the product boundary in
a GitHub issue before implementation.

## Workflow

1. Create or select a GitHub issue.
2. Work on a branch and keep implementation state in commits.
3. Run the relevant tests and quality gates.
4. Open a pull request linked to the issue.
5. Push all commits before ending the session.

Never commit credentials, `.airlock/runs/`, `.sandbox/`, or provider transcripts.

By contributing, you agree that your contributions are licensed under the
Apache License 2.0. Report suspected vulnerabilities privately as described in
[`SECURITY.md`](SECURITY.md), not through public issues.
