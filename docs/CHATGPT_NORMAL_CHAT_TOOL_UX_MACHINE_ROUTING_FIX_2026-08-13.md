# ChatGPT Normal-Chat Tool UX - Machine Routing Fix - 2026-08-13

Status: `SOURCE FIX VALIDATED`

## Incident

A live DNSTM conversation was given an authorized request combining a non-repository configuration edit with a watchdog restart. ChatGPT initially chose the wrong Soma route. The same operation class worked once the conversation was directed to Soma's permissive executable/PowerShell route.

This is a Soma Tool UX routing defect: public tool descriptions did not distinguish the general machine-operation route sharply enough from repository and SSH-specific routes.

## Correct routing boundary

- `run_start`: canonical permissive fallback for authorized local machine commands and operations, including non-repository configuration edits and local service/watchdog/process changes.
- `repo_preview` / `repo_apply`: Git repository content and repository lifecycle only.
- `ssh_action`: administration on a registered remote SSH host; equivalent local-machine work uses `run_start`.

## Source correction

Updated `soma/public_tool_metadata.py` so discovery metadata names these boundaries directly and gives `run_start` the clearer title `Run authorized machine command`.

Added deterministic regression coverage in `tests/test_public_tool_metadata.py`.

Validation:

- focused metadata/descriptor tests: `22 passed`;
- expanded public discovery/gateway suite: `53 passed`;
- Ruff on changed Python files: passed.

No public input schema or operation inventory changed. This intentionally changes descriptor identity only.

## Activation boundary

The running Soma service must advertise the new descriptor identity before ChatGPT can benefit from the correction. An already-open conversation may retain older connector discovery metadata until refreshed or recreated.

No push is authorized by this record.
