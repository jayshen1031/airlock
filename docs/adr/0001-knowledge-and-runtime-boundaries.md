# ADR 0001: Knowledge and runtime boundaries

- Status: accepted
- Date: 2026-08-29

## Context

Airlock needs durable product knowledge without becoming another memory,
knowledge-graph, publishing, or terminal-management platform. Its development
environment already uses MemHub and Nexus Decision, while users may run Airlock
from iTerm2, another terminal emulator, tmux, an IDE terminal, or CI.

## Decision

1. The Airlock Git repository is authoritative for source code, requirements,
   architecture, ADRs, tests, release notes, and issue/PR history.
2. Git workspace state and structured run artifacts are the runtime handoff
   between writer and reviewer. Agent conversation histories are not copied.
3. MemHub captures project-scoped Airlock sessions under `personal/airlock` for
   retrieval; Airlock's core package does not depend on MemHub.
4. Nexus Decision governs selected cross-project knowledge, accepted decisions,
   supersession, and Obsidian projection. Airlock does not implement its own
   Neo4j, Obsidian sync, or cross-project knowledge catalog.
5. Airlock is terminal-agnostic. Provider adapters use non-interactive CLI
   subprocesses and do not inspect or control existing terminal panes.
6. A documentation website may later be generated from repository sources.
   GitHub Pages or another static host is preferred initially. Cloudflare
   automation is added only when a concrete custom-domain, edge, or interactive
   requirement exists, and remains outside the review runtime.

## Consequences

- The open-source runtime remains small, portable, and independently useful.
- Project facts stay reviewable in Git, while personal cross-session and
  cross-project knowledge can still be discovered through existing systems.
- Obsidian and web publishing avoid duplicate pipelines and divergent truth.
- Users do not need Nexus Decision, MemHub, iTerm2, or Cloudflare to use Airlock.
