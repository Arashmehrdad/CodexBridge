"""CF1 chat-footprint acceptance suite.

Exercises the production terminal projection, publication, evidence, transport,
pagination, performance, compatibility, and redaction contracts across the 19
authoritative CF1 fixtures. Every scenario runs against real `RunStore`,
`JobManager`, publication, and MCP transport code — no duplicated projection
logic and no artificial dictionary comparisons.
"""
from __future__ import annotations

import asyncio
import json
import math
import statistics
import subprocess
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns
from types import SimpleNamespace

import pytest
from fastmcp import Client
from pydantic import TypeAdapter

import soma.job_manager as job_manager_module
import soma.server as server
from soma.cf1_fixture_footprint import build_representative_fixture_payload
from soma.cf1_fixture_matrix import (
    CF1_FIXTURE_MATRIX,
    validate_fixture_matrix,
)
from soma.events import redact_and_truncate
from soma.gateway_models import RunQueryRequest
from soma.git_tools import git_diff_snapshot
from soma.job_manager import JobManager
from soma.public_footprint_measurement import measure_public_footprint
from soma.public_projection_contract import (
    DEFAULT_PUBLIC_BYTE_BUDGETS,
    NON_AUTHORITATIVE_NOTICE,
    PUBLIC_PROJECTION_SCHEMA_VERSION,
)
from soma.repo_reader import read_repo_files, search_repo_text
from soma.run_public_result import (
    PUBLIC_RESULT_SCHEMA_VERSION,
    PUBLIC_RESULT_STATUS_NOT_MATERIALIZED,
    PUBLIC_RESULT_STATUS_READY,
    authoritative_result_sha256,
    build_public_result_projection,
    canonical_public_json_bytes,
)
from soma.run_publication import publish_run_result
from soma.run_store import RunStore, utc_now


FIXTURE_NAMES = tuple(fixture.name for fixture in CF1_FIXTURE_MATRIX)
DETAIL_BYTES = 4096
# Transport capability tags added by the gateway wrapper on top of every dict
# response; they are metadata, never authoritative result content.
CAPABILITY_KEYS = frozenset(
    {"server_build_hash", "schema_hash", "capability_epoch"}
)
# Durable terminal status per fixture outcome. `active_run` never transitions.
_DB_STATUS = {
    "success": "completed",
    "execution_failure": "failed",
    "cancelled": "cancelled",
    "partial": "partial",
    "ambiguous_side_effect": "failed",
    "needs_input": "needs_input",
}
# Normalized outcome the production projector must report for each fixture
# outcome, derived from the durable status plus stored classification.
_EXPECTED_OUTCOME = {
    "success": "success",
    "execution_failure": "unknown_failure",
    "cancelled": "cancellation_verified",
    "partial": "partial",
    "ambiguous_side_effect": "ambiguous_side_effect",
    "needs_input": "needs_input",
}


def _wire_bytes(payload: object) -> int:
    return len(canonical_public_json_bytes(payload))


def _manager(store: RunStore, lock: dict | None = None) -> JobManager:
    manager = object.__new__(JobManager)
    manager.store = store
    manager.config = None
    manager.locks = SimpleNamespace(
        find_lock=lambda _repo_name, _run_id: dict(lock or {})
    )
    return manager


