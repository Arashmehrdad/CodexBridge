# REPO-DOCUMENT-EDITING-1 History Hygiene Result

**Date:** 2026-07-31  
**Status:** accepted and closed  
**Branch:** `lane/memory-integration-foundation-1`  
**Push:** none

## Purpose

Close the remaining history-hygiene defect in managed repository editing. Preview and patch correctness were already accepted, but every successful apply and revert still created an immediate commit, making disposable inspection produce content-neutral history.

## Accepted design

Automatic commit remains the compatibility default. Callers that need an inspect/test/decide workflow may opt into explicit manual commit mode.

```text
preview
  -> repo_apply(commit_mode="manual")
  -> inspect and test the worktree
  -> repo_commit(commit_selected)
```

A disposable operation may instead be reversed without creating any commit:

```text
preview
  -> repo_apply(commit_mode="manual")
  -> inspect and test
  -> repo_apply(operation="revert", commit_mode="manual")
  -> clean worktree, unchanged HEAD
```

## Public contract

The following `repo_apply` operations accept:

```text
commit_mode: "auto" | "manual"
```

- `previewed_change`
- `revert`
- `cleanup`
- `move_file`

`auto` remains the default so existing callers preserve their current behavior.

In `manual` mode Soma:

- applies the already reviewed, hash-bound operation;
- does not invoke the Git commit path;
- releases the durable run and repository lease normally;
- reports `commit_required`;
- reports `commit_attempted: false`;
- reports the exact `pending_commit_files` still dirty after the operation;
- leaves final commit selection to `repo_commit.commit_selected`.

If a manual revert restores the original tracked state, Soma reports no pending files and no commit requirement.

## Commit metadata

Create and remove previews now accept validated:

- `commit_title`
- `commit_description`

The metadata is bound into the preview manifest together with its `Preview-ID` and is used if the caller later applies in automatic mode.

Revert, cleanup, and move apply requests also accept commit title and description for automatic mode, avoiding generic `Soma: repo_apply` messages when the caller wants an immediate commit.

## Safety retained

The change does not weaken:

- preview-before-write;
- exact file hashes;
- base-HEAD validation;
- opaque payload storage;
- atomic file replacement;
- rollback evidence;
- idempotent durable apply records;
- repository lease containment;
- selected-file commit isolation;
- unrelated dirty-work preservation;
- no-push policy.

Manual mode changes only the final commit decision. It does not bypass mutation validation.

## Validation

Initial focused run:

```text
448 passed, 2 failed
```

Both failures were test-fixture defects: one invalid synthetic run identifier and one assumption that discovery serializes model defaults explicitly. Neither failure exercised a broken implementation path. The fixtures were corrected and rerun.

Final focused suite:

```text
450 passed in 190.70s
```

Covered repository writer, durable worker, server routing, gateway models, MCP discovery, flat input, commit deferral, metadata binding, and the real Git transaction proof.

Adjacent compatibility suite:

```text
75 passed, 26 skipped in 4.46s
```

Covered gateway inventory, benchmark shape, public result materialization, transport content gates, and payload chunks.

## Decisive real-Git proof

The transaction test created a disposable Git repository, recorded its initial HEAD, previewed and manually applied a UTF-8 file containing Persian text and symbols, then manually reverted the same managed patch.

Acceptance evidence:

- manual apply reported the created file as pending commit;
- no commit occurred during apply;
- manual revert reported no pending commit;
- final `git status --porcelain` was empty;
- final HEAD exactly equaled the initial HEAD;
- the disposable file no longer existed.

This closes the content-neutral commit-confetti defect for callers that choose manual mode.

## Commits

- `f4d0442f90b0f84ddd6da0f83ac45a7d7161d0a7` — Activate repository history hygiene correction
- `a9ce6a63876c4a0d369a2188b8866614c3b4551f` — Add manual repository commit mode
- `39c258f7b0ad49898015d9b218d850a8f6037fd4` — Cover manual repository transaction mode
- `108c09a73a46a089ece6db00f33c1be7b06c807e` — Correct manual transaction test fixtures

## Remaining non-goals

This batch does not implement:

- automatic scratch branches;
- long-lived multi-preview transactions;
- automatic rollback after inspection timeout;
- Markdown heading-aware editing;
- typed discriminated edit-operation schemas;
- history rewriting or cleanup of previously created probe commits.

A manual apply intentionally leaves reviewed changes in the worktree. The caller must either commit the exact selected files or issue a validated manual revert.

## Disposition

`REPO-DOCUMENT-EDITING-1` is accepted and closed. Active plan truth returns to the documentation-only `V3-1A-INTERACTION-FOUNDATION-ARCH-REVIEW-1`; V3-1A product implementation remains paused.
