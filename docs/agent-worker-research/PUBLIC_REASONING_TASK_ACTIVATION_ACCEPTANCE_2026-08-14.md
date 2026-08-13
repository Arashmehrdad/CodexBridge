# Public Reasoning Task Activation Acceptance - 2026-08-14

Status: `ACCEPTED_OWNER_GATED_EXISTING_TASK_SURFACE`

## Decision

Normal ChatGPT does not receive new Mission, PlanRevision, WorkPackage, FanIn, or provider-specific MCP tools in this stage.

The public/runtime surface remains the existing canonical Task pair:

- `task_action` gains `start_reasoning`;
- `task_query` gains `evidence`.

Graph orchestration remains internal to Soma. The controller therefore sees one canonical Task lifecycle rather than a second public worker lifecycle.

## Activation boundary

Production repository reasoning is owner-gated and disabled by default. Source support for the route does not activate it.

When the gate is disabled:

- no production reasoning backend is constructed;
- Task capabilities do not advertise `reasoning` or `soma_reasoning`;
- `start_reasoning` returns `reasoning_backend_not_activated` before backend work;
- exposing the public request schema does not imply a provider call.

This acceptance does not enable the runtime gate.

## Public start contract

`start_reasoning` is provider-neutral at the public boundary. The request contains controller identity, project identity, repository, objective, optional instructions, and optional parent Task identity.

Before backend launch Soma freezes the repository's current committed `HEAD` into an immutable content-addressed assignment. Uncommitted working-tree content is not part of the authoritative worker source revision.

Canonical Task remains lifecycle authority. The reasoning backend remains subordinate execution/evidence authority.

## Evidence contract

`task_query evidence` retrieves the bounded mechanically verified `EvidenceSubmission` for a reasoning Task.

The response preserves exact assignment, source revision, locator, provenance, and publication identities. Raw provider event streams remain behind references. Soma does not semantically truncate the submission and does not judge whether a selected source range proves a worker claim.

`EvidenceSubmissionV1` has a 32 KiB hard serialized ceiling. The public evidence request permits up to 64 KiB so the complete bounded submission can be wrapped with Task projection metadata.

## Authority boundary

```text
reasoning worker
    -> semantic analysis and evidence choice

Soma
    -> lifecycle, immutable assignment identity, source/path/range mechanics,
       provenance, replay/recovery, bounded evidence publication

Sol
    -> semantic adjudication and synthesis
```

Missing evidence or weak evidence choice remains a semantic quality issue unless the mechanical contract itself is invalid.

## G6/G7 relationship

The G6 provider route remains accepted under the owner-directed budget closure. `CANONICAL_CONCURRENCY` remains `UNSELECTED`.

G6.4 and G7 remain deferred optimization/research gates. They are not completed and are not used by this activation to set runtime authority or topology. Reopening provider-expensive work still requires fresh explicit owner authorization.

## Validation

Final committed-source focused validation:

```text
run: 20260813T220903Z_executable_profile_69e9990d
result: 194 passed
ruff: all checks passed
exit_code: 0
```

Additional reasoning lifecycle/recovery validation:

```text
run: 20260813T220514Z_executable_profile_766f503d
result: 21 passed
ruff: all checks passed
exit_code: 0
```

These validation paths use deterministic/scripted or fake reasoning backends. No live provider generation is part of these tests.

## Runtime convergence

Implementation commit:

```text
1092dbc8eccfac88a9c6ef5b04cf5c667b2070e8
Add owner-gated reasoning Task activation
```

After restart:

```text
self_check: 10/10 green
server_build_hash: 248cfff9e8615435567acd26522f4829f79d051be6116eacce93a5d66d6042a7
public_schema_hash: f6b6ac6936ce5a424489120e712372906b0f410426e4c43120feb14c13536d8b
```

Live Task capabilities still advertised only `durable_command` and `soma_durable_run`, proving the provider route is source-available but owner-disabled.

## Tool UX decision

The normal-Chat activation choice is:

`EXISTING_TASK_SURFACES_ONLY`

Not selected:

- explicit public Mission/Plan graph tools;
- provider-specific reasoning tools;
- a second worker lifecycle surface;
- automatic provider activation.

## Final gate

`PUBLIC_TASK_REASONING_SURFACE_ACCEPTED`

`NO_GRAPH_TOOL_SPRAWL`

`PROVIDER_ROUTE_DISABLED_BY_DEFAULT`

`NO_LIVE_PROVIDER_GENERATION_USED`

`SOL_REMAINS_SEMANTIC_ADJUDICATOR`

`G6_CONCURRENCY_REMAINS_UNSELECTED`

`G6.4_DEFERRED`

`G7_DEFERRED`
