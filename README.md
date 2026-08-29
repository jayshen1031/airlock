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

## Review and repair workflows

```text
writer changes the repository
  -> airlock captures tracked, staged, and untracked changes
  -> an independent reviewer inspects them in read-only mode
  -> approve / reject with findings / blocked
  -> local, inspectable run artifacts
```

Requires Python 3.11+ and at least one authenticated provider CLI (`codex` or
`claude`) on `PATH`.

## Installation

Install directly from GitHub with `pipx`:

```bash
pipx install "git+https://github.com/jayshen1031/airlock.git"
```

For an editable contributor installation, clone the repository and use the
current directory. This is portable across paths and machines:

```bash
git clone https://github.com/jayshen1031/airlock.git
cd airlock
pipx install --editable .
```

Without `pipx`, use a virtual environment:

```bash
git clone https://github.com/jayshen1031/airlock.git
cd airlock
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --editable .
```

On Windows, activate the environment with `.venv\Scripts\activate` instead.
Confirm Airlock and the provider CLIs are available:

```bash
airlock --help
claude --version
codex --version
```

### Ubuntu and Debian (PEP 668)

Recent Ubuntu and Debian releases may reject a system-level `pip install` with
an `externally-managed-environment` error. Do not work around this with
`--break-system-packages`; install Airlock as an isolated application instead.

When `sudo` is available:

```bash
sudo apt update
sudo apt install -y pipx
pipx ensurepath
```

Start a new login shell, then install Airlock:

```bash
pipx install "git+https://github.com/jayshen1031/airlock.git"
```

Without `sudo`, create a persistent user-owned virtual environment (Python's
`venv` module must already be available):

```bash
python3 -m venv "$HOME/.local/share/airlock-venv"
"$HOME/.local/share/airlock-venv/bin/pip" install \
  "git+https://github.com/jayshen1031/airlock.git"
```

Add its executable directory to your shell profile (for example, `~/.bashrc`
or `~/.profile`) and start a new login shell:

```bash
export PATH="$HOME/.local/share/airlock-venv/bin:$PATH"
```

Both approaches persist across SSH sessions without modifying the operating
system's managed Python environment.

## Usage

Run Airlock from the Git repository you want to review, not from the Airlock
source directory:

```bash
cd your-project

airlock review \
  --reviewer claude \
  --task "Refactor authentication without changing token semantics"
```

Use Codex as the independent reviewer instead:

```bash
airlock review --reviewer codex --task "Fix issue #42"
```

Run an explicitly authorized, bounded repair loop:

```bash
airlock repair \
  --writer codex \
  --reviewer claude \
  --max-iterations 3 \
  --task "Fix issue #42 without changing the public API"
```

Airlock reviews first, passes only structured findings to the writer, then
re-runs the configured test gate and independent review. It stops on approval,
provider blockage, repeated findings, no workspace progress, a repeated prior
workspace state, forbidden Git revision changes, or the iteration limit. It
never commits, pushes, merges, resets, or attaches to existing terminal panes.

To run one explicit test command before review, commit `.airlock/config.toml`:

```toml
[gates.tests]
command = ["python", "-m", "pytest", "-q"]
timeout_seconds = 300
```

The command is executed directly without a shell, is terminated at the timeout,
and its bounded stdout/stderr are stored in `test-result.json` and supplied to
the reviewer. A failed test can never produce approval; timeout or launch
failure produces a blocked result. If the command changes auditable workspace
state, Airlock leaves the changes intact and blocks before reviewer invocation.
Malformed gate configuration also produces an auditable blocked result. If the
file is absent, Airlock retains the review-only workflow.

Configuration is limited to 64 KiB, and `timeout_seconds` must not exceed 3600.

Exit codes are stable for scripting:

- `0`: approved;
- `1`: rejected with actionable findings;
- `2`: blocked, including provider failure or malformed output;
- `3`: Airlock/Git error or detected reviewer workspace mutation.

Each invocation writes task, captured change material, schema, state, provider
metadata, and the validated verdict under `.airlock/runs/<run-id>/`. These run
artifacts are local and ignored by Git.

Airlock does not attach to existing terminal panes or run an unbounded autonomous
loop. Cross-process resume and external cancellation remain follow-up work;
interrupting the synchronous command records a canceled state.

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
