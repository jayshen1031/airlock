# Agent Instructions

<!-- BEGIN MEMHUB PROJECT -->
## MemHub project boundary

- `project_scope`: `airlock`
- `security_domain`: `personal`
- `access_mode`: `project`
- Enabled clients: claude
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
