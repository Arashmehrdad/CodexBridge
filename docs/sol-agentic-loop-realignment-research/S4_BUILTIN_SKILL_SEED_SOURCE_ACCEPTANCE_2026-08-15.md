# S4 Built-in Skill Seed Source Acceptance

Date: 2026-08-15  
Stage: S4 - built-in/seed Skill packaging  
Verdict: **SOURCE ACCEPTED - NOT LIVE ACTIVATED**  
Repository: `D:\Github\Soma`  
Branch: `lane/memory-integration-foundation-1`

## 1. Authority

S4 was implemented only after S1, S2, and S3 source acceptance.

Normative authority:

- `docs/SOL_CONTINUATION_AND_SOMA_SKILL_LAYER_IMPLEMENTATION_PLAN_2026-08-15.md`
- `docs/SOL_CONTINUATION_AND_SOMA_SKILL_LAYER_FINAL_AUDIT_2026-08-15.md`

The final audit wins where it amends the implementation plan.

S4 goal:

> Promote useful repo-owned Skill drafts into standards-compliant seed packages without making the source repo the owner library.

The first required seed is `soma-engineering`.

## 2. Implementation commit

Implementation commit:

```text
889c06a370cfea296752d6b9245d41da6227ff1c
Package S4 built-in Skill seed
```

Exact range from S3 acceptance HEAD `5c3dc53be8809c41891b362b4b30fc3551a844c5`:

```text
M  pyproject.toml
M  soma/skills/__init__.py
A  soma/skills/builtin.py
A  soma/skills/seed_packages/soma-engineering/SKILL.md
A  tests/test_builtin_skill_seeds.py
```

Diff stat:

```text
5 files changed, 326 insertions(+)
```

No continuation, Task, Run, server, gateway-model, public-inventory, public-metadata, or operation-inventory source changed in S4.

## 3. Standards-valid built-in seed location

The research draft remains at:

```text
docs/chatgpt-tool-ux/soma-engineering-skill-draft/SKILL.md
```

It remains research evidence and was not rewritten.

The reviewed built-in package is materialized at:

```text
soma/skills/seed_packages/soma-engineering/
  SKILL.md
```

The immediate package parent is therefore exactly:

```text
soma-engineering
```

and the frontmatter Skill name is exactly:

```text
soma-engineering
```

This satisfies the Agent Skills parent-directory/name invariant already enforced by `SkillLibrary.import_directory()`.

## 4. Additional defect found in the research draft

The S4 focused gate discovered a second standards-validity problem in the research draft beyond the parent-directory mismatch documented by the plan.

The draft used an unquoted YAML value conceptually shaped as:

```yaml
description: Use when working on a software repository through Soma: inspect current state, ...
```

The colon after `Soma` is followed by a space, so strict YAML interprets it as mapping syntax and rejects the frontmatter.

The promoted seed corrects this mechanically by quoting the description:

```yaml
description: "Use when working on a software repository through Soma: inspect current state, ..."
```

The semantic wording is preserved. The historical research draft is left untouched.

## 5. Built-in seed helper boundary

S4 adds:

```text
soma/skills/builtin.py
```

Public Python helpers:

```text
BUILTIN_SKILL_SEED_NAMES
BUILTIN_SKILL_SEED_SOURCE_PREFIX
builtin_skill_seed_path(...)
import_builtin_skill_seed(...)
```

Current allowlist:

```text
("soma-engineering",)
```

The lookup is allowlist-driven rather than arbitrary path-driven.

Unknown names and traversal-like names are refused as missing built-in seeds.

## 6. Explicit import only

`import_builtin_skill_seed()` delegates to the existing S1 `SkillLibrary.import_directory()` authority.

It does not create a second Skill store, importer, revision model, current-pointer authority, or replay mechanism.

Mechanical provenance is fixed to:

```text
source_kind = repo_builtin_seed
source_ref  = soma-builtin://<skill-name>
```

The helper deliberately defaults to:

```text
make_current = False
```

Therefore merely shipping a seed or explicitly importing its revision does not make it the owner's current Skill.

