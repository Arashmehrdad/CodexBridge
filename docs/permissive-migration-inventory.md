# Permissive-Only Migration Inventory

This inventory records the compatibility surfaces that remain after G1 and must be evaluated during C1, after unrestricted local PowerShell and parallel fan-out have passed their acceptance gates.

## Active installation state

- `config.yaml` activates only the `permissive` SSH autonomy profile.
- `JobManager._require_active_ssh_autonomy_profile` rejects disabled SSH profiles before durable run or repository-lock creation.
- SSH capability output reports both configured active profiles and compatibility-supported profiles.
- Permissive structured, reviewed-script, and root-shell routes remain active during migration.

## Runtime profile-routing candidates

The following files still carry compatibility routing or policy behavior for `conservative` and `balanced` SSH autonomy profiles and should be reviewed for removal or simplification in C1:

- `codexbridge/config.py`: `SSHConfig.active_autonomy_profiles` schema and compatibility defaults.
- `codexbridge/job_manager.py`: active-profile gate and legacy structured/reviewed-script launch paths.
- `codexbridge/ssh_policy.py`: mode/profile authorization matrix and delegated-approval metadata.
- `codexbridge/ssh_tools.py`: capability reporting for active and compatibility-only profiles.
- `codexbridge/gateway_models.py`: structured, reviewed-script, and root-shell request variants.
- `codexbridge/server.py`: SSH action delegation and compatibility route forwarding.
- `codexbridge/job_worker.py`: persisted policy revalidation for structured and reviewed-script runs.

## Configuration candidates

- `config.example.yaml` still demonstrates all three canonical autonomy profiles and must become permissive-only when C1 migration begins.
- `codexbridge/config.py` still defaults `active_autonomy_profiles` to all three canonical profiles for compatibility.
- Existing user configuration migration must preserve rollback information and must not silently delete durable run history.

## Test and fixture candidates

Compatibility-profile assertions remain primarily in:

- `tests/test_config.py`
- `tests/test_job_manager.py`
- `tests/test_ssh_policy.py`
- `tests/test_ssh_tools.py`
- `tests/test_ssh_worker.py`
- `tests/test_tool_gateway_models.py`

C1 should replace these with permissive-only assertions where behavior is superseded, while retaining tests for deterministic rejection of removed or disabled legacy values during the migration window.

## Documentation candidates

- `README.md`
- `config.example.yaml`
- `docs/domain-tool-gateway-migration.md`
- `docs/domain-tool-gateway-progress.md`
- `PLANS.md`

Documentation must distinguish SSH autonomy profiles from approval terminology.

## Terminology that is not an autonomy profile

Strings such as `T4_WRITE_APPLY_CHATGPT_DELEGATED`, `T5_COMMIT_PRIVATE_BRANCH_CHATGPT_DELEGATED`, `allowed_with_chatgpt_delegated_approval`, and `chatgpt_delegated_allowed` belong to the general approval and permission-tier model. They are not SSH autonomy-profile names and must not be removed merely because C1 removes compatibility execution profiles. Any later cleanup of approval terminology requires a separate policy migration and evidence gate.

## Restricted-wrapper candidates after PowerShell parity

The following command surfaces are potential cleanup targets only after X2 and X2A acceptance proves replacement parity:

- restricted local project-command starters and command profiles that PowerShell can invoke directly;
- legacy reviewed-script wrappers whose only remaining value is command filtering;
- bounded SSH administration wrappers superseded by unrestricted remote PowerShell or retained root-shell/controller facilities;
- obsolete command-profile definitions and workflow step adapters tied only to removed wrappers.

Repository query, preview, apply, revert, move, commit, validation, durable lifecycle, locks, transfers, remote-controller, artifacts, workflows, supervisors, status, cancellation, recovery, and audit tooling remain retained control-plane primitives.

## Before/after capability matrix

| Current surface | Current active callers | Retained replacement | C1 disposition |
| --- | --- | --- | --- |
| SSH `conservative` autonomy routing | Compatibility tests and explicitly configured legacy installations only | `permissive` SSH routing with operating-system and remote-account boundaries | Stop activating by default now; remove schema and runtime routing only after deterministic config migration is implemented. |
| SSH `balanced` autonomy routing | Compatibility tests and explicitly configured legacy installations only | `permissive` structured, reviewed-script, and root-shell routing | Stop activating by default now; remove with the same migration unit as `conservative`. |
| Local `project_command` public operation | Workflow worker, local-agent runner, local-coding manager, supervisor flow, scoped validation helpers | Unrestricted PowerShell for arbitrary commands; retained typed validation operations for safe focused checks | Keep until each internal caller is classified; remove only the arbitrary-command use case, not scoped validation primitives. |
| Local synchronous `run_project_command` compatibility tool | Legacy callers and benchmark/discovery fixtures | Durable `run_start` plus typed validation or unrestricted PowerShell | Remove after confirming no live connector caller depends on synchronous execution. |
| SSH reviewed-script wrapper | Public SSH gateway and durable worker | Retain temporarily for remote transport and durable ownership until R4/X4 parity exists | Not removable in the first C1 slice. Command filtering alone is not sufficient justification to retain it after remote PowerShell parity. |
| SSH administration wrappers | Public SSH administration gateway | Transfer/controller primitives and future unrestricted remote PowerShell | Defer until R3/R4/X4 because current wrappers still provide transport and staging behavior. |
| Durable run history and protected artifacts from removed tools | Run store, result publication, audit and recovery tooling | Existing durable lifecycle and explicit retention policy | Always retain; route removal must never delete historical evidence. |

## First independently removable compatibility unit

1. Default `SSHConfig.active_autonomy_profiles` to `permissive` only.
2. Update `config.example.yaml` and default-value tests to match.
3. Continue accepting explicit legacy profile lists during the migration window so existing configuration remains loadable and rollback-capable.
4. In the next unit, add a deterministic migration report for explicit legacy values before narrowing the schema or deleting runtime branches.

## C1 execution checklist

1. Produce a before/after capability matrix for every candidate route. **Complete for the current candidate set; refine as call sites are migrated.**
2. Confirm an accepted unrestricted-PowerShell replacement or explicitly abandon the capability.
3. Migrate active callers and configuration deterministically.
4. Remove runtime routes, schemas, tests, fixtures, examples, and documentation together.
5. Preserve durable historical runs and protected evidence under an explicit retention policy.
6. Run focused tests, the full suite, `python -m pip check`, `git diff --check`, and live PowerShell/parallel acceptance tests before declaring cleanup complete.
