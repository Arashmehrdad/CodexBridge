# SSH-A1 — Agent-Driven Credential Binding and Transactional Host Activation

Status: **active implementation plan selected by the owner on 2026-07-25**.

## Objective

Add one global SSH onboarding and migration capability that lets the controller configure any supported remote host from credential material stored at a local location chosen by the owner.

The owner interaction must be limited to a natural-language instruction such as:

```text
The credentials for the new VPS are at C:\Users\arash\Secrets\new-vps.env.
Wire it as production_vps and move project_x to it.
```

The controller and Soma must then perform credential-source discovery, field binding, host-key handling, authentication testing, capability discovery, project validation, activation, and rollback without asking the owner to edit `config.yaml`, `.env`, OpenSSH configuration, `known_hosts`, deployment profiles, or project bindings manually.

## Owner interaction contract

The normal path is zero-prompt after the owner supplies:

- the local credential location or an existing OpenSSH alias;
- the intended host identity or migration intent;
- the project to bind when a project migration is requested.

The controller must:

1. inspect the source through a dedicated secret-safe Soma operation rather than reading it into chat or ordinary PowerShell output;
2. infer the source format and available field names;
3. map canonical SSH fields automatically when the mapping is deterministic;
4. create a hash-bound preview;
5. apply the preview through a durable candidate-validation transaction;
6. report the activated host, fingerprint, discovered capabilities, project bindings, and evidence IDs.

If the source is incomplete or genuinely ambiguous, Soma must fail closed with machine-readable missing or ambiguous field names. The controller should resolve the issue from source metadata or the owner's original instruction whenever possible. It must not reveal values or ask the owner to copy secret material into chat.

## Scope

SSH-A1 is global. It must work for ordinary VPS hosts, cloud VMs, private-network hosts, RunPod-style endpoints, Windows OpenSSH hosts where supported, and future servers without embedding project-specific assumptions in Soma.

The lane includes:

- local credential-source registration and safe probing;
- reference-based host profiles;
- managed host-key and fingerprint lifecycle;
- durable candidate authentication and capability discovery;
- separate project-to-host bindings;
- atomic activation and rollback;
- agent-driven public gateway operations;
- migration of existing literal and alias-based profiles without breaking them.

## Non-goals

The first implementation does not:

- accept raw private-key content through MCP arguments, chat, YAML, or `.env`;
- enable SSH password authentication or keyboard-interactive authentication;
- replace an encrypted operating-system secret store;
- expose arbitrary OpenSSH options or arbitrary shell text;
- silently accept a changed host key for an existing active endpoint without explicit migration or rotation intent;
- create project-specific Andiya, QuoteFollow, RunPod, or other hard-coded migration logic;
- require new paid infrastructure for validation.

A later secret-store adapter may add Windows Credential Manager or another encrypted provider behind the same credential-source interface.

## Current baseline

Soma already provides:

- `ssh_query` capability, profile-preview, and profile-status operations;
- `ssh_action.profile_apply`;
- add, replace, and remove host mutations;
- command-profile upsert and removal;
- candidate configuration hashing and stale-config rejection;
- atomic config replacement and restoration on reload failure;
- non-interactive key-based SSH with password, keyboard-interactive, forwarding, and agent forwarding disabled;
- host health, environment, GPU, filesystem, service, Docker, Git, and process inspection;
- durable SSH command, transfer, deployment, reviewed-script, and root-shell execution.

The current activation callback validates and reloads configuration only. It does not resolve generic credential references, verify a candidate host fingerprint, test candidate authentication, persist a capability snapshot, validate project bindings, or make those checks part of rollback.

## Target configuration model

### Credential sources

Add reusable credential sources under the global SSH configuration:

```yaml
ssh:
  credential_sources:
    production_vps_source:
      type: env_file
      path: "C:/Users/arash/Secrets/production-vps.env"
```

Supported first-release source types:

- `env_file` — an absolute local dotenv-style file;
- `process_environment` — named variables already present in the Soma service environment;
- `openssh_config` — an absolute OpenSSH config file plus alias;
- `connection_file` — the existing one-line `ssh user@host -p PORT -i KEY` format;
- `key_file` — an absolute private-key path, with non-secret endpoint fields supplied by the controller.

`auto` is accepted only by the probe operation. A stored source records the resolved explicit type.

The first release accepts an exact file path, not an unbounded directory crawl. The file may live anywhere the Soma service account can read, subject to secret-file hygiene checks.

### Reference-based host binding

