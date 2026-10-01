# Installation, updates, and CLI reference

For the everyday AI-runtime workflow, start with the [README](../README.md).
This guide covers manual setup, updates, troubleshooting, and direct CLI usage.

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

## Updating an existing installation

You normally do not need to uninstall Airlock first. The exact update command
depends on how that machine installed it.

First identify the executable and its owning environment instead of assuming
that `pipx` manages it:

```bash
command -v airlock
readlink -f "$(command -v airlock)"
pipx list
```

If `pipx list` has no Airlock entry, use the resolved executable path to locate
its virtual environment and run that environment's `pip show airlock-agent`.
An `Editable project location` means the installed command reads code directly
from that directory.

For a `pipx` installation made directly from GitHub, rebuild the managed
environment from its recorded source specification:

```bash
pipx reinstall airlock-agent
airlock --help
```

This command applies only when the current user's `pipx list` actually contains
`airlock-agent`. `reinstall` replaces only Airlock's isolated environment; it
does not affect project repositories, `.airlock/runs/`, or the separately
installed provider CLIs.

For an editable contributor installation, update the checkout first. Editable
installs use that checkout directly, while reinstalling refreshes package
metadata and dependencies:

```bash
cd /absolute/path/to/airlock
git pull --rebase
pipx install --force --editable .
airlock --help
```

For an editable virtual-environment installation:

```bash
cd /absolute/path/to/airlock
git pull --rebase
. .venv/bin/activate
python -m pip install --upgrade --editable .
airlock --help
```

If the editable location is an extracted archive or another static directory
without `.git`, `git pull` cannot update it and `pip install --upgrade` will
continue reading the stale copy. Replace that editable link with a GitHub
installation in the same environment instead:

```bash
V="$HOME/.local/share/airlock-venv"
"$V/bin/pip" uninstall -y airlock-agent
"$V/bin/pip" install --upgrade --force-reinstall \
  "git+https://github.com/jayshen1031/airlock.git"
hash -r
"$V/bin/airlock" --help
```

Adjust `V` to the environment revealed by the resolved executable path. Before
deleting the old editable source directory, inspect it for project-local
`.airlock/`, `.memhub/`, and `configs/` content that may need to be preserved.

For the persistent user-owned virtual environment shown below, reinstall the
current GitHub source into the same environment:

```bash
"$HOME/.local/share/airlock-venv/bin/pip" install \
  --upgrade --force-reinstall \
  "git+https://github.com/jayshen1031/airlock.git"
"$HOME/.local/share/airlock-venv/bin/airlock" --help
```

An explicit uninstall is only useful when changing installation method,
removing a stale editable link, or repairing a broken environment. In those
cases, remove the old installation with `pipx uninstall airlock-agent` or the
matching environment's `python -m pip uninstall airlock-agent`, then follow the
installation instructions above. Do not delete project `.airlock/runs/` merely
to upgrade the CLI.

The package version may remain unchanged between unreleased Git commits, so
`pip show airlock-agent` alone does not prove that an update succeeded. A Git
installation records its source commit in `direct_url.json`; inspect it with
the environment's Python and compare `vcs_info.commit_id` with the intended
upstream commit:

```bash
"$V/bin/python" -c \
  'import importlib.metadata as m; print(m.distribution("airlock-agent").read_text("direct_url.json"))'
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

## Direct CLI usage

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

After installing or updating Airlock, smoke-test the Codex structured-output
path from a Git repository:

```bash
airlock review \
  --reviewer codex \
  --task "Smoke-test the Codex reviewer. Report the current changes accurately."
```

A successful invocation prints its artifact directory and readable report
path. A clean workspace can legitimately produce an approval with no findings:

```text
APPROVE
No reviewable uncommitted changes are present.
Artifacts: /path/to/project/.airlock/runs/<run-id>
Readable report: /path/to/project/.airlock/runs/<run-id>/review.md
```

The human-readable `review.md` groups the result as:

```markdown
### 合理
- Evidence-backed behavior that is correct.

### 不合理
- [HIGH] `src/example.py:42`: An actionable problem.

### 建议
- The concrete recommended repair.
```

The same verdict remains available for automation in `review.json`:

```json
{
  "verdict": "approve",
  "summary": "No reviewable uncommitted changes are present.",
  "reasonable": ["The tracked and staged diffs are empty."],
  "findings": []
}
```

If Codex fails before review with `invalid_json_schema` and reports that
`reasonable` is missing from `required`, the machine is running a stale Airlock
build. Follow the update-source diagnosis above, reinstall from the current
GitHub source, and rerun the smoke test. A provider failure is `BLOCKED`; it is
not a review conclusion and must not be treated as one side of a completed
cross-review.

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
when only low-severity findings remain, provider blockage, repeated findings,
no workspace progress, a repeated prior workspace state, forbidden Git revision
changes, or the iteration limit. Low-only findings produce a `minor_findings`
state and exit code `1`; they are not silently converted to approval. Airlock
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
artifacts are local and ignored by Git. A single review includes `review.md`.
A repair run also includes `review-report.md`, which preserves the original
input and presents every round as `合理`, `不合理`, and `建议`. The JSON files
remain the machine-readable audit source.

Airlock does not attach to existing terminal panes or run an unbounded autonomous
loop. Cross-process resume and external cancellation remain follow-up work;
interrupting the synchronous command records a canceled state.
