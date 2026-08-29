# Agent Instructions

Track shared work in GitHub Issues and keep implementation state in Git commits
and pull requests.

## Landing the Plane (Session Completion)

When ending a work session:

1. File GitHub issues for remaining work.
2. Run relevant tests, linters, and builds when code changed.
3. Update or close the active issue.
4. Run `git pull --rebase`, `git push`, and verify `git status` is up to date
   with origin. Work is not complete until the push succeeds.
5. Clear stale stashes and prune remote branches when safe.
6. Hand off the exact commit, verification evidence, and remaining risks.

Never leave completed work only in a local working tree. Never commit secrets,
provider transcripts, `.airlock/runs/`, or `.sandbox/`.

## Product boundary

- Airlock is a terminal-first cross-agent coding review and bounded repair loop.
- Git workspace state and structured artifacts are shared memory; agent chat
  histories are not transferred between roles.
- Reviewers are read-only. A failure, timeout, malformed verdict, or detected
  write must never be interpreted as approval.
- Airlock must not automatically commit, push, merge, reset, or expand provider
  permissions.
- Preserve explicit user control, bounded iterations, audit artifacts, and
  interruptibility.

<!-- BEGIN MEMHUB PROJECT -->
## MemHub project boundary

- `project_scope`: `airlock`
- `security_domain`: `personal`
- `access_mode`: `project`
- Enabled clients: codex, claude, kimi, qoder
- Memory reads and writes are restricted to this project and security domain.
- "提交记忆" / "commit memory" means run `~/.local/bin/commit-memory-to-oss.sh` for the current client session.
- Session-close hooks publish automatically. Repeated mid-session submissions are incremental and idempotent.
- Memory submission uses the durable spool and shared OSS L0; do not distill or write Neo4j from the foreground Agent.
- This host's background `ingress → distill → consumer` services use local PostgreSQL and a dedicated replication Neo4j. Never use the legacy/Cognee Neo4j or another workstation's databases as the projection target.
- Treat `configs/memhub.yaml` as the project identity and governance source of truth.
- GitNexus remains the local real-time code-graph authority. Persist only selected impact observations through Nexus.
- Shared Agent skills are installed globally; this repository declares required capabilities but does not copy skill implementations.

## Workspace zones

- Source of truth: `src/`, `configs/`, `docs/`, `scripts/`
- Generated artifacts: `artifacts/`
- Temporary files, logs and caches: `.sandbox/`
- Distilled local exports, when present: `capsules/`
- Never index `.sandbox/**` and never put credentials in the repository.

## Multi-host evidence boundary

- Company, home, and other machines are separate host scopes.
- Git-tracked state at an explicit commit is shared; ignored data, caches, containers, credentials, tools, symlink resolution, and process state are host-local.
- Never infer that a path is globally absent or unused from one host observation.
- Cleanup evidence must record `host_id` and `repo_commit`; cross-host differences are `HOST_VARIANT`, not corruption.
- Repository cleanup and host-local cleanup must be reviewed and executed separately.
<!-- END MEMHUB PROJECT -->

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **airlock** (356 symbols, 636 relationships, 7 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> Index stale? Run `node .gitnexus/run.cjs analyze` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? `npx gitnexus analyze` (npm 11 crash → `npm i -g gitnexus`; #1939).

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows. For regression review, compare against the default branch: `detect_changes({scope: "compare", base_ref: "main"})`.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit changes without running `detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/airlock/context` | Codebase overview, check index freshness |
| `gitnexus://repo/airlock/clusters` | All functional areas |
| `gitnexus://repo/airlock/processes` | All execution flows |
| `gitnexus://repo/airlock/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
