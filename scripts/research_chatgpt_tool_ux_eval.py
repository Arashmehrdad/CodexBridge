from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import inspect
import json
import re
from pathlib import Path
from typing import Any

RESEARCH_ONLY_NOTICE = (
    "Offline research evaluator. It reads schemas/files only; it does not restart "
    "Soma, refresh connectors, install plugins, or invoke OpenAI."
)

SPLIT_SOURCES = {
    "knowledge_query",
    "knowledge_action",
    "ssh_query",
    "docker_action",
    "cloudflare_action",
    "trading_query",
}

KNOWN_STATEFUL_NOT_READONLY = {
    "repo_preview",
    "memory_context",
    "research_context",
    "memory_action",
    "knowledge_action",
    "ssh_prepare",
    "ssh_probe",
    "trading_companion_sync",
}

KNOWN_DESTRUCTIVE = {
    "repo_apply",
    "cancel_run",
    "memory_action",
    "docker_destructive_action",
    "cloudflare_destructive_action",
    "ssh_action",
    "run_start",
    "workflow_action",
    "task_action",
    "supervisor_action",
    "trading_signal_cancel_before_entry",
    "trading_companion_action",
    "trading_action_submit",
    "trading_runtime_control",
}

KNOWN_OPEN_WORLD = {
    "ssh_inspect",
    "cloudflare_query",
    "ssh_action",
    "run_start",
    "workflow_action",
    "task_action",
    "supervisor_action",
    "trading_companion_action",
    "trading_action_submit",
    "trading_runtime_control",
    "ssh_probe",
    "docker_action",
    "docker_destructive_action",
    "cloudflare_action",
    "cloudflare_destructive_action",
    "trading_market_query",
}

TOKEN_RE = re.compile(r"[a-z0-9_]+")


def compact_bytes(value: Any) -> int:
    return len(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    )


def discriminator(schema: dict[str, Any]) -> str:
    props = schema.get("properties") or {}
    if "operation" in props:
        return "operation"
    if "action" in props:
        return "action"
    raise ValueError("schema has no operation/action discriminator")


def branch_values(branch: dict[str, Any], disc: str) -> list[str]:
    decl = (branch.get("properties") or {}).get(disc) or {}
    if "const" in decl:
        return [str(decl["const"])]
    if isinstance(decl.get("enum"), list):
        return [str(value) for value in decl["enum"]]
    raise ValueError(f"branch has no {disc} const/enum")


def root_values(schema: dict[str, Any]) -> set[str]:
    disc = discriminator(schema)
    decl = (schema.get("properties") or {})[disc]
    if "const" in decl:
        return {str(decl["const"])}
    values = decl.get("enum")
    if isinstance(values, list):
        return {str(value) for value in values}
    values_out: set[str] = set()
    for branch in schema.get("oneOf") or schema.get("anyOf") or []:
        values_out.update(branch_values(branch, disc))
    return values_out


def slice_schema(schema: dict[str, Any], selected: list[str]) -> dict[str, Any]:
    out = copy.deepcopy(schema)
    disc = discriminator(out)
    target = set(selected)
    root_decl = (out.get("properties") or {})[disc]
    if isinstance(root_decl.get("enum"), list):
        root_decl["enum"] = [
            value for value in root_decl["enum"] if str(value) in target
        ]
    elif "const" in root_decl and str(root_decl["const"]) not in target:
        raise ValueError("root const does not match requested slice")

    branch_key = "oneOf" if isinstance(out.get("oneOf"), list) else "anyOf"
    branches = out.get(branch_key)
    if not isinstance(branches, list):
        raise ValueError("discriminated source schema has no branches")

    kept: list[dict[str, Any]] = []
    seen: list[str] = []
    for branch in branches:
        values = branch_values(branch, disc)
        selected_values = [value for value in values if value in target]
        if not selected_values:
            continue
        item = copy.deepcopy(branch)
        decl = (item.get("properties") or {})[disc]
        if isinstance(decl.get("enum"), list):
            decl["enum"] = [
                value for value in decl["enum"] if str(value) in target
            ]
        kept.append(item)
        seen.extend(selected_values)

    missing = target - set(seen)
    if missing:
        raise ValueError(f"slice missing discriminator values: {sorted(missing)}")
    out[branch_key] = kept
    return out