def _raw_result_json(store: RunStore, run_id: str) -> str:
    with store.connect() as conn:
        row = conn.execute(
            "SELECT result_json FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    assert row is not None
    return str(row["result_json"])


def _nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _run_query(payload: dict) -> dict:
    return server.run_query(TypeAdapter(RunQueryRequest).validate_python(payload))


def _gateway_full_result(run_id: str) -> dict:
    """Reassemble the complete authoritative result from the gateway route.

    The production `run_query` result route returns either an inline payload
    (small results) or a hash-bound chunked-JSON evidence stream.
    """
    response = _run_query({"operation": "result", "run_id": run_id, "view": "full"})
    if response.get("transport") == "chunked_json":
        serialized = response["chunk"]
        while not response["complete"]:
            response = _run_query(
                {
                    "operation": "result",
                    "run_id": run_id,
                    "view": "full",
                    "cursor": response["next_cursor"],
                }
            )
            assert response.get("transport") == "chunked_json"
            serialized += response["chunk"]
        assert (
            sha256(serialized.encode("ascii")).hexdigest()
            == response["payload_sha256"]
        )
        return json.loads(serialized)
    return {
        key: value
        for key, value in response.items()
        if key not in CAPABILITY_KEYS and key != "_transport"
    }


async def _mcp_terminal_responses(run_ids: dict[str, str]) -> dict[str, object]:
    responses: dict[str, object] = {}
    async with Client(server.mcp) as client:
        for name, run_id in run_ids.items():
            responses[name] = await client.call_tool(
                "run_query", {"request": {"operation": "terminal", "run_id": run_id}}
            )
    return responses


@pytest.fixture(scope="module")
def matrix_session(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    """Durable 19-fixture session built through real store transitions."""
    runs_dir = tmp_path_factory.mktemp("cf1-acceptance") / "runs"
    store = RunStore(runs_dir)
    runs: dict[str, dict] = {}
    for index, fixture in enumerate(CF1_FIXTURE_MATRIX):
        run_id = f"20260722T05{index:04d}Z_{fixture.tool}_{index:08x}"
        run_dir = runs_dir / run_id
        run_dir.mkdir(parents=True)
        status = "running" if fixture.name == "active_run" else "queued"
        store.create_run(
            run_id=run_id,
            repo_name="Soma",
            tool=fixture.tool,
            run_dir=run_dir,
            input_data={"fixture": fixture.name},
            status=status,
        )
        record: dict = {"run_id": run_id, "fixture": fixture, "result": None}
        if fixture.name != "active_run":
            payload = build_representative_fixture_payload(
                fixture, detail_bytes=DETAIL_BYTES
            )
            base = payload.authoritative_record["result_json"]
            result = {
                "status": _DB_STATUS[fixture.outcome],
                "classification": fixture.outcome,
                "summary": str(base["summary"]),
                "detail": str(base["detail"]),
                "evidence": json.loads(json.dumps(base["evidence"])),
                "process_success": True if fixture.outcome == "success" else None,
            }
            current = store.get_run(run_id)
            transitioned = store.transition_terminal(
                run_id,
                status=_DB_STATUS[fixture.outcome],
                result=result,
                expected_statuses=("queued",),
                expected_state_version=current["state_version"],
                ended_at=utc_now(),
                summary=result["summary"],
                error="",
                safety_failure=False,
            )
            assert transitioned is not None
            published = publish_run_result(store, run_id)
            assert published["ok"] is True
            record["result"] = result
        runs[fixture.name] = record
    return SimpleNamespace(store=store, runs=runs)


@pytest.fixture(scope="module")
def twenty_run_session(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    """Twenty realistic durable runs mirroring the ~837 KB measurement fixture.

    Detail strings stay below the 20,000-character full-retrieval truncation
    boundary so the complete authoritative content remains byte-exact through
    the production full route while the total scale matches the fixture.
    """
    runs_dir = tmp_path_factory.mktemp("cf1-twenty") / "runs"
    store = RunStore(runs_dir)
    detail_first = "x" * 10_425
    detail_second = "x" * 10_425
    run_ids: list[str] = []
    for index in range(20):
        run_id = f"20260722T06{index:04d}Z_project_command_{index:08x}"
        run_dir = runs_dir / run_id
        run_dir.mkdir(parents=True)
        store.create_run(
            run_id=run_id,
            repo_name="Soma",
            tool="project_command",
            run_dir=run_dir,
            input_data={"detail_first": detail_first, "detail_second": detail_second},
        )
        result = {
            "status": "completed",
            "classification": "success",
            "summary": (
                f"Durable acceptance run {index:02d} finished its validation "
                "sweep with bounded artifacts and recoverable evidence "
                + "s" * 200
            ),
            "detail_first": detail_first,
            "detail_second": detail_second,
        }
        current = store.get_run(run_id)
        transitioned = store.transition_terminal(
            run_id,
            status="completed",
            result=result,
            expected_statuses=("queued",),
            expected_state_version=current["state_version"],
            ended_at=utc_now(),
            summary=result["summary"],
            error="",
            safety_failure=False,
        )
        assert transitioned is not None
        run_ids.append(run_id)
    return SimpleNamespace(store=store, run_ids=run_ids)


def test_acceptance_matrix_covers_all_nineteen_fixtures_exactly_once() -> None:
    validate_fixture_matrix()
    assert len(CF1_FIXTURE_MATRIX) == 19
    assert len(set(FIXTURE_NAMES)) == 19
    for fixture in CF1_FIXTURE_MATRIX:
        canonical = json.dumps(
            fixture.canonical_payload(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        assert fixture.identity_sha256 == sha256(canonical).hexdigest()
    assert len({fixture.identity_sha256 for fixture in CF1_FIXTURE_MATRIX}) == 19
    # Every outcome the matrix declares has a seeded durable mapping and an
    # expected normalized outcome; nothing can be silently skipped.
    terminal_outcomes = {
        fixture.outcome
        for fixture in CF1_FIXTURE_MATRIX
        if fixture.name != "active_run"
    }
    assert terminal_outcomes == set(_DB_STATUS) == set(_EXPECTED_OUTCOME)


def test_lifecycle_and_outcome_distinctions_stay_distinguishable() -> None:
    compact_identity: dict[tuple[str, str], tuple[str, str, str]] = {}
    for fixture in CF1_FIXTURE_MATRIX:
        source = (fixture.lifecycle_status, fixture.outcome)
        if fixture.name == "active_run":
            compact = ("running", "", "pending")
        else:
            compact = (
                _DB_STATUS[fixture.outcome],
                fixture.outcome,
                _EXPECTED_OUTCOME[fixture.outcome],
            )
        existing = compact_identity.setdefault(source, compact)
        assert existing == compact
    distinct_sources = set(compact_identity)
    distinct_compacts = set(compact_identity.values())
    assert len(distinct_compacts) == len(distinct_sources)


@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_production_projection_and_exact_evidence_recovery(
    fixture_name: str,
    matrix_session: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = matrix_session.runs[fixture_name]
    fixture = record["fixture"]
    run_id = record["run_id"]
    manager = _manager(matrix_session.store)
    monkeypatch.setattr(server, "get_job_manager", lambda: manager)

    compact = _run_query({"operation": "terminal", "run_id": run_id})
    assert compact["run_id"] == run_id
    assert compact["tool"] == fixture.tool
    assert compact["view"] == "summary"
    assert compact["projection_version"] == PUBLIC_PROJECTION_SCHEMA_VERSION
    assert compact["public_result_schema_version"] == PUBLIC_RESULT_SCHEMA_VERSION
    assert compact["non_authoritative"] is True
    assert compact["notice"] == NON_AUTHORITATIVE_NOTICE
    assert _wire_bytes(compact) <= DEFAULT_PUBLIC_BYTE_BUDGETS.terminal_result

    if fixture_name == "active_run":
        # Pending path: no terminal result may be invented; evidence points to
        # the authoritative control route.
        assert compact["projection_status"] == "pending"
        assert compact["result_available"] is False
        assert compact["result"]["status"] == "running"
        assert compact["result"]["outcome"] == "pending"
        assert compact["evidence"]["authoritative_operation"] == "control"
        assert compact["evidence"]["run_id"] == run_id
        return

    raw = _raw_result_json(matrix_session.store, run_id)
    stored = json.loads(raw)
    assert compact["projection_status"] == PUBLIC_RESULT_STATUS_READY
    assert compact["source_result_sha256"] == authoritative_result_sha256(raw)
    assert compact["evidence"]["authoritative_operation"] == "result"
    assert compact["evidence"]["source_result_sha256"] == compact[
        "source_result_sha256"
    ]
    assert (
        compact["result"]["status"],
        compact["result"]["classification"],
        compact["result"]["outcome"],
    ) == (
        _DB_STATUS[fixture.outcome],
        fixture.outcome,
        _EXPECTED_OUTCOME[fixture.outcome],
    )

    # Exact authoritative recovery through the production full route.
    direct_full = manager.get_result(run_id)
    assert direct_full == stored
    assert canonical_public_json_bytes(direct_full) == canonical_public_json_bytes(
        stored
    )
    gateway_full = _gateway_full_result(run_id)
    assert gateway_full == stored

    # Every declared evidence kind stays content-bound and recoverable.
    for kind in fixture.evidence_kinds:
        entry = direct_full["evidence"][kind]
        assert entry["detail"]
        assert entry["sha256"] == sha256(
            f"{fixture.name}:{kind}:{entry['detail']}".encode("utf-8")
        ).hexdigest()


def test_evidence_recovery_is_one_hundred_percent_across_matrix(
    matrix_session: SimpleNamespace,
) -> None:
    manager = _manager(matrix_session.store)
    total = 0
    recovered = 0
    for record in matrix_session.runs.values():
        if record["result"] is None:
            continue
        fixture = record["fixture"]
        raw = _raw_result_json(matrix_session.store, record["run_id"])
        stored = json.loads(raw)
        full = manager.get_result(record["run_id"])
        exact = canonical_public_json_bytes(full) == canonical_public_json_bytes(
            stored
        )
        for kind in fixture.evidence_kinds:
            total += 1
            entry = full.get("evidence", {}).get(kind) or {}
            bound = entry.get("sha256") == sha256(
                f"{fixture.name}:{kind}:{entry.get('detail', '')}".encode("utf-8")
            ).hexdigest()
            if exact and bound:
                recovered += 1
    assert total > 0
    assert recovered == total  # 100% evidence recovery
    print(
        "CF1-ACCEPTANCE-EVIDENCE "
        + json.dumps({"evidence_total": total, "evidence_recovered": recovered})
    )


def test_run_route_responses_respect_serialized_byte_budgets(
    matrix_session: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = matrix_session.store
    manager = _manager(store)
    budgets = DEFAULT_PUBLIC_BYTE_BUDGETS
    for record in matrix_session.runs.values():
        terminal = manager.get_terminal_result(record["run_id"])
        assert _wire_bytes(terminal) <= budgets.terminal_result
        summary = manager.get_run_summary(record["run_id"])
        assert _wire_bytes(summary) <= budgets.run_summary
        assert _wire_bytes(terminal) <= budgets.unsolicited_response
        assert _wire_bytes(summary) <= budgets.unsolicited_response

    active_run_id = matrix_session.runs["active_run"]["run_id"]
    monkeypatch.setattr(job_manager_module, "process_is_running", lambda _pid: False)
    monkeypatch.setattr(
        job_manager_module, "process_matches_identity", lambda _pid, _identity: False
    )
    control = manager.get_control_status(active_run_id)
    assert control["ok"] is True
    assert _wire_bytes(control) <= budgets.run_control
    unchanged = manager.get_control_status(
        active_run_id, if_state_version=control["state_version"]
    )
    assert unchanged["unchanged"] is True
    assert _wire_bytes(unchanged) <= budgets.unchanged_poll

    events_run_id = matrix_session.runs["successful_run"]["run_id"]
    for index in range(30):
        store.append_event(
            events_run_id,
            level="info",
            stage="execute",
            message=f"acceptance event {index} " + "m" * 1200,
            data={"blob": "b" * 1500},
            update_run_metadata=False,
        )
    # after_id=0 anchors at the beginning; the default page anchors at the
    # most recent events. Both stay byte-bounded; the anchored walk proves
    # lossless coverage of every appended event.
    page = manager.get_event_page(events_run_id, after_id=0)
    seen: list[int] = [event["id"] for event in page["events"]]
    assert _wire_bytes(page) <= budgets.events
    while page["has_more"]:
        page = manager.get_event_page(events_run_id, cursor=page["next_cursor"])
        assert _wire_bytes(page) <= budgets.events
        seen.extend(event["id"] for event in page["events"])
    assert len(seen) == 30
    assert len(set(seen)) == 30
    assert seen == sorted(seen)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True
    )


def test_repository_route_responses_respect_serialized_byte_budgets(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "acceptance@example.com")
    _git(repo, "config", "user.name", "Acceptance User")
    # Stay under the 500 KB per-file search ceiling while providing far more
    # matches than the 16 KB search budget can carry.
    lines = [f"line {index:05d} " + "content " * 40 for index in range(1200)]
    big = repo / "big.txt"
    big.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    _git(repo, "add", "big.txt")
    _git(repo, "commit", "-m", "acceptance baseline")

    budgets = DEFAULT_PUBLIC_BYTE_BUDGETS
    search = search_repo_text(
        repo,
        "content",
        max_results=500,
        response_budget_bytes=budgets.repository_search,
    )
    assert search["hits"]
    assert _wire_bytes(search) <= budgets.repository_search

    batch = read_repo_files(repo, [{"path": "big.txt"}])
    assert batch["results"][0]["content"]
    assert _wire_bytes(batch) <= budgets.repository_read_batch

    big.write_text(
        "\n".join(f"changed {line}" for line in lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    diff = git_diff_snapshot(repo, view="summary")
    assert diff["ok"] is True
    assert _wire_bytes(diff) <= budgets.repository_diff

    for response in (search, batch, diff):
        assert _wire_bytes(response) <= budgets.unsolicited_response


def _paginate_twenty_run_summaries(store: RunStore) -> list[dict]:
    manager = _manager(store)
    pages: list[dict] = []
    cursor: str | None = None
    while True:
        page = manager.list_run_summaries(limit=20, cursor=cursor)
        pages.append(page)
        if not page["has_more"]:
            break
        cursor = page["next_cursor"]
        assert cursor
    return pages


def test_twenty_run_summary_pagination_is_lossless_and_bounded(
    twenty_run_session: SimpleNamespace,
) -> None:
    pages = _paginate_twenty_run_summaries(twenty_run_session.store)
    seen: list[str] = []
    for page in pages:
        assert page["ok"] is True
        assert page["requested_limit"] == 20
        assert page["returned_count"] == len(page["runs"])
        assert _wire_bytes(page) <= DEFAULT_PUBLIC_BYTE_BUDGETS.run_list
        assert page["byte_limited"] is (
            page["returned_count"] < 20 - len(seen)
        )
        seen.extend(run["run_id"] for run in page["runs"])
    # Accepted contract: requesting 20 summaries is supported; when the 12 KB
    # run-list budget cannot hold every projected summary, the response is
    # byte-limited and the remainder stays recoverable through the stable
    # cursor without loss or duplication (not by forcing all 20 into one page).
    assert set(seen) == set(twenty_run_session.run_ids)
    assert len(seen) == 20
    assert len(set(seen)) == 20
    # The seeded summaries exceed one page deterministically: each projected
    # item carries a 256-byte bounded summary plus scalar columns, so twenty
    # items cannot serialize under 12 KB in a single page.
    assert len(pages) >= 2
    assert pages[0]["byte_limited"] is True
    assert pages[0]["has_more"] is True
    print(
        "CF1-ACCEPTANCE-TWENTY-RUN "
        + json.dumps(
            {
                "requested_count": 20,
                "first_page_returned": pages[0]["returned_count"],
                "pages": len(pages),
                "total_returned": len(seen),
                "byte_limited_pages": sum(
                    1 for page in pages if page["byte_limited"]
                ),
                "page_bytes": [_wire_bytes(page) for page in pages],
            }
        )
    )


def test_837kb_twenty_run_payload_recovers_without_entering_conversation(
    twenty_run_session: SimpleNamespace,
) -> None:
    store = twenty_run_session.store
    manager = _manager(store)
    authoritative = []
    for run_id in twenty_run_session.run_ids:
        run = store.get_run(run_id)
        authoritative.append(
            {
                "run_id": run_id,
                "status": run["status"],
                "input": run["input"],
                "result": run["result"],
            }
        )
    authoritative_bytes = _wire_bytes(authoritative)
    assert 830_000 <= authoritative_bytes <= 845_000

    pages = _paginate_twenty_run_summaries(store)
    conversation_bytes = sum(_wire_bytes(page) for page in pages)
    assert conversation_bytes < authoritative_bytes * 0.10

    for run_id in twenty_run_session.run_ids:
        stored = json.loads(_raw_result_json(store, run_id))
        full = manager.get_result(run_id)
        assert canonical_public_json_bytes(full) == canonical_public_json_bytes(
            stored
        )
        terminal = manager.get_terminal_result(run_id)
        assert terminal["source_result_sha256"] == authoritative_result_sha256(
            _raw_result_json(store, run_id)
        )
    print(
        "CF1-ACCEPTANCE-837KB "
        + json.dumps(
            {
                "authoritative_bytes": authoritative_bytes,
                "conversation_bytes": conversation_bytes,
                "recovered_runs": len(twenty_run_session.run_ids),
            }
        )
    )


def test_conversation_footprint_reduction_is_at_least_90_percent(
    matrix_session: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(matrix_session.store)
    monkeypatch.setattr(server, "get_job_manager", lambda: manager)

    # CF1 exit gate is re-measured against the TEXT block — the channel the
    # model actually consumes (content[].text) — rather than structuredContent.
    # Pre-CF1 the model consumed the full authoritative record serialized into
    # the text block; the corrected transport serializes only the compact
    # projection into that same channel.
    baseline_text_total = 0
    for fixture in CF1_FIXTURE_MATRIX:
        payload = build_representative_fixture_payload(
            fixture, detail_bytes=DETAIL_BYTES
        )
        measurement = measure_public_footprint(
            request_arguments=payload.request_arguments,
            server_projection=payload.server_projection,
            mcp_structured_content=payload.mcp_structured_content,
            mcp_text_content=payload.mcp_text_content,
            connector_envelope=payload.connector_envelope,
            authoritative_record=payload.authoritative_record,
        )
        # Baseline text block carried the complete authoritative projection.
        assert measurement.mcp_text_content_bytes == measurement.server_projection_bytes
        baseline_text_total += measurement.mcp_text_content_bytes

    run_ids = {
        name: record["run_id"] for name, record in matrix_session.runs.items()
    }
    responses = asyncio.run(_mcp_terminal_responses(run_ids))

    current_text_total = 0
    structured_total = 0
    for name, response in responses.items():
        structured = response.structured_content
        assert structured is not None
        text = "".join(
            block.text
            for block in response.content
            if getattr(block, "type", "") == "text"
        )
        # The corrected transport MUST populate content[].text with the same
        # compact projection carried by structuredContent — non-empty, JSON
        # parseable, and semantically equivalent.
        assert text, f"{name} produced an empty text block"
        assert json.loads(text) == structured
        envelope = {
            "structuredContent": structured,
            "content": [{"type": "text", "text": text}],
        }
        stored = matrix_session.runs[name]["result"] or {}
        measurement = measure_public_footprint(
            request_arguments={"operation": "terminal", "run_id": run_ids[name]},
            server_projection=structured,
            mcp_structured_content=structured,
            mcp_text_content=text,
            connector_envelope=envelope,
            authoritative_record=stored,
        )
        assert measurement.mcp_text_content_bytes > 0
        current_text_total += measurement.mcp_text_content_bytes
        structured_total += measurement.mcp_structured_content_bytes

    reduction_bytes = baseline_text_total - current_text_total
    reduction_percent = reduction_bytes / baseline_text_total * 100
    assert reduction_percent >= 90.0
    print(
        "CF1-ACCEPTANCE-REDUCTION "
        + json.dumps(
            {
                "baseline_text_bytes": baseline_text_total,
                "current_text_bytes": current_text_total,
                "reduction_bytes": reduction_bytes,
                "reduction_percent": round(reduction_percent, 2),
                "structured_content_bytes": structured_total,
            }
        )
    )


def test_projection_overhead_and_full_retrieval_performance(
    matrix_session: SimpleNamespace,
) -> None:
    store = matrix_session.store
    record = matrix_session.runs["successful_run"]
    run_id = record["run_id"]
    snapshot = store.get_result_source_snapshot(run_id)
    source_sha256 = authoritative_result_sha256(snapshot["result_json"])
    result = record["result"]

    for _ in range(20):
        build_public_result_projection(snapshot, result, source_sha256)
    samples_ms: list[float] = []
    for _ in range(200):
        started = perf_counter_ns()
        build_public_result_projection(snapshot, result, source_sha256)
        samples_ms.append((perf_counter_ns() - started) / 1_000_000)
    projection_p50 = statistics.median(samples_ms)
    projection_p95 = _nearest_rank(samples_ms, 0.95)
    assert projection_p95 <= 2.0

    manager = _manager(store)

    def full_retrieval_current() -> None:
        manager.get_result(run_id)

    def full_retrieval_baseline() -> None:
        # Equivalent pre-CF1 direct authoritative retrieval: durable row read
        # plus the same redaction pass, without gateway routing.
        redact_and_truncate(store.get_run(run_id).get("result") or {})

    for _ in range(10):
        full_retrieval_baseline()
        full_retrieval_current()

    def timed_batch(callable_) -> float:
        started = perf_counter_ns()
        for _ in range(50):
            callable_()
        return (perf_counter_ns() - started) / 1_000_000

    baseline_batches: list[float] = []
    current_batches: list[float] = []
    for index in range(7):
        # Alternate ordering so transient CPU/load drift cannot consistently
        # penalize the current path merely because it always runs second.
        if index % 2:
            current_ms = timed_batch(full_retrieval_current)
            baseline_ms = timed_batch(full_retrieval_baseline)
        else:
            baseline_ms = timed_batch(full_retrieval_baseline)
            current_ms = timed_batch(full_retrieval_current)
        baseline_batches.append(baseline_ms)
        current_batches.append(current_ms)
    baseline_median = statistics.median(baseline_batches)
    current_median = statistics.median(current_batches)
    # Preserve the original aggregate-median contract while alternating order
    # to prevent systematic second-run scheduler bias. The 0.5 ms batch epsilon
    # remains approximately 10 microseconds per call.
    assert current_median <= baseline_median * 1.05 + 0.5
    print(
        "CF1-ACCEPTANCE-PERFORMANCE "
        + json.dumps(
            {
                "projection_p50_ms": round(projection_p50, 4),
                "projection_p95_ms": round(projection_p95, 4),
                "full_retrieval_baseline_batch_ms_p50": round(baseline_median, 3),
                "full_retrieval_current_batch_ms_p50": round(current_median, 3),
                "full_retrieval_batch_calls": 50,
            }
        )
    )


def test_compact_summary_sql_never_decodes_blobs_and_transport_serializes_payload(
    matrix_session: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = matrix_session.store
    run_id = matrix_session.runs["successful_run"]["run_id"]
    monkeypatch.setattr(
        "soma.run_store.loads",
        lambda _value: pytest.fail("compact summary path decoded a JSON blob"),
    )
    manager = _manager(store)
    assert manager.get_run_summary(run_id)["ok"] is True
    assert store.get_run_control_snapshot(run_id)["run_id"] == run_id
    assert store.list_run_summaries()["runs"]
    monkeypatch.undo()

    payload = {
        "ok": True,
        "operation": "summary_list",
        "runs": [{"run_id": f"run-{index}", "summary": "x" * 2000} for index in range(20)],
        "error": "",
    }
    transported = server._mcp_transport_result(payload)
    assert transported.structured_content == payload
    text = "".join(
        block.text
        for block in transported.content
        if getattr(block, "type", "") == "text"
    )
    # The transport serializes the same projection into content[].text so
    # non-ChatGPT clients receive the payload; both channels stay equivalent.
    assert text
    assert json.loads(text) == payload


def test_direct_dict_mcp_wrapper_and_durable_projection_reuse(
    matrix_session: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manager = _manager(matrix_session.store)
    monkeypatch.setattr(server, "get_job_manager", lambda: manager)
    run_id = matrix_session.runs["successful_run"]["run_id"]

    direct = _run_query({"operation": "terminal", "run_id": run_id})
    assert isinstance(direct, dict)
    assert direct["run_id"] == run_id

    responses = asyncio.run(_mcp_terminal_responses({"successful_run": run_id}))
    response = responses["successful_run"]
    structured = response.structured_content
    assert structured["run_id"] == run_id
    text = "".join(
        block.text
        for block in response.content
        if getattr(block, "type", "") == "text"
    )
    # content[].text carries the same projection as structuredContent, rendered
    # with the canonical compact separators.
    assert text
    assert json.loads(text) == structured
    assert (
        json.dumps(structured, ensure_ascii=False, separators=(",", ":")) == text
    )

    # Legacy durable rows materialize their projection once and reuse it.
    runs_dir = tmp_path / "runs"
    legacy_store = RunStore(runs_dir)
    legacy_run_id = "20260722T080000Z_project_command_0badc0de"
    legacy_run_dir = runs_dir / legacy_run_id
    legacy_run_dir.mkdir(parents=True)
    legacy_store.create_run(
        run_id=legacy_run_id,
        repo_name="Soma",
        tool="project_command",
        run_dir=legacy_run_dir,
        input_data={"legacy": True},
    )
    current = legacy_store.get_run(legacy_run_id)
    assert (
        legacy_store.transition_terminal(
            legacy_run_id,
            status="completed",
            result={
                "status": "completed",
                "classification": "success",
                "summary": "legacy row",
            },
            expected_statuses=("queued",),
            expected_state_version=current["state_version"],
            ended_at=utc_now(),
            summary="legacy row",
            error="",
            safety_failure=False,
        )
        is not None
    )
    legacy_manager = _manager(legacy_store)
    before = legacy_store.get_run(legacy_run_id)
    assert before["public_result_status"] == PUBLIC_RESULT_STATUS_NOT_MATERIALIZED
    first = legacy_manager.get_terminal_result(legacy_run_id)
    after_first = legacy_store.get_run(legacy_run_id)
    second = legacy_manager.get_terminal_result(legacy_run_id)
    after_second = legacy_store.get_run(legacy_run_id)
    assert first == second
    assert after_first["public_result_status"] == PUBLIC_RESULT_STATUS_READY
    assert after_first["state_version"] == before["state_version"] + 1
    assert after_second["state_version"] == after_first["state_version"]

    # Stale projection bindings rebuild safely and rebind to the source hash.
    legacy_store.update_run(
        legacy_run_id,
        public_result_schema_version="legacy.schema",
        public_result_source_sha256="0" * 64,
    )
    rebuilt = legacy_manager.get_terminal_result(legacy_run_id)
    refreshed = legacy_store.get_run(legacy_run_id)
    assert rebuilt == first
    assert refreshed["public_result_schema_version"] == PUBLIC_RESULT_SCHEMA_VERSION
    assert refreshed["public_result_source_sha256"] == authoritative_result_sha256(
        _raw_result_json(legacy_store, legacy_run_id)
    )


def test_compact_responses_redact_secrets_but_keep_evidence_handles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_dir = tmp_path / "RUNDIRSECRETMARKER"
    store = RunStore(runs_dir)
    run_id = "20260722T090000Z_project_command_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store.create_run(
        run_id=run_id,
        repo_name="Soma",
        tool="project_command",
        run_dir=run_dir,
        input_data={
            "reviewed_script": "REVIEWED-SCRIPT-BODY-7f3",
            "environment": {"API_TOKEN": "envsecretvalue77zz"},
        },
    )
    store.update_run(
        run_id,
        worker_lease_token="leasetoken4242secret",
        worker_identity="313:windows:identsecret99",
    )
    result = {
        "status": "completed",
        "classification": "success",
        "summary": "api_key=plainsecretvalue run finished",
        "stdout": "PROTECTED-STDOUT-BLOB " + "o" * 3000,
        "stderr": "PROTECTED-STDERR-BLOB " + "e" * 3000,
        "environment": {"API_TOKEN": "envsecretvalue77zz"},
        "reviewed_script": "REVIEWED-SCRIPT-BODY-7f3",
    }
    current = store.get_run(run_id)
    assert (
        store.transition_terminal(
            run_id,
            status="completed",
            result=result,
            expected_statuses=("queued",),
            expected_state_version=current["state_version"],
            ended_at=utc_now(),
            summary=result["summary"],
            error="",
            safety_failure=False,
        )
        is not None
    )
    assert publish_run_result(store, run_id)["ok"] is True

    manager = _manager(store)
    monkeypatch.setattr(job_manager_module, "process_is_running", lambda _pid: False)
    monkeypatch.setattr(
        job_manager_module, "process_matches_identity", lambda _pid, _identity: False
    )
    responses = {
        "terminal": manager.get_terminal_result(run_id),
        "summary": manager.get_run_summary(run_id),
        "control": manager.get_control_status(run_id),
        "summary_list": manager.list_run_summaries(limit=5),
    }
    forbidden_markers = (
        "leasetoken4242secret",
        "identsecret99",
        "RUNDIRSECRETMARKER",
        "PROTECTED-STDOUT-BLOB",
        "PROTECTED-STDERR-BLOB",
        "REVIEWED-SCRIPT-BODY-7f3",
        "envsecretvalue77zz",
        "plainsecretvalue",
    )
    for name, response in responses.items():
        blob = canonical_public_json_bytes(response).decode("utf-8")
        for marker in forbidden_markers:
            assert marker not in blob, f"{marker} leaked through {name}"

    # Evidence handles and hashes stay usable for explicit retrieval.
    raw = _raw_result_json(store, run_id)
    terminal = responses["terminal"]
    assert terminal["source_result_sha256"] == authoritative_result_sha256(raw)
    assert terminal["evidence"]["authoritative_operation"] == "result"
    full = manager.get_result(run_id)
    assert full["stdout"].startswith("PROTECTED-STDOUT-BLOB")
    assert full["stderr"].startswith("PROTECTED-STDERR-BLOB")
    # Secret values remain redacted even in explicit full retrieval.
    assert "plainsecretvalue" not in canonical_public_json_bytes(full).decode("utf-8")
