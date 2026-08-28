# Airlock

**Keep the terminals. Remove the copy-paste.**

Airlock is a terminal-first cross-agent coding review loop. It lets one coding
agent implement a change and another independently review the resulting Git
diff, then carries structured findings back into a bounded repair loop.

Airlock is not a general multi-agent framework. Git is the shared memory, the
reviewer is read-only, and the developer stays in control from their existing
terminal workflow.

## Project independence

Airlock is an independent open-source project. It is not affiliated with,
endorsed by, sponsored by, or officially connected to Anthropic, OpenAI,
Google, or any other agent-provider vendor. Claude, Claude Code, Codex, Gemini,
and other product names and trademarks belong to their respective owners.

Airlock invokes provider CLIs that users install and configure separately. It
does not redistribute those CLIs, grant access to their services, or replace
their licenses, terms, subscriptions, or acceptable-use policies.

## v0.1 review-only workflow

```text
writer changes the repository
  -> airlock captures tracked, staged, and untracked changes
  -> an independent reviewer inspects them in read-only mode
  -> approve / reject with findings / blocked
  -> local, inspectable run artifacts
```

Requires Python 3.11+ and at least one authenticated provider CLI (`codex` or
`claude`) on `PATH`.

```bash
python -m pip install -e .

airlock review \
  --reviewer claude \
  --task "Refactor authentication without changing token semantics"
```

Use Codex as the independent reviewer instead:

```bash
airlock review --reviewer codex --task "Fix issue #42"
```

Exit codes are stable for scripting:

- `0`: approved;
- `1`: rejected with actionable findings;
- `2`: blocked, including provider failure or malformed output;
- `3`: Airlock/Git error or detected reviewer workspace mutation.

Each invocation writes task, captured change material, schema, state, provider
metadata, and the validated verdict under `.airlock/runs/<run-id>/`. These run
artifacts are local and ignored by Git.

Airlock v0.1 does not attach to existing terminal panes, run an automatic test
gate, repair changes, or loop autonomously. Those capabilities remain separate,
bounded follow-up work.

## Product principles

- Preserve the user's iTerm2 or terminal layout.
- Automate handoff, not judgment or final authority.
- Pass task artifacts, diffs, tests, and findings; do not copy conversations.
- Keep reviewers read-only and independently prompted.
- Make every iteration visible, resumable, and bounded.
- Start with Claude Code and Codex CLI; add providers only when demanded.

## Design and knowledge boundaries

The product requirements and architecture are defined in
[`docs/product-requirements_CN.md`](docs/product-requirements_CN.md) and
[`docs/architecture_CN.md`](docs/architecture_CN.md). The repository is the
source of truth for code and project decisions; ADR 0001 defines how optional
MemHub/Nexus knowledge governance remains outside the standalone runtime.

## License

Licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for
project attribution. This repository does not provide legal advice.
