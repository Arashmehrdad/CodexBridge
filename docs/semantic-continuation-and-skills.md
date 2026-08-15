# Semantic Continuation and Portable Skills

Status: active v1 runbook

Soma's continuation and Skill layers extend normal Chat without creating another semantic controller.

```text
Sol / ChatGPT = semantic reasoning and action choice
Soma          = durable re-entry, Skill storage/retrieval, tools and execution truth
```

Continuation is semantic re-entry, not a reasoning engine. Skills are portable guidance packages, not executable authorities.

## Continuation

Public gateways:

- `continuation_query`: capabilities, list, status, resume, handoffs, effects;
- `continuation_action`: open, update_contract, checkpoint, complete, cancel.

The current continuation contract revision ID is the opaque `continuation_context_ref`. It identifies the governing continuation revision; it is not an authorization token.

Use continuation when an objective may need to survive interruption, compaction, a fresh Chat or a surface change. Ordinary one-turn work does not require continuation ceremony.

A typical fresh-Chat recovery is:

```text
owner: continue
Sol -> continuation_query.resume(...)
    -> inspect current Task/Run/repository/service truth as needed
    -> reason normally
    -> use ordinary Soma tools
```

Handoff prose is an opaque hint. It is never current-world truth by itself. Fresh Sol must independently re-check live state when correctness depends on it.

Task and participating direct single-Run starts may carry an explicit continuation origin. Soma never guesses one. Once associated with a stable logical request, replay cannot silently relink, detach or substitute a different continuation origin.

Completed or cancelled continuations remain readable for history/resume but cannot admit new continuation-sensitive writes or associated work.

## Skills

Public gateways:

- `skill_query`: capabilities, list, search, get, history, resource;
- `skill_action`: import_revision, set_current, rollback, enable, disable.

Discovery returns bounded metadata. Sol decides whether a Skill is useful and which instructions apply. Soma does not run a semantic Skill router and does not merge conflicting Skill semantics.

Exact immutable Skill references use:

```text
skill:<name>@sha256:<whole-package-hash>
```

The package hash covers every regular file in the canonical package. Symlinks are rejected in v1. Historical revisions remain immutable and exact-retrievable.

Repository-local `.agents/skills/...` packages are not automatically imported or activated. Built-in reviewed seed packages are also explicit imports; importing a seed does not silently replace the owner's current revision.

`skill_query.resource` only retrieves a bounded immutable package resource. A script bundled inside a Skill is inert until Sol explicitly invokes an existing Soma execution authority such as `run_start`.

## Skill library configuration

The safe development default is the runs-internal library:

```yaml
skill_library:
  skill_library_root: ""
  skill_library_kind: "runs_internal_development"
  max_files: 256
  max_total_bytes: 16777216
  max_file_bytes: 4194304
```

With that configuration Soma resolves the library to `<runs_dir>/skills`.

For an owner-selected external private library, configure an absolute root:

```yaml
skill_library:
  skill_library_root: "D:/SomaSkills"
  skill_library_kind: "external_private_library"
```

`external_private_library` without an absolute root is rejected.

## Compatibility

The v1 layers are additive:

- historical Runs without logical request identity remain readable;
- existing Task calls continue to work without continuation context;
- ordinary Soma effect tools continue to work without continuation;
- repository and canonical project-memory authorities are unchanged;
- project-local Skill auto-discovery is not part of v1;
- Company remains a separate architecture/lane;
- owner-gated reasoning-worker infrastructure, where retained, is not part of continuation or Skill routing.

## Current accepted public identity

At the I1/I2 programme boundary the live/source public identity is:

- 38 public gateways;
- 286 operation schemas;
- public schema hash `5ef04e36efed1496ede40ffe3c51c8f8fe3de06255f0b9ecfda15905c4df8ebd`;
- public descriptor hash `e53780fa49bc31702e89601bd8f9b8db3844b15aeac5b77c0659a0e2171ebd60`;
- operation inventory hash `ffdcc0d5f7bb2d93316c3ce0b67de86b1d8f1dc35162316005b95a117417165b`.

The identity must be re-measured after any later public-surface change rather than copied forward by assumption.
