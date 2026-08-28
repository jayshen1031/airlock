# Airlock

**Keep the terminals. Remove the copy-paste.**

Airlock is a terminal-first cross-agent coding review loop. It lets one coding
agent implement a change and another independently review the resulting Git
diff, then carries structured findings back into a bounded repair loop.

Airlock is not a general multi-agent framework. Git is the shared memory, the
reviewer is read-only, and the developer stays in control from their existing
terminal workflow.

## Planned v0.1 workflow

```text
task
  -> writer changes the repository
  -> configured test command
  -> reviewer inspects the Git diff (read-only)
  -> approve: done
  -> reject: structured findings -> writer repairs -> review again
```

The first useful command will be review-only:

```bash
airlock review --reviewer claude
```

The bounded automation layer will follow:

```bash
airlock run --writer codex --reviewer claude --max-iterations 3 \
  "refactor the authentication module"
```

## Product principles

- Preserve the user's iTerm2 or terminal layout.
- Automate handoff, not judgment or final authority.
- Pass task artifacts, diffs, tests, and findings; do not copy conversations.
- Keep reviewers read-only and independently prompted.
- Make every iteration visible, resumable, and bounded.
- Start with Claude Code and Codex CLI; add providers only when demanded.

## Status

Airlock is in project bootstrap. The product requirements and architecture are
defined in [`docs/product-requirements_CN.md`](docs/product-requirements_CN.md)
and [`docs/architecture_CN.md`](docs/architecture_CN.md).

## License

MIT
