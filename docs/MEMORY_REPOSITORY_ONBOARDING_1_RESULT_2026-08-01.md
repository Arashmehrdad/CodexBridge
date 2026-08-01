# MEMORY-REPOSITORY-ONBOARDING-1 Result

**Date:** 2026-08-01  
**Status:** implementation accepted; live action activation requires one Soma process restart and connector refresh  
**Branch:** `lane/memory-integration-foundation-1`  
**Push:** none

## Defect

A newly discovered repository could use Git/repository gateways because dynamic discovery inserted it into the in-memory repository registry, but canonical memory refused it because discovery did not create a ProjectScope repository binding. The internal ProjectScope bootstrap API existed, but no supported public onboarding action exposed it.

This was a genuine onboarding integration gap, not a failure of repository discovery or canonical memory isolation.

## Correction

Added the explicit write action:

```text
knowledge_action(action="memory_bind_repository", repo_name="...")
```

The action:

- resolves the exact trusted repository and canonical root;
- returns an existing active binding without mutation when one already exists;
- otherwise derives stable project/resource identities from the canonical repository identity hash;
- applies ProjectScope bootstrap idempotently;
- returns the exact `scope` required by later memory calls;
- preserves read-only discovery: `memory_scope` still never creates authority silently;
- publishes ProjectScope evidence and outcome hashes.

## Validation

The first focused run passed all new onboarding and memory paths but found the new action absent from the authoritative operation inventory. The inventory was corrected and the decisive targeted set passed:

```text
9 passed
```

The complete focused gateway, memory, discovery, schema, model, and inventory set then passed:

```text
319 passed in 175.83s
```

## Live repair

The existing `axon_modelling` repository was explicitly bound using the accepted deterministic bootstrap logic:

```text
project_id:  proj_repo_23058ce41311b76c56303da0
resource_id: res_repo_23058ce41311b76c56303da0
repo_name:   axon_modelling
root:        D:\Github\Axon_modelling
```

The committed `docs/PROJECT_MEMORY.md` handoff was then saved through the existing canonical `memory_save` gateway and read back successfully:

```text
memory_id:      kn_327b978b6acd2e4ca02569c517d33686
vault_path:     handoffs/axon-bus-project-memory.md
canonical_count: 1
canonical_health: healthy
```

The stored record retains the repository commit, source file path, source SHA-256, exact body, and canonical memory integrity hash.

## Activation

The source code and public operation inventory are committed at or after:

- `b718de0` — Add explicit memory repository onboarding
- `7fd0373` — Register memory repository onboarding operation

The running server predates these commits. One Soma process restart and ChatGPT connector refresh are required before controllers can call `memory_bind_repository` directly for future repositories.

## Disposition

The immediate `axon_modelling` memory failure is repaired. The general onboarding path is implemented and validated without weakening exact ProjectScope enforcement. The active V3 interaction-foundation architecture review remains unchanged.