A host profile references source fields rather than storing resolved values:

```yaml
ssh:
  hosts:
    production_vps:
      credential_binding:
        source_id: production_vps_source
        hostname: PRODUCTION_SSH_HOST
        user: PRODUCTION_SSH_USER
        port: PRODUCTION_SSH_PORT
        identity_file: PRODUCTION_SSH_KEY_PATH
        expected_host_key: PRODUCTION_SSH_HOST_KEY
      connect_timeout_seconds: 20
      use_sudo: true
```

The canonical field names inside `credential_binding` are independent of the source format. For an OpenSSH alias or connection file, the resolver produces the same canonical endpoint structure internally.

Literal and alias-based host profiles remain supported during migration. A host must use exactly one canonical connection mode after resolution.

### Project-to-host bindings

Move project deployment identity out of individual host profiles into a separate canonical mapping:

```yaml
ssh:
  project_bindings:
    project_x_production:
      repo_name: project_x
      host_id: production_vps
      remote_root: /srv/project-x
      compose_file: docker-compose.yml
      health_command_id: api_health
      required_capabilities:
        - systemd
        - docker
        - docker_compose
        - git
```

The existing nested `deployment_profiles` format remains readable through a compatibility resolver until all configured profiles are migrated. The migration must preserve deployment IDs, remote paths, shared files, health commands, and durable history.

## Credential-source probe

Add a read-only `ssh_query` operation named `credential_probe`.

Inputs:

- `source_path` or `source_id`;
- `source_type`, defaulting to `auto` for an unregistered path;
- optional `host_hint` or variable-prefix hint;
- optional field-name overrides supplied by the controller;
- compact/full view and response budget.

The probe returns only:

- resolved source type;
- source identity and protected hash metadata;
- file type, size, modification identity, and security posture;
- discovered variable names, aliases, or canonical field availability;
- deterministic field mapping candidates;
- missing or ambiguous canonical fields;
- whether the referenced key file exists and passes local hygiene checks;
- a derived public-key fingerprint where available;
- warnings and refusal reasons.

It must never return:

- variable values;
- private-key bytes;
- passphrases;
- environment dumps;
- complete OpenSSH config text;
- resolved secret values in errors.

The probe may create an opaque source-probe manifest under `runs/ssh_credential_sources/`. Public results contain a probe ID and sanitized metadata only.

## Local credential hygiene

Every source and key path must be checked before use:

- absolute path where a path is required;
- regular file, not a directory, device, symlink, or junction;
- bounded size and UTF-8 text for text sources;
- no NUL or multiline dotenv values;
- valid variable names and duplicate-key handling;
- private-key file exists and is not inside `.git`;
- source or key inside a Git repository is refused when tracked or not Git-ignored;
- Windows ACL inspection refuses clearly broad write access and reports broad read access conservatively;
- the resolved key is validated through `ssh-keygen` without returning key material;
- the source file and key identity are rebound at apply time so source changes require a new preview.

Only source references, field names, file identities, and public fingerprints may enter configuration, preview manifests, public results, events, and logs.

## Host-key lifecycle

Use a Soma-managed known-hosts file under ignored durable state rather than editing the user's global file implicitly:

```text
runs/ssh_known_hosts/known_hosts
```

Candidate validation must:

1. resolve all candidate endpoints;
2. scan the host key with bounded retries;
3. calculate canonical SHA-256 fingerprints;
4. compare an expected fingerprint when supplied;
5. compare the existing pinned identity for an active host;
6. stage a candidate known-hosts update without changing the active store;
7. use `StrictHostKeyChecking=yes` and the staged explicit known-hosts file for authentication.

Trust policies:

- `pinned` — an expected fingerprint is required and must match;
- `tofu` — allowed only for an explicit new-host onboarding intent, records the repeatedly observed first-use fingerprint;
- `rotation` — allowed only for explicit host migration or host-key rotation intent and preserves the previous fingerprint for rollback.

An unexpected host-key change during ordinary execution always fails closed.

## Capability discovery

Convert current probes into a versioned durable capability snapshot containing at least:

- operating system, distribution, version, kernel, and architecture;
- shell and command execution behaviour;
- root identity, sudo availability, and passwordless sudo result;
- package manager;
- systemd, Docker, Docker Compose, Supervisor, Kubernetes client, and Nginx availability;
- Git, Python, Node, npm, curl, hashing tools, tar, scp, and optional rsync availability;
- filesystem type, mount points, free disk, memory, swap, CPU, and optional GPU facts;
- process-group and cancellation primitives;
- timezone and locale;
- detected network route and endpoint used;
- probe timestamp, schema version, source host-key fingerprint, and snapshot hash.

