# REPO-DOCUMENT-EDITING-1 Result

**Date:** 2026-07-31  
**Status:** first corrective batch accepted and closed  
**Branch:** `lane/memory-integration-foundation-1`  
**Push:** none

## Purpose

Close two proven correctness defects and add the smallest safe primitive needed for coherent documentation rewrites without reopening V3-1A implementation.

## Proven defects

1. `scripts/browser_pulse_sender.py` did not recognise `needs_external_coder` or `approval_required`. A supervisor parked in either state was rejected as “not a handoff state,” so the polling loop could continue indefinitely even though no work remained active.
2. Repository `line_range` / `replace_lines` edits accepted unanchored coordinates, did not reject ranges beyond the file, and could be composed after earlier same-file edits that shifted their target.
3. Existing text files had no direct hash-bound whole-file replacement primitive, forcing large document changes through brittle exact-text or line-number patches.

## Implemented correction

### Browser pulse handoff states

`HANDOFF_STATUSES` now includes:

- `needs_external_coder`
- `approval_required`
- `needs_input`
- `blocked`
- `completed`
- `failed`
- `cancelled`

Parked handoff states now produce a prompt/dry-run result and let the poller exit instead of retrying forever.

### Fail-closed line-range edits

Every `line_range` / `replace_lines` operation now:

- requires `expected_old_text` or `expected_range_sha256`;
- rejects invalid or out-of-bounds ranges with the actual file line count;
- validates the selected source range before replacement;
- remains exclusive for its file within one patch, so another same-file edit cannot shift its coordinates;
- preserves the existing newline behaviour where requested.

This is intentionally conservative. Stable multi-range composition remains a later design problem rather than being guessed from mutable coordinates.

### Whole-file replacement

Existing text files may now use operation type `replace_file` (alias `whole_file`) with:

- `path`
- `expected_sha256`
- `new_text`
- optional `newline_policy`

Supported newline policies:

- `preserve_current` — default; use the existing file’s dominant newline style;
- `lf`;
- `crlf`;
- `exact` — retain the supplied text bytes after UTF-8 encoding.

A whole-file replacement must be the only operation for that file in its patch. It retains the existing preview, stale-hash, base-HEAD, opaque-payload, atomic-write, rollback, and isolated-commit protections.

## Validation

Focused suite:

```text
python -m pytest tests/test_browser_pulse_sender.py tests/test_repo_writer.py -q
109 passed in 34.58s
```

Adjacent server and payload contract suite:

```text
python -m pytest tests/test_server.py tests/test_payload_chunks.py tests/test_mcp_action_discovery.py -q
77 passed in 4.44s
```

The first focused run exposed one historical `replace_lines` test still using the unsafe unanchored request shape. That compatibility test was updated to the new anchored contract and the complete focused suite then passed.

## Commits

- `999f8daa647bb9038a93dfea4c38a3e2c25d64e8` — Activate repository document editing correction
- `ebb8ce561fec2c40524d435a61d0f9c2754f1423` — Fix handoff polling and document edits
- `a7c1d33f2a21c948eb465bdb423a288241aee264` — Update anchored line range contract test

## Remaining work

This first batch deliberately does not implement:

- Markdown heading/section-aware edits;
- typed discriminated public edit-operation schemas;
- stable multi-operation source-coordinate composition;
- draft transactions spanning several preview/apply cycles;
- richer per-operation retry diagnostics.

Those are later ergonomics and architecture improvements. They are not required to accept this correctness correction.

## Disposition

The browser-pulse deadlock is closed. Unsafe unanchored line-range editing now fails closed. Coherent full-document rewrites can be performed as one hash-bound preview, one atomic apply, and one commit.

V3-1A implementation remains paused. The active roadmap may return to `V3-1A-INTERACTION-FOUNDATION-ARCH-REVIEW-1` after this result is recorded.
