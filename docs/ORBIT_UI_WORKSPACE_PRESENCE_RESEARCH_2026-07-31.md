# Orbit UI and Workspace Presence Research

**Date:** 2026-07-31
**Status:** research data only.
**Roadmap status:** not scheduled, not approved, not an implementation lane, and not a dependency of current V3 work.

## Purpose

Capture UI and interaction ideas observed in Orbit that may later inform Soma and Cortana interface design. This note records inspiration and possible missing concepts only. It creates no architectural commitment and does not modify `AGENTS.md`, `PLANS.md`, the V3 sequence, or any active gate.

## Source observations

Orbit presents one agent across several user surfaces: editor, terminal, embedded browser, Markdown vault, Git, skills, plugins, and MCP tools. Its product framing emphasizes shared context across those surfaces, visual browser interaction, and one continuing conversation rather than repeated manual handoffs.

Official pages reviewed:

- https://www.orbit.build/
- https://www.orbit.build/features
- https://www.orbit.build/how-it-works
- https://www.orbit.build/orbit-for-developers
- https://www.orbit.build/roadmap
- https://www.orbit.build/skills

Orbit's official pages currently contain inconsistent model-support descriptions. Some pages describe V1 as Claude-only, while other pages advertise broad multi-provider support. Any future comparison should therefore distinguish observed live behavior from marketing or roadmap claims.

## Research hypothesis: workspace and presence plane

The strongest potentially useful idea is a subordinate owner-facing workspace or presence model connecting what the owner and workers are currently seeing and doing.

A future UI projection might associate:

- canonical task and active run;
- repository, branch, and worktree;
- provider-native session;
- active terminal processes;
- relevant files, diffs, and artifacts;
- browser context and visual observations;
- documents and memory references;
- checkpoints;
- recent activity and pending owner decisions.

This would answer:

> What environment are Cortana and the active workers jointly looking at right now?

The concept must remain a projection or subordinate context object. It must not become another task lifecycle, execution authority, result publisher, or memory authority.

## UI ideas worth preserving for later evaluation

### Continuous owner-facing workspace

The owner should experience one continuing workspace even when individual workers are short-lived or replaced.

Possible design principle:

> Continuous company, continuous owner-facing workspace, discontinuous workers.

### Unified activity projection

A future Cortana interface could present a typed stream derived from canonical evidence, for example:

- worker started;
- file changed;
- command started or completed;
- browser observed;
- visual verification passed or failed;
- checkpoint created;
- decision requested;
- controller input supplied;
- result proposed;
- result accepted.

The stream would be a projection only, never the source of truth.

### Browser observation as evidence

Potential future UI research should consider browser screenshots, accessibility-tree observations, bounded interaction, before-and-after evidence, and visual acceptance checks attached to canonical runs.

### Workspace checkpoints

A future workspace checkpoint could bind repository state, provider cursor, relevant artifacts, and task/run version. Rewind should create a recoverable branch or superseding state rather than erase history.

### Simple owner modes

A future interface may benefit from owner-facing modes such as:

- Explore — observe and reason without mutation;
- Plan — propose tasks and decisions;
- Execute — use explicitly granted capabilities;
- Review — independently inspect evidence and proposed results.

These should be capability profiles, not new lifecycle states.

### Governed skills presentation

Future UI research should consider showing skill scope, version, source, required capabilities, trust status, compatibility, prior evidence, revocation, and supersession rather than presenting skills as ungoverned prompt files.

## Relationship to Soma

This research does not suggest replacing Soma, changing its destination, or turning it into an IDE. Orbit is useful here as evidence that continuity across visible surfaces matters to users.

Soma should continue owning canonical tasks, runs, authority, provider-session bindings, cancellation, recovery, memory, decisions, commitments, evidence, and acceptance. A future workspace or presence layer would make those systems coherent and understandable to the owner through Cortana.

## Deferred questions

- Should a workspace be ephemeral, durable, or both?
- Is one owner-facing workspace associated with a task, objective, project, or active executive session?
- Which observations belong in canonical evidence versus a derived UI cache?
- How should multiple concurrent workers appear without turning the interface into a swarm dashboard?
- What checkpoint semantics are useful without duplicating Task-to-Run authority?
- How should browser and terminal observations be redacted before owner-facing projection?

## Disposition

Keep this as research data for future UI and Cortana design review. Do not activate it, add it to the V3 sequence, or use it to interrupt the current implementation gate without a later explicit owner decision.