Snapshots live under:

```text
runs/ssh_capabilities/<host_id>/<snapshot_id>.json
```

The public capability projection contains only bounded facts and the snapshot identity. The complete protected snapshot remains explicitly retrievable.

## Candidate project validation

Before a project binding activates, validate it read-only against the candidate host:

- repository and release roots;
- required parent directories and ownership;
- configured service manager and service names;
- Docker/Compose files and project name when configured;
- shared environment-file locations without reading their contents;
- health command or URL definitions;
- required executable and capability set;
- expected writable and read-only paths;
- rollback target or current-release link when configured.

A missing project path may be reported as `preparation_required` when the binding explicitly allows first deployment. It must not be silently treated as healthy.

## Durable activation transaction

Network validation and activation must move out of the current synchronous config-only callback into a durable worker.

The state machine is:

```text
PREVIEWED
  -> SOURCE_RESOLVED
  -> LOCAL_CREDENTIAL_VALIDATED
  -> HOST_KEY_VERIFIED
  -> AUTHENTICATION_VERIFIED
  -> CAPABILITIES_DISCOVERED
  -> PROJECT_BINDINGS_VALIDATED
  -> ACTIVATION_STAGED
  -> CONFIG_ACTIVATED
  -> POST_ACTIVATION_VERIFIED
  -> COMPLETED
```

Failure after any step enters:

```text
ROLLBACK_PENDING
  -> ROLLED_BACK
```

or, when restoration cannot be proven:

```text
RECOVERY_REQUIRED
```

The transaction must preserve and restore as one unit:

- `config.yaml`;
- credential-source and host-reference mappings;
- project bindings;
- managed known-hosts content;
- active capability-snapshot pointer;
- runtime configuration identity.

The worker must hold the existing `__soma_config__` operation lock, persist intent before any mutation, use compare-and-set state transitions, support idempotent replay, and reconcile safely after a Soma restart.

No active host profile or binding changes until all candidate read-only checks pass.

## Public gateway changes

Keep the existing three SSH gateways.

### `ssh_query`

Add or extend:

- `credential_probe`;
- `capabilities` with credential-source and binding summaries;
- `profile_preview` with source registration, credential binding, trust policy, and project-binding mutations;
- `profile_status` with the full activation state machine and evidence references;
- optional `capability_snapshot_get` for explicit protected snapshot retrieval.

### `ssh_action`

Change `profile_apply` to start the durable activation transaction and return a `run_id` plus `change_id`.

Existing command, monitored-command, reviewed-script, root-shell, administration, transfer, and deployment actions remain unchanged.

### Compatibility

Legacy profile previews without credential references continue to work. Their activation uses the same candidate validation transaction when connection testing is possible.

## Agent-driven orchestration

No separate autonomous model or coding-agent process is introduced.

The connected ChatGPT controller performs this deterministic sequence:

1. call `credential_probe` on the path named by the owner;
2. select or provide field mapping from sanitized metadata;
3. preview source, host, trust-policy, and optional project-binding changes;
4. inspect the bounded capability diff and planned validation steps;
5. call `profile_apply`;
6. poll the durable run and profile status;
7. retrieve explicit evidence only when needed;
8. report success or automatic rollback.

The controller must not ask the owner to paste credentials or manually duplicate values that Soma can resolve locally.

## Implementation sequence

### SSH-A1.0 — Contract freeze and fixtures

- freeze canonical source, binding, fingerprint, capability-snapshot, and activation-state schemas;
- capture current alias, explicit endpoint, connection-file, project deployment, and profile-lifecycle fixtures;
- add secret-leak sentinel fixtures containing unique canary values;
- document compatibility and migration invariants.

### SSH-A1.1 — Generic local credential-source resolver

- add a shared bounded dotenv parser instead of duplicating Cloudflare's private helper;
- implement source adapters and auto-detection;
- implement local file, Git, key, and ACL hygiene checks;
- add protected source-probe manifests and sanitized projections.

### SSH-A1.2 — Reference-based SSH configuration

- add credential-source and credential-binding models;
- resolve canonical endpoints only at execution time;
- keep literal, alias, and connection-file compatibility;
- ensure configuration serialization stores references only.

### SSH-A1.3 — Managed host identity

