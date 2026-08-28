# Security Policy

## Supported versions

Airlock is currently pre-alpha and has not published a stable release. Until a
versioned release policy is announced, security fixes are applied only to the
latest commit on the default branch. Older commits and forks are not supported.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability.

Use GitHub's private vulnerability reporting form:

https://github.com/jayshen1031/airlock/security/advisories/new

Include, where possible:

- the affected commit or version;
- the operating system and provider CLI involved;
- reproduction steps or a minimal repository;
- expected and observed behavior;
- the security impact;
- whether credentials, private source code, or third-party data may have been
  exposed.

Do not include real credentials, access tokens, private provider transcripts,
or confidential repository contents. Use sanitized examples and wait for a
private maintainer response before sharing additional sensitive evidence.

You should receive an acknowledgement within seven days. The maintainer will
coordinate validation, remediation, disclosure timing, and credit through the
private advisory. Please allow a reasonable remediation period before public
disclosure.

## Security scope

Airlock orchestrates user-installed third-party command-line tools. Reports
about Airlock's process isolation, reviewer write protection, artifact handling,
prompt boundary, credential exposure, or command execution are in scope.

Vulnerabilities in Claude Code, Codex CLI, Gemini CLI, or another provider tool
should also be reported to that vendor through its own security process. Airlock
is not affiliated with, endorsed by, sponsored by, or officially connected to
those vendors and cannot issue fixes for their products.

## Safe-harbor intent

Good-faith research that avoids privacy violations, data destruction, service
disruption, and access beyond what is necessary to demonstrate the issue is
welcome. This statement expresses the project's intent and is not legal advice
or a waiver of third-party terms.