A caller may explicitly request `make_current=True`; replacement of existing current state remains guarded by the already-accepted S1/S3 state-version semantics.

## 7. No automatic seed synchronization

A source scan for `import_builtin_skill_seed` found exactly three implementation references:

```text
soma/skills/builtin.py      definition
soma/skills/__init__.py     import/export
soma/skills/__init__.py     __all__ export
```

There is no invocation from:

```text
server startup
configuration loading
skill_query
skill_action
background service lifecycle
repository discovery
.agents/skills scanning
continuation resume
Task/Run startup
```

S4 therefore does not silently synchronize repo-owned seeds into any owner library.

## 8. Fresh-library import acceptance

The S4 tests explicitly create a fresh `SkillLibrary` and import `soma-engineering` through `import_builtin_skill_seed()`.

With explicit `make_current=True`, the result proves:

```text
name          = soma-engineering
created       = true
current       = true
state_version = 1
```

The resulting immutable revision records only the expected built-in provenance:

```text
(repo_builtin_seed, soma-builtin://soma-engineering)
```

The canonical revision package remains materialized through the S1 standards-valid content-addressed layout:

```text
<owner-library>/revisions/<package-hash>/soma-engineering/SKILL.md
```

## 9. Default import does not seize current state

A separate fresh-library case calls the helper without `make_current`.

It proves:

```text
created = true
current = false
current_skill_ref = ""
state_version = 0
```

This is the required separation between repo-owned seed source and owner-library current state.

## 10. Owner revision remains a normal immutable revision

The acceptance test then performs this sequence:

1. import the built-in seed and explicitly make it current;
2. create an owner/local revision of the same Skill through ordinary `SkillLibrary.import_revision()`;
3. make the owner revision current with the correct expected state version;
4. verify the owner revision has the built-in revision as normal parent lineage;
5. simulate a later/newer repo-owned seed package;
6. explicitly import that newer seed using the built-in helper's default `make_current=False` behavior.

The result proves all three immutable revisions coexist:

```text
original built-in seed
owner/local revision
newer repo-owned seed revision
```

and the owner revision remains current:

```text
current_skill_ref == owner skill_ref
state_version == 2
```

The later repo seed does not overwrite or repoint personal current state automatically.

## 11. Deterministic seed identity

Fresh source measurement run:

```text
20260815T161355Z_executable_profile_6bcabea6
```

Measured seed facts:

```text
seed_name        = soma-engineering
seed_parent      = soma-engineering
seed_file_count  = 1
seed_total_bytes = 4994
seed_package_hash = cdbcff0306b4588a7e33968e59ec30aa199440e48ff98a7d847d8d97581c454c
```

Canonical immutable Skill ref for the reviewed S4 seed:

```text
skill:soma-engineering@sha256:cbdcff0306b4588a7e33968e59ec30aa199440e48ff98a7d847d8d97581c454c
```

The hash is produced by the already-accepted whole-package manifest authority.

## 12. Distribution packaging

A repo-local seed is not honestly "built in" if it disappears from installed Soma distributions.

S4 therefore adds explicit setuptools package data:

```toml
[tool.setuptools.package-data]
soma = ["skills/seed_packages/*/SKILL.md"]
```

This was validated with an isolated temporary source snapshot, not by writing build artifacts into the Soma worktree.

Wheel proof run:

```text
20260815T160856Z_executable_profile_3a2fb761
```

Result:

```text
soma-0.1.0-py3-none-any.whl built successfully
seed_present = true
seed_bytes   = 4994
```

Exact wheel member checked:

```text
soma/skills/seed_packages/soma-engineering/SKILL.md
```

The temporary build directory was removed after inspection.

## 13. Focused S4/Skill acceptance

Initial focused run exposed the research-draft YAML issue described above. That run was not accepted.

After correcting only the promoted seed frontmatter, final focused run:

```text
20260815T160816Z_executable_profile_d41680e9
```

Result:

```text
60 passed in 11.00s
Ruff: PASS
git diff --check: PASS
```

