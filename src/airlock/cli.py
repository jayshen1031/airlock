"""Airlock command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from airlock.adapters import ClaudeAdapter, CodexAdapter, ProviderError
from airlock.git_workspace import GitWorkspaceError
from airlock.models import ReviewResult, Verdict
from airlock.repair import repair_repository
from airlock.review import ReviewerMutationError, review_repository


EXIT_APPROVED = 0
EXIT_REJECTED = 1
EXIT_BLOCKED = 2
EXIT_ERROR = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="airlock",
        description="Terminal-first cross-agent coding review",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    review = subcommands.add_parser("review", help="review current Git changes")
    review.add_argument("--reviewer", choices=("claude", "codex"), required=True)
    review.add_argument(
        "--task",
        default="Review the current repository changes.",
        help="task or acceptance criteria the changes should satisfy",
    )
    review.add_argument("--cwd", type=Path, default=Path.cwd())
    review.add_argument("--timeout", type=float, default=600)
    repair = subcommands.add_parser(
        "repair", help="review and run a bounded findings-driven repair loop"
    )
    repair.add_argument("--writer", choices=("claude", "codex"), required=True)
    repair.add_argument("--reviewer", choices=("claude", "codex"), required=True)
    repair.add_argument("--task", required=True)
    repair.add_argument("--cwd", type=Path, default=Path.cwd())
    repair.add_argument("--timeout", type=float, default=600)
    repair.add_argument("--max-iterations", type=int, default=3)
    return parser


def _print_result(result: ReviewResult, run_path: Path) -> None:
    print(result.verdict.value.upper())
    print(result.summary)
    for finding in result.findings:
        location = finding.file or "repository"
        if finding.line is not None:
            location = f"{location}:{finding.line}"
        print(f"- [{finding.severity.value.upper()}] {location}: {finding.issue}")
        if finding.suggestion:
            print(f"  Suggestion: {finding.suggestion}")
    print(f"Artifacts: {run_path}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    adapters = {"claude": ClaudeAdapter, "codex": CodexAdapter}
    try:
        if args.command == "review":
            result, store = review_repository(
                repository=args.cwd,
                task=args.task,
                adapter=adapters[args.reviewer](),
                timeout_seconds=args.timeout,
            )
        else:
            result, store = repair_repository(
                repository=args.cwd,
                task=args.task,
                writer=adapters[args.writer](),
                reviewer=adapters[args.reviewer](),
                max_iterations=args.max_iterations,
                timeout_seconds=args.timeout,
            )
    except (
        GitWorkspaceError,
        ProviderError,
        ReviewerMutationError,
        ValueError,
        OSError,
    ) as exc:
        print(f"airlock: {exc}", file=sys.stderr)
        return EXIT_ERROR
    _print_result(result, store.artifact_path)
    if result.verdict is Verdict.APPROVE:
        return EXIT_APPROVED
    if result.verdict is Verdict.REJECT:
        return EXIT_REJECTED
    return EXIT_BLOCKED


if __name__ == "__main__":
    raise SystemExit(main())