- add staged known-hosts storage;
- implement pinned, TOFU, and explicit-rotation policies;
- force every candidate and active connection through the explicit managed host-key file;
- add host-key mismatch and rollback evidence.

### SSH-A1.4 — Durable capability discovery

- extend structured probes;
- persist versioned capability snapshots;
- add required-capability evaluation;
- expose compact and explicit full evidence views.

### SSH-A1.5 — Canonical project bindings

- add top-level project-to-host bindings;
- migrate nested deployment profiles through a compatibility adapter;
- add read-only candidate path, service, environment-file, and health-check validation;
- preserve deployment IDs and durable history.

### SSH-A1.6 — Transactional activation worker

- persist activation intent and ownership;
- run source, key, fingerprint, authentication, capability, and project checks;
- stage and atomically activate all local state;
- perform post-activation verification;
- roll back every changed resource on failure;
- reconcile crash windows and idempotent retries.

### SSH-A1.7 — Public agent workflow

- extend strict gateway models and discovery;
- make `profile_apply` durable;
- add compact projections and evidence links;
- update README, capability docs, examples, and operator guidance;
- add a natural-language controller runbook using only a source path and host/project intent.

### SSH-A1.8 — Acceptance and rollout

- run focused unit, security, gateway, durability, and Windows integration suites;
- run the full Soma suite, Ruff, `pip check`, and `git diff --check`;
- verify a free local fake-SSH acceptance harness;
- opportunistically run one read-only acceptance against an already-authorized real host without changing remote state;
- restart Soma once after source/schema completion;
- verify live MCP schemas and one complete source-to-activation or source-to-rollback cycle.

## Required tests

### Credential and leakage tests

- valid and invalid dotenv syntax;
- quoted values, duplicate keys, BOM, size limits, and control characters;
- process-environment, OpenSSH config, connection-file, and key-file adapters;
- tracked, unignored, symlinked, missing, oversized, and broadly writable source files;
- missing and malformed key files;
- canary secrets absent from public responses, config, manifests, logs, events, errors, run input, run output, results, diffs, and commits.

### Host identity and authentication tests

- pinned fingerprint match and mismatch;
- deterministic TOFU onboarding;
- ordinary host-key change refusal;
- explicit rotation with rollback;
- missing key, wrong key, timeout, DNS failure, and unreachable port;
- authentication succeeds only through the staged managed known-hosts file.

### Capability and binding tests

- Linux distributions and architectures;
- root, sudo, no-sudo, systemd, Docker, Compose, Nginx, Python, Git, Node, and missing-tool combinations;
- project path exists, first-deployment path missing, wrong ownership, missing health command, and missing required capability;
- nested deployment compatibility and canonical migration.

### Durability tests

- crash after source resolution;
- crash after host-key staging;
- crash after authentication;
- crash after config swap but before reload;
- crash after reload but before post-check;
- concurrent activation attempts;
- source file changes after preview;
- cancellation before and after local mutation;
- idempotent apply replay;
- failed rollback enters `RECOVERY_REQUIRED` rather than claiming success.

## Security invariants

- Raw secret values never cross the MCP boundary.
- Raw private-key material is never accepted as input or stored by Soma.
- Password and keyboard-interactive SSH remain disabled.
- Source values are resolved only inside the local candidate worker.
- Durable records contain source references and protected identity evidence, not resolved values.
- Active host-key identity is explicit and pinned.
- Existing host-key changes fail closed outside an explicit migration or rotation transaction.
- No active profile or project binding changes before candidate validation passes.
- Rollback includes config, host-key state, capability pointer, project binding, and runtime identity.
- Existing repository, run, and resource-lock systems are reused; no parallel lock authority is introduced.

## Exit gates

SSH-A1 completes only when all of the following are true:

1. The owner can point the controller at one supported local credential source without editing configuration manually.
2. The controller can discover and bind fields without receiving secret values.
3. Host authentication and host-key validation happen before activation.
4. A versioned capability snapshot is persisted and required capabilities are evaluated.
5. Project-to-host bindings are canonical, independently replaceable, and validated read-only.
6. `profile_apply` is durable, restart-recoverable, idempotent, and transactionally rolls back every local change.
7. Canary-secret scanning proves no leakage across public or durable surfaces.
8. Existing SSH hosts and deployments remain compatible.
9. The live MCP connector advertises the new strict operations and schemas.
10. One complete agent-driven acceptance requires only a credential location plus host/project intent from the owner.

Until these gates pass, the current SSH profile manager remains the active production path and no existing host is automatically migrated.