def current_mcp_descriptors() -> dict[str, dict[str, Any]]:
    import soma.server as server
    from soma.knowledge_tools_integration import register_knowledge_tools

    register_knowledge_tools(server.mcp)
    listed = server.mcp.list_tools()
    tools = asyncio.run(listed) if inspect.isawaitable(listed) else listed
    return {
        tool.name: tool.to_mcp_tool().model_dump(
            mode="json", by_alias=True, exclude_none=False
        )
        for tool in tools
    }


def build_candidate(
    contract: dict[str, Any],
    current: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    candidate: list[dict[str, Any]] = []
    for name, spec in contract["tools"].items():
        source = spec["source_gateway"]
        if source not in current:
            raise KeyError(f"candidate source gateway is absent: {source}")
        descriptor = copy.deepcopy(current[source])
        descriptor["name"] = name
        descriptor["title"] = spec["title"]
        descriptor["description"] = spec["description"]
        descriptor["annotations"] = {
            **spec["annotations"],
            "title": None,
        }
        descriptor["_meta"] = {
            "openai/toolInvocation/invoking": spec["invoking"],
            "openai/toolInvocation/invoked": spec["invoked"],
        }
        if spec.get("operations") is not None:
            descriptor["inputSchema"] = slice_schema(
                descriptor["inputSchema"], list(spec["operations"])
            )
        candidate.append(descriptor)
    return sorted(candidate, key=lambda item: item["name"])


def structural_checks(
    contract: dict[str, Any],
    current: dict[str, dict[str, Any]],
    candidate: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    add(
        "candidate_tool_count",
        len(contract["tools"]) == contract["tool_count"] == 43,
        {"declared": contract["tool_count"], "actual": len(contract["tools"])},
    )

    for name, spec in contract["tools"].items():
        add(
            f"description_trigger:{name}",
            spec["description"].startswith("Use this when"),
            spec["description"][:80],
        )
        for key in ("invoking", "invoked"):
            add(
                f"label_length:{name}:{key}",
                len(spec[key]) <= 64,
                len(spec[key]),
            )

    partitions: dict[str, list[str]] = {}
    for spec in contract["tools"].values():
        if spec["source_gateway"] in SPLIT_SOURCES:
            partitions.setdefault(spec["source_gateway"], []).extend(
                list(spec.get("operations") or [])
            )

    for source in sorted(SPLIT_SOURCES):
        expected = root_values(current[source]["inputSchema"])
        covered = partitions.get(source, [])
        add(
            f"partition_exact:{source}",
            set(covered) == expected and len(covered) == len(set(covered)),
            {
                "expected_count": len(expected),
                "covered_count": len(set(covered)),
                "missing": sorted(expected - set(covered)),
                "extra": sorted(set(covered) - expected),
                "duplicates": len(covered) - len(set(covered)),
            },
        )

    for name in KNOWN_STATEFUL_NOT_READONLY:
        ann = contract["tools"][name]["annotations"]
        add(f"stateful_not_readonly:{name}", ann["readOnlyHint"] is False, ann)

    for name in KNOWN_DESTRUCTIVE:
        ann = contract["tools"][name]["annotations"]
        add(f"destructive_hint:{name}", ann["destructiveHint"] is True, ann)

    for name in KNOWN_OPEN_WORLD:
        ann = contract["tools"][name]["annotations"]
        add(f"open_world_hint:{name}", ann["openWorldHint"] is True, ann)

    descriptor_names = [item["name"] for item in candidate]
    add(
        "candidate_names_unique",
        len(descriptor_names) == len(set(descriptor_names)),
        len(descriptor_names),
    )
    return checks


def tokenize(value: str) -> set[str]:
    stop = {
        "a", "an", "and", "are", "as", "at", "be", "before", "by", "for",
        "from", "in", "into", "is", "it", "of", "on", "or", "that", "the",
        "this", "to", "use", "when", "with", "you", "your",
    }
    return {token for token in TOKEN_RE.findall(value.lower()) if token not in stop}


def lexical_diagnostic(
    contract: dict[str, Any],
    corpus: dict[str, Any],
) -> dict[str, Any]:
    surfaces: dict[str, set[str]] = {}
    for name, spec in contract["tools"].items():
        text = " ".join(
            [
                name,
                spec["title"],
                spec["description"],
                " ".join(spec.get("operations") or []),
            ]
        )
        surfaces[name] = tokenize(text)

    rows: list[dict[str, Any]] = []
    hits = 0
    eligible = 0
    for case in corpus["cases"]:
        expected = case["expected_c1_tool"]
        prompt_tokens = tokenize(case["prompt"])
        ranked = sorted(
            (
                (name, len(prompt_tokens & terms))
                for name, terms in surfaces.items()
            ),
            key=lambda item: (-item[1], item[0]),
        )
        top = [name for name, score in ranked[:5] if score > 0]
        if expected != "NONE":
            eligible += 1
            if expected in top:
                hits += 1
        rows.append(
            {
                "id": case["id"],
                "expected": expected,
                "top5": top,
                "expected_in_top5": expected in top if expected != "NONE" else None,
            }
        )
    return {
        "warning": (
            "Lexical overlap is a diagnostic only. It is not a model-router "
            "simulation and is not a ChatGPT quality claim."
        ),
        "eligible_cases": eligible,
        "expected_in_top5_count": hits,
        "expected_in_top5_rate": round(hits / eligible, 4) if eligible else 0.0,
        "rows": rows,
    }


def corpus_contract_checks(
    contract: dict[str, Any], corpus: dict[str, Any]
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in corpus["cases"]:
        tool = case["expected_c1_tool"]
        if tool == "NONE":
            results.append({"id": case["id"], "ok": True, "detail": "no Soma tool"})
            continue
        spec = contract["tools"].get(tool)
        if spec is None:
            results.append(
                {"id": case["id"], "ok": False, "detail": "expected tool missing"}
            )
            continue
        ann = spec["annotations"]
        ok = True
        mismatches: list[str] = []
        if case["expected_open_world"] and not ann["openWorldHint"]:
            ok = False
            mismatches.append("openWorldHint")
        if case["expected_destructive"] and not ann["destructiveHint"]:
            ok = False
            mismatches.append("destructiveHint")
        if case["expected_stateful"] and ann["readOnlyHint"]:
            ok = False
            mismatches.append("readOnlyHint")
        results.append({"id": case["id"], "ok": ok, "detail": mismatches})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=RESEARCH_ONLY_NOTICE)
    parser.add_argument(
        "--contract",
        default="docs/chatgpt-tool-ux/candidate-contract-c1.json",
    )
    parser.add_argument(
        "--corpus",
        default="docs/chatgpt-tool-ux/golden-corpus-g01-g48.json",
    )
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()

    contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
    corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    current = current_mcp_descriptors()
    candidate = build_candidate(contract, current)
    baseline = [current[name] for name in sorted(current)]

    checks = structural_checks(contract, current, candidate)
    corpus_checks = corpus_contract_checks(contract, corpus)
    all_checks = checks + [
        {
            "name": f"golden_contract:{item['id']}",
            "ok": item["ok"],
            "detail": item["detail"],
        }
        for item in corpus_checks
    ]

    raw_candidate = json.dumps(
        candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    result: dict[str, Any] = {
        "ok": all(item["ok"] for item in all_checks),
        "mode": "offline_research",
        "notice": RESEARCH_ONLY_NOTICE,
        "contract_version": contract["contract_version"],
        "corpus_version": corpus["corpus_version"],
        "baseline": {
            "tool_count": len(baseline),
            "descriptor_bytes": compact_bytes(baseline),
            "input_schema_bytes": sum(
                compact_bytes(item["inputSchema"]) for item in baseline
            ),
        },
        "candidate": {
            "tool_count": len(candidate),
            "descriptor_bytes": len(raw_candidate),
            "input_schema_bytes": sum(
                compact_bytes(item["inputSchema"]) for item in candidate
            ),
            "descriptor_sha256": hashlib.sha256(raw_candidate).hexdigest(),
        },
        "structural_check_count": len(checks),
        "golden_contract_check_count": len(corpus_checks),
        "failed_checks": [
            item["name"] for item in all_checks if not item["ok"]
        ],
        "lexical_diagnostic": lexical_diagnostic(contract, corpus),
    }
    result["candidate"]["descriptor_delta_bytes"] = (
        result["candidate"]["descriptor_bytes"]
        - result["baseline"]["descriptor_bytes"]
    )
    result["candidate"]["descriptor_delta_percent"] = round(
        result["candidate"]["descriptor_delta_bytes"]
        * 100
        / result["baseline"]["descriptor_bytes"],
        1,
    )
    result["candidate"]["input_schema_delta_bytes"] = (
        result["candidate"]["input_schema_bytes"]
        - result["baseline"]["input_schema_bytes"]
    )
    if args.details:
        result["checks"] = all_checks
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
