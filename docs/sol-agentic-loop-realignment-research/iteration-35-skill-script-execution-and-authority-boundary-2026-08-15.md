# Iteration 35 - Skill Script Execution and Authority Boundary

Date: 2026-08-15
Status: research only; repo-backed authority result
Track: Sol-centric agent interface + Soma Skill layer

## Question

How should Soma treat executable code bundled in Agent Skills without allowing a Skill package to create a second execution/authorization path?

## External evidence

The Agent Skills open specification explicitly allows:

```text
scripts/
```

containing executable code. Supported languages depend on the agent implementation; common examples are Python, Bash and JavaScript.

The specification also defines an optional `allowed-tools` field, but labels it experimental and warns that support varies between agent implementations.

OpenAI's ChatGPT Skills documentation also states that uploaded Skills can contain instructions, supporting files and code; uploaded Skills are scanned before they become available, and users are still expected to review and trust the source.

Primary sources:

- https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx
- https://help.openai.com/en/articles/20001066-skills-in-chatgpt

## Current Soma repo evidence

Soma already has explicit execution authorities.

The current public `run_start` request surface contains typed durable execution operations including local PowerShell/executable profiles, remote PowerShell, parallel execution and Hermes operations.

`JobManager.start_executable_profile()` resolves the target repository, builds a normalized executable request, and routes it into the existing durable Run lifecycle.

The existing `soma-engineering` Skill draft already states the correct principle:

> the Skill is workflow guidance and does not grant permissions, replace server authorization, or weaken Soma validation.

It also tells Sol to use durable execution for tests/scripts rather than creating another execution mechanism.

## Candidate approaches

### A. Skill runtime executes bundled scripts directly

Rejected.

This would create a new process-launch authority parallel to `run_start`/Task/Run and would bypass existing:

- durable Run identity;
- execution evidence;
- repository resolution;
- process containment;
- cancellation/recovery;
- configured execution/profile boundaries;
- future direct Run idempotency.

### B. Treat `allowed-tools` as Soma authorization

Rejected.

The Agent Skills field is experimental and client-specific. More importantly, a Skill package is not an authority source in Soma.

A package must not be able to grant itself:

```text
run_start
repo_apply
ssh_action
cloudflare_action
Docker mutations
provider access
```

`allowed-tools` may be preserved as package metadata/compatibility information for interoperability, but Soma must not interpret it as a grant of capability.

### C. Skill script is inert until Sol explicitly invokes existing Soma execution

Preferred.

Normal flow:

```text
skill_query.get(skill_ref)
  -> SKILL.md says a helper script may be useful

skill_query.resource(skill_ref, "scripts/helper.py")
  -> exact immutable script/resource identity/content

Sol decides whether execution is useful

Sol -> existing Soma execution gateway
  -> normal authority/validation/durability
  -> canonical Run/Task evidence
```

No Skill-specific executor is introduced.

## Script identity

If script execution is supported from the canonical Skill Library, execution should preserve mechanical provenance such as:

```text
skill_ref
relative_resource_path
resource_hash
```

This is provenance only.

It must not change the meaning of the canonical Run request or make Skill state the Run authority.

The exact script bytes executed must correspond to the immutable Skill revision/resource hash, avoiding a time-of-check/time-of-use substitution after retrieval.

## Execution transport options

The implementation thread may choose the safest mechanical transport supported by existing Soma execution architecture, for example:

- stage exact immutable script bytes into a Run input/artifact boundary and execute from staging;
- materialize a verified read-only/copy-on-run resource into an approved working directory;
- use an existing executable profile that accepts a verified script artifact.

Research does not choose the implementation detail yet.

The invariant is more important:

> execution must pass through existing Task/Run authority and the bytes executed must be bound to the immutable resource identity.

## Repository lock interaction

A Skill script does not get special lock semantics.

If the execution mutates a repository/resource, existing Soma locking/scope authority applies.

If it is a non-mutating durable job, existing execution semantics decide whether a repository lock is needed.

The Skill package cannot declare itself lock-free.

## Remote/network behavior

A Skill may contain instructions or code that would use network access, but the Skill itself does not grant remote/network authority.

If the action requires SSH, Cloudflare, Docker/provider access or another external surface, Sol must route through the corresponding Soma gateway where that gateway owns the effect.

Do not hide external provider effects behind a generic Skill-script launcher when a canonical Soma domain gateway already exists.

## Uploaded/untrusted Skills

OpenAI's own product scans uploaded Skills and still instructs users to review/trust their source.

For Soma, package provenance and immutable hashing are therefore important, but static scanning should not be treated as sufficient authorization.

A later implementation may add import validation/scanning, but the core safety architecture does not depend on perfect malware classification:

```text
untrusted package instructions cannot create authority
script execution still requires normal Soma effect path
```

## Progressive disclosure

Do not load or stage all scripts when a Skill is discovered.

Follow the open standard's progressive-disclosure model:

```text
search/list -> metadata only
get -> SKILL.md
resource -> exact requested script/reference/asset
execution -> only after explicit Sol action
```

This keeps Skill content out of normal context and avoids accidental execution semantics.

## Relationship to continuation

No special continuation rule is required.

If a Skill-derived script launches a durable Task/Run and Sol supplies the continuation context ref, the normal continuation effect-link mechanism may associate that canonical effect.

The Skill itself does not become continuation authority.

## Repo-backed recommendation

Soma should implement Skill script support as **resource retrieval + existing execution**, not as a new Skill executor.

The exact existing ownership point is:

```text
Skill Library -> immutable resource authority
Run/Task -> execution authority
```

This matches current Soma architecture and the existing `soma-engineering` Skill draft.

## Verdict

**REPO-BACKED AUTHORITY RESULT.**

Bundled Skill code is inert content until Sol deliberately routes it through an existing Soma execution authority. The experimental Agent Skills `allowed-tools` field must never become a Soma permission grant.

This iteration does not authorize implementation.
