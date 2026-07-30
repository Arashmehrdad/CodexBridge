"""V3-1A-ADAPTER-CONTRACT-1: provider adapter contract and protocol fixtures.

No provider process is launched, no environment is mutated, and no gateway is
registered. Every case parses recorded bytes or inspects an inert command
specification.

The manifest in ``soma/worker_adapters/fixtures/manifest.json`` is the oracle.
It is hand-authored from the fixture bytes, so these tests compare the parser
against an independent expectation rather than against itself.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pytest

from soma.project_scope.store import ProjectScopeStore
from soma.run_store import RunStore
from soma.tasks.models import (
    BackendKind,
    TaskKind,
    TaskState,
    make_task_id,
    normalize_durable_command_request,
    normalized_request_hash,
)
from soma.tasks.store import TaskStore
from soma.worker_adapters import (
    ADAPTERS,
    Capability,
    CapabilityDeclaration,
    CapabilitySupport,
    ClaudeCodeAdapter,
    CodexAdapter,
    EventClass,
    FixtureIntegrityError,
    ProtocolDriftError,
    ProviderCapabilities,
    SessionIdentityOutcome,
    SessionIdentityUnavailable,
    SpecKind,
    StdinMode,
    UsageExtraction,
    fixture_hash,
    fixtures_for,
    get_adapter,
    load_manifest,
    read_fixture_lines,
)
from soma.worker_adapters import contract as contract_module
from soma.worker_adapters import fixtures as fixtures_module
from soma.worker_substrate import WorkerSubstrateStore


PROJECT_ID = "proj_11111111-1111-1111-1111-111111111111"
RESOURCE_ID = "res_22222222-2222-2222-2222-222222222222"
PROMPT_REF = "worker_payload:" + "a" * 64
# A neutral absolute path. The same redaction rule the fixtures follow applies
# here: no real user profile path is committed.
EXE = r"C:\opt\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe"


def _parse(record):
    adapter = get_adapter(record.provider)
    return adapter, adapter.parse_stream(read_fixture_lines(record))


def _usage_summary(result) -> list[dict]:
    """Project usage the same way the manifest declares it (raw_event excluded)."""
    keys = (
        "event_kind",
        "sequence",
        "provider_event_id",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "total_tokens",
        "provider_reported_cost_usd",
    )
    return [
        {key: extraction.to_record_kwargs()[key] for key in keys}
        for extraction in result.usage_extractions
    ]


# ---------------------------------------------------------------------------
# fixture integrity
# ---------------------------------------------------------------------------


ALL_FIXTURES = sorted(load_manifest())


def test_every_fixture_on_disk_is_in_the_manifest():
    declared = {record.path for record in load_manifest().values()}
    on_disk = {
        path.relative_to(fixtures_module.FIXTURE_ROOT).as_posix()
        for path in fixtures_module.FIXTURE_ROOT.rglob("*.jsonl")
    }
    assert on_disk == declared


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_fixture_hash_is_pinned(name):
    record = load_manifest()[name]
    assert fixture_hash(record.full_path) == record.sha256


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_fixture_bytes_are_not_line_ending_rewritten(name):
    """A checkout that rewrites these bytes invalidates every pinned hash.

    This repository runs with ``core.autocrlf=true``, so the fixture directory is
    marked ``-text`` in ``.gitattributes``. This test fails if that protection is
    ever removed, which is a far clearer signal than eighteen hash mismatches.
    """
    assert b"\r" not in load_manifest()[name].full_path.read_bytes()


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_fixture_declares_provenance_and_redaction(name):
    record = load_manifest()[name]
    manifest = json.loads(fixtures_module.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert record.capture_kind in manifest["capture_kinds"]
    assert len(record.provenance) > 20
    assert record.redaction_review.startswith("clean")
    assert record.protocol_version == get_adapter(record.provider).identity.protocol_version


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_fixture_contains_no_credential_shaped_content(name):
    record = load_manifest()[name]
    text = record.full_path.read_text(encoding="utf-8").lower()
    for marker in (
        "sk-",
        "bearer ",
        "api_key",
        "apikey",
        "authorization",
        "password",
        "secret",
        "arash",
    ):
        assert marker not in text, f"{name} contains {marker!r}"


def test_a_tampered_fixture_fails_closed(tmp_path: Path, monkeypatch):
    record = load_manifest()["codex/turn_success"]
    tampered_root = tmp_path / "fixtures"
    tampered_root.mkdir()
    target = tampered_root / record.path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"type":"turn.completed"}\n', encoding="utf-8")
    monkeypatch.setattr(fixtures_module, "FIXTURE_ROOT", tampered_root)
    with pytest.raises(FixtureIntegrityError):
        read_fixture_lines(record)


def test_the_inferred_codex_failure_fixture_is_labelled_and_distrusted():
    """The one fixture Soma never observed must not confer a capability."""
    record = load_manifest()["codex/turn_failed"]
    assert record.capture_kind == "inferred_unverified"
    assert "NOT OBSERVED" in record.provenance
    assert CodexAdapter.capabilities.support(Capability.FAILURE_EVENT_MAPPING) is (
        CapabilitySupport.UNMEASURED
    )


# ---------------------------------------------------------------------------
# deterministic parsing against the independent oracle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_fixture_parses_exactly_as_the_manifest_declares(name):
    record = load_manifest()[name]
    _adapter, result = _parse(record)
    expected = record.expected

    assert [event.event_class.value for event in result.events] == expected[
        "event_classes"
    ]
    assert result.identity_outcome.value == expected["identity_outcome"]
    assert result.native_session_id == expected["native_session_id"]
    assert result.provider_reported_completion is expected[
        "provider_reported_completion"
    ]
    assert result.provider_reported_failure is expected["provider_reported_failure"]
    assert result.unknown_event_count == expected["unknown_event_count"]
    assert result.malformed_line_count == expected["malformed_line_count"]
    assert result.protocol_uncertain is expected["protocol_uncertain"]
    assert result.provider_claimed_completion is expected[
        "provider_claimed_completion"
    ]
    assert result.provider_claimed_failure is expected["provider_claimed_failure"]
    assert _usage_summary(result) == expected["usage"]
    if "observed_identities" in expected:
        assert list(result.observed_identities) == expected["observed_identities"]


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_parsing_is_repeatable(name):
    record = load_manifest()[name]
    _adapter, first = _parse(record)
    _adapter, second = _parse(record)
    assert first.to_dict() == second.to_dict()


# ---------------------------------------------------------------------------
# session identity
# ---------------------------------------------------------------------------


def test_claude_identity_is_extracted_case_sensitively():
    manifest = load_manifest()
    _a, lower = _parse(manifest["claude_code/session_success"])
    _a, upper = _parse(manifest["claude_code/identity_case_variant"])

    assert lower.require_native_session_id() == "91f5d23f-2c4a-4d1e-9b8f-5a7c3e1d0b62"
    assert upper.require_native_session_id() == "91F5D23F-2C4A-4D1E-9B8F-5A7C3E1D0B62"
    # Two spellings are two identities. A parser that normalised case would make
    # these equal and would silently resume the wrong conversation.
    assert lower.native_session_id != upper.native_session_id
    assert lower.native_session_id.upper() == upper.native_session_id


def test_codex_identity_is_extracted_from_thread_started():
    _a, result = _parse(load_manifest()["codex/turn_success"])
    assert result.require_native_session_id() == "019fa061-8c3d-7a41-9e52-6b1f4d8a20c7"


@pytest.mark.parametrize(
    "name", ["claude_code/missing_identity", "codex/missing_identity"]
)
def test_missing_identity_refuses_binding(name):
    _a, result = _parse(load_manifest()[name])
    assert result.identity_outcome is SessionIdentityOutcome.MISSING
    with pytest.raises(SessionIdentityUnavailable) as excinfo:
        result.require_native_session_id()
    assert excinfo.value.outcome is SessionIdentityOutcome.MISSING
    # The raw event carried a completion marker, but identity uncertainty gates
    # the whole stream: no trusted completion or usage may escape it.
    assert result.provider_claimed_completion is True
    assert result.protocol_uncertain is True
    assert result.provider_reported_completion is False
    assert result.usage_extractions == ()


@pytest.mark.parametrize(
    "name", ["claude_code/conflicting_identity", "codex/conflicting_identity"]
)
def test_conflicting_identity_becomes_protocol_uncertainty(name):
    _a, result = _parse(load_manifest()[name])
    assert result.identity_outcome is SessionIdentityOutcome.CONFLICTING
    assert len(result.observed_identities) == 2
    with pytest.raises(SessionIdentityUnavailable):
        result.require_native_session_id()
    # Neither candidate is chosen; the field stays empty rather than picking one.
    assert result.native_session_id == ""


# ---------------------------------------------------------------------------
# fail-closed drift rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["claude_code/drift_unknown_event", "codex/drift_unknown_event"]
)
def test_unknown_events_imply_nothing(name):
    _a, result = _parse(load_manifest()[name])
    assert result.unknown_event_count == 2
    assert result.provider_reported_completion is False
    assert result.provider_reported_failure is False
    assert result.usage_extractions == ()


def test_a_result_without_its_outcome_marker_cannot_report_success():
    """The most dangerous drift: subtype still says success, is_error is gone."""
    record = load_manifest()["claude_code/drift_result_without_marker"]
    _a, result = _parse(record)
    drifted = result.events[-1]
    assert drifted.provider_event_type == "result"
    assert json.loads(record.full_path.read_text().splitlines()[1])["subtype"] == (
        "success"
    )
    assert drifted.event_class is EventClass.UNKNOWN
    assert result.provider_reported_completion is False
    # And it contributes no usage either, though it carried a cost figure.
    assert result.usage_extractions == ()


def test_a_truncated_codex_stream_is_not_a_completion():
    _a, result = _parse(load_manifest()["codex/truncated_no_completion"])
    assert result.provider_reported_completion is False
    assert result.provider_reported_failure is False
    assert result.events[-1].event_class is EventClass.TOOL_ACTIVITY


@pytest.mark.parametrize(
    "name", ["claude_code/malformed_line", "codex/malformed_line"]
)
def test_malformed_lines_are_contained_as_bounded_evidence(name):
    _a, result = _parse(load_manifest()[name])
    malformed = [e for e in result.events if e.event_class is EventClass.MALFORMED]
    assert malformed
    for event in malformed:
        assert event.raw is None
        assert event.raw_excerpt
        assert len(event.raw_excerpt) <= contract_module.MAX_RAW_EXCERPT_CHARS
        assert event.detail
    # Readable events on either side still parse as evidence, but one unreadable
    # line makes the whole stream unsafe for trusted completion or usage.
    assert result.events[0].event_class is EventClass.SESSION_STARTED
    assert result.provider_claimed_completion is True
    assert result.protocol_uncertain is True
    assert result.provider_reported_completion is False
    assert result.usage_extractions == ()
    assert result.raw_usage_extractions
    for event in malformed:
        assert len(event.raw_sha256) == 64
        assert event.raw_sha256 in event.raw_excerpt
        assert event.raw_bytes > 0
        assert "{\"" not in event.raw_excerpt


@pytest.mark.parametrize("provider", ["claude_code", "codex"])
def test_protocol_version_mismatch_fails_closed(provider):
    adapter = get_adapter(provider)
    with pytest.raises(ProtocolDriftError) as excinfo:
        adapter.parse_stream(["{}"], declared_protocol_version="2027-01-01")
    assert excinfo.value.declared == "2027-01-01"
    assert adapter.identity.protocol_version in excinfo.value.supported


def test_an_event_without_a_type_is_unknown_not_ignored():
    adapter = get_adapter("claude_code")
    result = adapter.parse_stream(['{"session_id":"abc","data":1}'])
    assert result.events[0].event_class is EventClass.UNKNOWN
    # Identity is still harvested, so a typeless event cannot hide a conflict.
    assert result.native_session_id == "abc"


def test_a_top_level_non_object_line_is_malformed():
    adapter = get_adapter("codex")
    result = adapter.parse_stream(["[1, 2, 3]"])
    assert result.events[0].event_class is EventClass.MALFORMED
    assert "not an object" in result.events[0].detail
    assert result.events[0].raw is None
    assert result.events[0].raw_sha256
    assert result.protocol_uncertain is True


@pytest.mark.parametrize("provider", ["claude_code", "codex"])
def test_an_unknown_event_taints_a_later_completion_claim(provider):
    if provider == "claude_code":
        lines = [
            '{"type":"system","subtype":"init","session_id":"s1"}',
            '{"type":"future.event","session_id":"s1"}',
            '{"type":"result","subtype":"success","is_error":false,'
            '"session_id":"s1","total_cost_usd":1.0}',
        ]
    else:
        lines = [
            '{"type":"thread.started","thread_id":"t1"}',
            '{"type":"future.event","thread_id":"t1"}',
            '{"type":"turn.completed","usage":{"input_tokens":1,'
            '"output_tokens":1}}',
        ]
    result = get_adapter(provider).parse_stream(lines)
    assert result.provider_claimed_completion is True
    assert result.protocol_uncertain is True
    assert result.provider_reported_completion is False
    assert result.usage_extractions == ()
    assert len(result.raw_usage_extractions) == 1


def test_unmeasured_codex_failure_shape_is_protocol_uncertainty():
    _adapter, result = _parse(load_manifest()["codex/turn_failed"])
    assert result.events[-1].event_class is EventClass.UNKNOWN
    assert result.protocol_uncertain is True
    assert result.provider_claimed_failure is False
    assert result.provider_reported_failure is False


# ---------------------------------------------------------------------------
# usage extraction
# ---------------------------------------------------------------------------


def test_claude_reports_cost_and_leaves_tokens_absent():
    _a, result = _parse(load_manifest()["claude_code/session_success"])
    (usage,) = result.usage_extractions
    assert usage.provider_reported_cost_usd == "0.1094"
    assert usage.input_tokens is None
    assert usage.cached_input_tokens is None
    assert usage.output_tokens is None
    assert usage.total_tokens is None


def test_codex_reports_tokens_and_leaves_cost_absent():
    _a, result = _parse(load_manifest()["codex/turn_success"])
    (usage,) = result.usage_extractions
    assert usage.input_tokens == 1200
    assert usage.cached_input_tokens == 800
    assert usage.output_tokens == 340
    assert usage.total_tokens is None
    # No pricing authority exists, so no dollar figure is derived from tokens.
    assert usage.provider_reported_cost_usd is None


def test_cost_is_preserved_as_text_not_a_float():
    _a, result = _parse(load_manifest()["claude_code/session_success"])
    (usage,) = result.usage_extractions
    assert isinstance(usage.provider_reported_cost_usd, str)


def test_non_numeric_or_absent_figures_become_none_not_guesses():
    assert contract_module.coerce_optional_int("1200") is None
    assert contract_module.coerce_optional_int(12.5) is None
    assert contract_module.coerce_optional_int(True) is None
    assert contract_module.coerce_optional_int(None) is None
    assert contract_module.coerce_optional_int(0) == 0
    assert contract_module.coerce_optional_int(-1) is None
    assert contract_module.coerce_optional_cost(None) is None
    assert contract_module.coerce_optional_cost(True) is None
    assert contract_module.coerce_optional_cost({"usd": 1}) is None
    assert contract_module.coerce_optional_cost(-1) is None
    assert contract_module.coerce_optional_cost(float("nan")) is None
    assert contract_module.coerce_optional_cost(float("inf")) is None
    assert contract_module.coerce_optional_cost("-0.01") is None
    assert contract_module.coerce_optional_cost("NaN") is None
    assert contract_module.coerce_optional_cost("0.1094") == "0.1094"


def test_usage_extraction_refuses_invalid_values_even_without_coercion():
    with pytest.raises(ValueError, match="sequence"):
        UsageExtraction(event_kind="turn", sequence=-1, raw_event={})
    with pytest.raises(ValueError, match="input_tokens"):
        UsageExtraction(
            event_kind="turn", sequence=0, raw_event={}, input_tokens=-1
        )
    with pytest.raises(ValueError, match="provider_reported_cost_usd"):
        UsageExtraction(
            event_kind="turn",
            sequence=0,
            raw_event={},
            provider_reported_cost_usd="Infinity",
        )


# ---------------------------------------------------------------------------
# command specifications
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider", ["claude_code", "codex"])
def test_start_spec_keeps_the_prompt_out_of_argv(provider):
    spec = get_adapter(provider).build_start_spec(
        executable_path=EXE, prompt_payload_ref=PROMPT_REF, working_directory="C:/wt"
    )
    assert spec.spec_kind is SpecKind.START
    assert spec.stdin_mode is not StdinMode.NONE
    assert spec.prompt_payload_ref == PROMPT_REF
    assert not spec.contains_in_argv(PROMPT_REF)
    assert not spec.contains_in_argv("worker_payload:")
    assert not any("a" * 64 in item for item in spec.argv)


@pytest.mark.parametrize("provider", ["claude_code", "codex"])
def test_resume_spec_carries_the_exact_native_identity(provider):
    identity = "91F5d23f-AAAA-4bbb-8ccc-DDDDDDDDDDDD"
    spec = get_adapter(provider).build_resume_spec(
        executable_path=EXE, native_session_id=identity, prompt_payload_ref=PROMPT_REF
    )
    assert spec.spec_kind is SpecKind.RESUME
    assert spec.native_session_id == identity
    # The exact bytes appear in argv; nothing lower-cases an opaque identifier.
    assert identity in spec.argv
    assert not spec.contains_in_argv(identity.lower())


@pytest.mark.parametrize("provider", ["claude_code", "codex"])
def test_resume_without_an_explicit_identity_is_refused(provider):
    with pytest.raises(ValueError, match="resume-last is forbidden"):
        get_adapter(provider).build_resume_spec(
            executable_path=EXE, native_session_id="", prompt_payload_ref=PROMPT_REF
        )


def test_claude_resume_uses_explicit_id_and_never_continue_last():
    spec = ClaudeCodeAdapter().build_resume_spec(
        executable_path=EXE,
        native_session_id="sess-1",
        prompt_payload_ref=PROMPT_REF,
    )
    assert "--resume" in spec.argv
    assert spec.argv[spec.argv.index("--resume") + 1] == "sess-1"
    assert "--continue" not in spec.argv
    assert "--last" not in spec.argv


def test_codex_resume_uses_exec_resume_with_the_thread_id():
    spec = CodexAdapter().build_resume_spec(
        executable_path=EXE,
        native_session_id="thread-9",
        prompt_payload_ref=PROMPT_REF,
    )
    assert spec.argv[:3] == ("exec", "resume", "thread-9")


@pytest.mark.parametrize("provider", ["claude_code", "codex"])
def test_spec_requires_a_fully_resolved_executable(provider):
    for invalid in ("", "codex.exe", ".\\codex.exe", "C:codex.exe", "../codex"):
        with pytest.raises(ValueError, match="executable_path"):
            get_adapter(provider).build_start_spec(
                executable_path=invalid, prompt_payload_ref=PROMPT_REF
            )
    with pytest.raises(ValueError, match="executable_path"):
        get_adapter(provider).build_start_spec(
            executable_path=r"C:\tools\..\codex.exe",
            prompt_payload_ref=PROMPT_REF,
        )


@pytest.mark.parametrize("provider", ["claude_code", "codex"])
def test_spec_requires_an_exact_content_addressed_prompt_reference(provider):
    for invalid in (
        "",
        "worker_payload:",
        "worker_payload:" + "a" * 63,
        "worker_payload:" + "A" * 64,
        "payload:" + "a" * 64,
    ):
        with pytest.raises(ValueError, match="prompt_payload_ref"):
            get_adapter(provider).build_start_spec(
                executable_path=EXE, prompt_payload_ref=invalid
            )


@pytest.mark.parametrize("provider", ["claude_code", "codex"])
def test_spec_declares_provider_recursion_markers_for_removal(provider):
    """Pilot Finding 8: a supervising agent leaks its identity into the worker."""
    spec = get_adapter(provider).build_start_spec(
        executable_path=EXE, prompt_payload_ref=PROMPT_REF
    )
    assert "CLAUDECODE" in spec.environment_remove
    assert any(item.startswith("CODEX_") for item in spec.environment_remove)


def test_a_payload_reference_in_argv_is_structurally_refused():
    from soma.worker_adapters.contract import ProviderCommandSpec

    with pytest.raises(ValueError, match="must travel on stdin"):
        ProviderCommandSpec(
            spec_kind=SpecKind.START,
            executable_path=EXE,
            argv=("--prompt", PROMPT_REF),
            stdin_mode=StdinMode.NONE,
        )


# ---------------------------------------------------------------------------
# capability declarations
# ---------------------------------------------------------------------------


def test_claude_steering_is_declared_supported_from_measurement():
    caps = ClaudeCodeAdapter.capabilities
    assert caps.is_supported(Capability.MID_TURN_STEERING)
    assert "Finding 10" in caps.declarations[Capability.MID_TURN_STEERING].evidence


def test_codex_steering_is_unmeasured_not_supported_and_not_denied():
    caps = CodexAdapter.capabilities
    assert caps.support(Capability.MID_TURN_STEERING) is CapabilitySupport.UNMEASURED
    # Unmeasured is not a yes. Anything gating on capability must see False.
    assert caps.is_supported(Capability.MID_TURN_STEERING) is False


def test_both_providers_declare_root_cancellation_unsafe():
    """Pilot Finding 4 is why Soma owned-tree cancellation is mandatory."""
    for adapter in ADAPTERS.values():
        assert adapter.capabilities.support(
            Capability.ORPHAN_FREE_ROOT_CANCELLATION
        ) is CapabilitySupport.NOT_SUPPORTED


def test_an_incomplete_capability_declaration_is_refused():
    with pytest.raises(ValueError, match="absence is never support"):
        ProviderCapabilities(
            {
                Capability.STRUCTURED_STREAM: CapabilityDeclaration(
                    CapabilitySupport.SUPPORTED, "partial declaration"
                )
            }
        )


def test_every_capability_declaration_cites_evidence():
    for adapter in ADAPTERS.values():
        for capability, declaration in adapter.capabilities.declarations.items():
            assert declaration.evidence.strip(), (
                f"{adapter.identity.provider}.{capability.value} has no evidence"
            )


def test_unknown_provider_has_no_default_adapter():
    with pytest.raises(KeyError, match="no adapter for provider"):
        get_adapter("gemini_cli")


# ---------------------------------------------------------------------------
# authority audit
# ---------------------------------------------------------------------------


ADAPTER_MODULES = (
    "soma/worker_adapters/contract.py",
    "soma/worker_adapters/claude_code.py",
    "soma/worker_adapters/codex.py",
    "soma/worker_adapters/fixtures.py",
    "soma/worker_adapters/__init__.py",
)


def _code_identifiers(relative: str) -> set[str]:
    """Return the exact identifier tokens a module uses.

    The guards below must judge what the code *does*, not what its prose
    discusses -- these modules document the authorities they refuse to touch, so
    a substring scan flags its own documentation. Whole-token comparison also
    avoids the opposite error: ``environment_allowlist`` is not ``environ`` and
    ``_has_tool_use`` is not ``tool``.
    """
    import io
    import tokenize

    source = Path(relative).read_text(encoding="utf-8")
    return {
        token.string
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.NAME
    }


def test_no_event_class_can_be_projected_as_task_state():
    task_states = {state.value for state in TaskState}
    classes = {item.value for item in EventClass}
    assert classes & task_states == set()


def test_adapters_never_import_canonical_state():
    """A parser that could name a task state could eventually set one."""
    for relative in ADAPTER_MODULES:
        identifiers = _code_identifiers(relative)
        for banned in (
            "TaskState",
            "TaskStore",
            "RunStore",
            "TaskManager",
            "JobManager",
            "WorkerSubstrateStore",
            "OutcomeAcceptance",
        ):
            assert banned not in identifiers, f"{relative} references {banned}"


def test_adapters_perform_no_process_or_network_work():
    for relative in ADAPTER_MODULES:
        identifiers = _code_identifiers(relative)
        for banned in (
            "subprocess",
            "system",
            "Popen",
            "socket",
            "requests",
            "httpx",
            "environ",
            "putenv",
            "open",
            "exec",
            "eval",
            "__import__",
        ):
            assert banned not in identifiers, f"{relative} references {banned}"


def test_adapters_register_no_gateway_and_are_not_imported_by_the_server():
    server_source = Path("soma/server.py").read_text(encoding="utf-8")
    assert "worker_adapters" not in server_source
    for relative in ADAPTER_MODULES:
        identifiers = _code_identifiers(relative)
        assert "FastMCP" not in identifiers
        assert "mcp" not in identifiers


def test_no_adapter_method_returns_a_success_verdict():
    """The contract exposes provider *claims*, never a Soma outcome."""
    names = set()
    for obj in (contract_module.StreamParseResult, contract_module.ParsedEvent):
        names |= {name for name, _ in inspect.getmembers(obj)}
    for banned in ("succeeded", "is_success", "accepted", "outcome_accepted"):
        assert banned not in names


# ---------------------------------------------------------------------------
# integration with the accepted worker substrate
# ---------------------------------------------------------------------------


def _canonical_task(runs_dir: Path, *, controller_request_id: str) -> tuple[str, str]:
    task_id = make_task_id()
    run_id = (
        "20260730T101010Z_worker_"
        + hashlib.sha256(controller_request_id.encode("utf-8")).hexdigest()[:8]
    )
    normalized = normalize_durable_command_request(
        repo_name="soma", profile_id="pytest", argv=["python", "-m", "pytest", "-q"]
    )
    RunStore(runs_dir).create_run(
        run_id=run_id,
        repo_name="soma",
        tool="executable_profile",
        run_dir=runs_dir / run_id,
        input_data=normalized,
    )
    TaskStore(runs_dir).reserve_task(
        task_id=task_id,
        task_kind=TaskKind.DURABLE_COMMAND.value,
        controller_request_id=controller_request_id,
        request_hash=normalized_request_hash(normalized),
        backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
        backend_executor="executable_profile",
        backend_ref=run_id,
        backend_identity={"run_id": run_id},
    )
    scope_store = ProjectScopeStore(runs_dir)
    scope_store.init_db()
    now = "2026-07-30T00:00:00+00:00"
    with scope_store.connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (project_id, project_key, lifecycle_state,"
            " scope_generation, created_at, updated_at)"
            " VALUES (?, 'soma-test', 'active', 1, ?, ?)",
            (PROJECT_ID, now, now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO project_resources (resource_id, resource_kind,"
            " opaque_ref, identity_hash, created_at)"
            " VALUES (?, 'repository', 'd:/github/soma', 'soma-test-resource', ?)",
            (RESOURCE_ID, now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO project_resource_bindings (project_id, resource_id,"
            " access_mode, created_at) VALUES (?, ?, 'exclusive', ?)",
            (PROJECT_ID, RESOURCE_ID, now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO project_repository_bindings (project_id,"
            " resource_id, repo_name, repository_root, identity_hash, created_at)"
            " VALUES (?, ?, 'soma', 'd:/github/soma', 'soma-test-resource', ?)",
            (PROJECT_ID, RESOURCE_ID, now),
        )
        conn.execute(
            "INSERT INTO project_task_reservations (task_id, project_id,"
            " scope_generation, status, created_at, updated_at)"
            " VALUES (?, ?, 1, 'attached', ?, ?)",
            (task_id, PROJECT_ID, now, now),
        )
        conn.execute(
            "INSERT INTO project_run_attempts (run_id, project_id, task_id,"
            " resource_id, scope_generation, status, recovery_reason, created_at,"
            " updated_at) VALUES (?, ?, ?, ?, 1, 'attached', '', ?, ?)",
            (run_id, PROJECT_ID, task_id, RESOURCE_ID, now, now),
        )
    return task_id, run_id


def test_extraction_feeds_the_substrate_and_resume_replay_deduplicates(tmp_path: Path):
    """The whole point of the gate: parsed evidence lands in accepted storage.

    ``codex/resume_replay`` is byte-identical to ``codex/turn_success`` because a
    resume replays the same events. Recording both must yield one usage row, and
    the aggregate must reflect one turn -- not two.
    """
    runs_dir = tmp_path / "runs"
    TaskStore(runs_dir)
    store = WorkerSubstrateStore(runs_dir)
    task_id, run_id = _canonical_task(runs_dir, controller_request_id="req-adapter-1")

    adapter = get_adapter("codex")
    manifest = load_manifest()
    first = adapter.parse_stream(read_fixture_lines(manifest["codex/turn_success"]))
    replay = adapter.parse_stream(read_fixture_lines(manifest["codex/resume_replay"]))

    binding, created = store.bind_provider_session(
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        task_id=task_id,
        run_id=run_id,
        provider=adapter.identity.provider,
        native_session_id=first.require_native_session_id(),
        adapter_id=adapter.identity.adapter_id,
        adapter_version=adapter.identity.adapter_version,
        protocol_id=adapter.identity.protocol_id,
        protocol_version=adapter.identity.protocol_version,
    )
    assert created is True

    common = {
        "session_binding_id": binding.session_binding_id,
        "task_id": task_id,
        "run_id": run_id,
        "provider": adapter.identity.provider,
        "native_session_id": binding.native_session_id,
    }
    (usage,) = first.usage_extractions
    _event, was_created = store.record_usage_event(**common, **usage.to_record_kwargs())
    assert was_created is True

    (replayed,) = replay.usage_extractions
    _event, was_created_again = store.record_usage_event(
        **common, **replayed.to_record_kwargs()
    )
    assert was_created_again is False

    summary = store.aggregate_usage(session_binding_id=binding.session_binding_id)
    assert summary["event_count"] == 1
    assert summary["input_tokens"] == 1200
    assert summary["output_tokens"] == 340
    assert summary["provider_reported_cost_usd"] is None
    assert summary["provider_reported_cost_missing_events"] == 1


def test_claude_extraction_lands_cost_without_inventing_tokens(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    TaskStore(runs_dir)
    store = WorkerSubstrateStore(runs_dir)
    task_id, run_id = _canonical_task(runs_dir, controller_request_id="req-adapter-2")

    adapter = get_adapter("claude_code")
    result = adapter.parse_stream(
        read_fixture_lines(load_manifest()["claude_code/session_success"])
    )
    binding, _ = store.bind_provider_session(
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        task_id=task_id,
        run_id=run_id,
        provider=adapter.identity.provider,
        native_session_id=result.require_native_session_id(),
        adapter_id=adapter.identity.adapter_id,
        adapter_version=adapter.identity.adapter_version,
        protocol_id=adapter.identity.protocol_id,
        protocol_version=adapter.identity.protocol_version,
    )
    (usage,) = result.usage_extractions
    event, _ = store.record_usage_event(
        session_binding_id=binding.session_binding_id,
        task_id=task_id,
        run_id=run_id,
        provider=adapter.identity.provider,
        native_session_id=binding.native_session_id,
        **usage.to_record_kwargs(),
    )
    assert event.provider_reported_cost_usd == "0.1094"
    assert event.input_tokens is None
    assert event.raw_event["total_cost_usd"] == 0.1094

    summary = store.aggregate_usage(task_id=task_id)
    assert summary["provider_reported_cost_usd"] == "0.1094"
    assert summary["input_tokens"] is None
    assert summary["input_tokens_missing_events"] == 1


def test_binding_uses_the_exact_parsed_identity_bytes(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    TaskStore(runs_dir)
    store = WorkerSubstrateStore(runs_dir)
    task_id, run_id = _canonical_task(runs_dir, controller_request_id="req-adapter-3")

    adapter = get_adapter("claude_code")
    result = adapter.parse_stream(
        read_fixture_lines(load_manifest()["claude_code/identity_case_variant"])
    )
    binding, _ = store.bind_provider_session(
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        task_id=task_id,
        run_id=run_id,
        provider=adapter.identity.provider,
        native_session_id=result.require_native_session_id(),
        adapter_id=adapter.identity.adapter_id,
        adapter_version=adapter.identity.adapter_version,
        protocol_id=adapter.identity.protocol_id,
        protocol_version=adapter.identity.protocol_version,
    )
    assert binding.native_session_id == "91F5D23F-2C4A-4D1E-9B8F-5A7C3E1D0B62"
    assert store.find_binding_by_run(run_id).native_session_id == (
        "91F5D23F-2C4A-4D1E-9B8F-5A7C3E1D0B62"
    )


def test_adapter_identity_matches_what_the_substrate_stores():
    """A binding row and its adapter must agree on provider and protocol names."""
    for provider, adapter in ADAPTERS.items():
        assert adapter.identity.provider == provider
        assert adapter.identity.adapter_id.endswith(provider)
        for record in fixtures_for(provider):
            assert record.protocol_id == adapter.identity.protocol_id