Focused coverage includes:

```text
S1 Skill library foundation
S2 progressive Skill query
S3 Skill lifecycle gateway
S4 built-in seed packaging
```

## 14. Final cross-authority regression

Final S4 seal run:

```text
20260815T160949Z_executable_profile_3d834476
```

This is the accepted S3 650-test authority surface plus the six S4 built-in-seed tests.

Result:

```text
656 passed in 223.93s
Ruff: PASS
git diff --check: PASS
```

The durable run completed with:

```text
one worker
lease_generation = 1
launch_attempts = 1
no recovery
no relaunch
no cancellation
no stale-worker event
exit_code = 0
```

The regression covers the established Skill, continuation, Task, Run, ProjectScope, Hermes, gateway, public descriptor, flat-input, operation inventory, and gateway-model authorities.

## 15. Public topology is intentionally unchanged

S4 adds no MCP gateway and no gateway operation.

Fresh source identity measurement after the final seal:

```text
tool_count             = 38
operation_schema_count = 286
discovery_passes_converged = true
operation_schema_error = ""
```

Hashes are exactly unchanged from accepted S3:

```text
operation_inventory_hash = ffdcc0d5f7bb2d93316c3ce0b67de86b1d8f1dc35162316005b95a117417165b
public_schema_hash       = 5ef04e36efed1496ede40ffe3c51c8f8fe3de06255f0b9ecfda15905c4df8ebd
public_descriptor_hash   = e53780fa49bc31702e89601bd8f9b8db3844b15aeac5b77c0659a0e2171ebd60
```

Therefore S4 introduces exactly zero public topology drift.

## 16. Semantic authority audit

S4 does not add or restore:

```text
Skill router
Skill recommender
Skill execution runtime
skill_execute
subprocess execution
second reasoning model
semantic next-step engine
project-local automatic Skill discovery
native Skill synchronization
browser picker
```

The built-in package remains inert guidance.

Sol/ChatGPT remains the semantic controller. Soma remains the mechanical library/import authority.

## 17. Owner-library boundary

The canonical owner Skill library remains whatever location `SkillLibraryConfig` resolves for the owner/runtime.

The repo-owned seed package is only source material.

The seed directory is not:

```text
the owner library
current owner state
a native scanner root
a historical revision store
an automatically activated instruction source
```

No user-owned Skill such as `arash-research` was hard-coded into Soma source.

## 18. Concurrent work preservation

S4 operated in the shared worktree using selected managed writes/commits.

At implementation scope freeze, the concurrent `docs/soma-improvement-research/` lane contained 28 untracked research documents.

Those documents were not modified, staged, committed, deleted, moved, or incorporated into S4.

## 19. Runtime/live boundary

S4 is **source accepted only**.

Not performed:

```text
Soma service restart
connector refresh
live runtime activation
owner library mutation
automatic seed import
native Skill export/synchronization
push
Codex invocation
subagent invocation
```

The running connector therefore remains whatever pre-rollout source/runtime generation was already active before this stage.

## 20. S4 acceptance checklist

Plan acceptance:

```text
built-in seed is standards-valid                         PASS
seed can be imported into a fresh Skill library          PASS
subsequent owner revision is a normal immutable revision PASS
built-in source does not overwrite personal current      PASS
```

Additional hardening:

```text
seed survives wheel packaging                            PASS
built-in lookup is allowlisted                           PASS
import is explicit only                                  PASS
default import does not set current                      PASS
newer repo seed does not seize owner current state       PASS
public gateway identity unchanged                        PASS
no auto-sync call path                                   PASS
```

## 21. Verdict

**S4 BUILT-IN/SEED SKILL PACKAGING: SOURCE ACCEPTED - NOT LIVE ACTIVATED.**

The required `soma-engineering` research draft is now promoted into a standards-valid, installable, explicitly importable repo-owned seed package while remaining mechanically separate from owner-library authority.

S4 is complete.

The next mandatory sequential stage is:

```text
I1 - Integrated normal-Chat acceptance
```

I1 was not started in this stage.
