"""Flatten the public MCP gateway input contract at the registration boundary.

Every public gateway is a Python function shaped ``tool(request: Union)`` where
``Union`` is a Pydantic discriminated union of operation models. FastMCP derives
a tool's advertised ``inputSchema`` from that signature, so the single parameter
name became a mandatory outer ``request`` object in ``tools/list``:

    {"properties": {"request": {"oneOf": [...]}}, "required": ["request"]}

Callers therefore had to wrap every payload. This module hoists the union to the
argument root for advertisement and unwraps flat calls back into the internal
model at invocation time, so the typed discriminated-union validation, the
operation models, and the durable execution path are all untouched.

The two halves are deliberately split:

* :func:`flatten_request_input_schema` rewrites only what ``tools/list`` shows.
* :class:`FlatGatewayTool` rewrites only how arguments arrive, then delegates to
  FastMCP's own argument validation against the unchanged function signature.

Nothing here validates a payload itself, so there is no second execution path
and no parallel copy of the request models.
"""

from __future__ import annotations

from typing import Any, Final

from fastmcp.exceptions import ToolError, ValidationError
from fastmcp.tools.function_tool import FunctionTool
from pydantic import ValidationError as PydanticValidationError

__all__ = [
    "REQUEST_ENVELOPE_PROPERTY",
    "FlatGatewayTool",
    "flatten_request_input_schema",
    "normalize_gateway_arguments",
]

REQUEST_ENVELOPE_PROPERTY: Final[str] = "request"

# Discriminators used by the public gateway unions. ``system_action``,
# ``knowledge_action`` and their peers discriminate on ``action`` rather than
# ``operation``, so both names are recognised and hoisted identically.
_DISCRIMINATOR_NAMES: Final[tuple[str, ...]] = ("operation", "action")

# Identity fields are pulled directly behind the discriminator so a reader sees
# "which operation, against which object" before any tuning knobs.
_IDENTITY_FIELD_ORDER: Final[tuple[str, ...]] = (
    "repo_name",
    "run_id",
    "group_id",
    "workflow_id",
    "supervisor_id",
    "task_id",
    "host_id",
    "profile_id",
    "signal_id",
    "patch_id",
    "cleanup_id",
    "snapshot_id",
    "base_commit",
    "head_commit",
)

# JSON Schema keywords whose values are themselves schemas, grouped by shape so
# the rewrite walks only real schema positions. Without this split a property
# literally named ``default`` or ``items`` would be mistaken for a keyword.
_SCHEMA_MAP_KEYWORDS: Final[tuple[str, ...]] = (
    "properties",
    "$defs",
    "definitions",
    "patternProperties",
    "dependentSchemas",
)
_SCHEMA_LIST_KEYWORDS: Final[tuple[str, ...]] = (
    "oneOf",
    "anyOf",
    "allOf",
    "prefixItems",
)
_SCHEMA_VALUE_KEYWORDS: Final[tuple[str, ...]] = (
    "items",
    "not",
    "if",
    "then",
    "else",
    "contains",
    "propertyNames",
    "additionalProperties",
    "unevaluatedItems",
    "unevaluatedProperties",
)


def _rewrite_schema(node: Any) -> Any:
    """Strip advertised defaults and order properties, recursively.

    ``default`` is removed because the request models still apply every default
    at validation time; advertising it only teaches clients to materialise
    ``include_stale: false``, ``view: "compact"`` and empty-string noise in
    calls that should have omitted the field entirely. Constraints, enums,
    ranges, descriptions and discriminator metadata are all preserved.
    """
    if isinstance(node, list):
        return [_rewrite_schema(item) for item in node]
    if not isinstance(node, dict):
        return node

    rewritten: dict[str, Any] = {}
    for key, value in node.items():
        if key == "default":
            continue
        if key in _SCHEMA_MAP_KEYWORDS and isinstance(value, dict):
            rewritten[key] = {
                name: _rewrite_schema(child) for name, child in value.items()
            }
        elif key in _SCHEMA_LIST_KEYWORDS and isinstance(value, list):
            rewritten[key] = [_rewrite_schema(child) for child in value]
        elif key in _SCHEMA_VALUE_KEYWORDS:
            rewritten[key] = _rewrite_schema(value)
        else:
            rewritten[key] = value

    properties = rewritten.get("properties")
    if isinstance(properties, dict):
        rewritten["properties"] = _ordered_properties(
            properties, rewritten.get("required")
        )
    return rewritten


def _ordered_properties(
    properties: dict[str, Any], required: Any
) -> dict[str, Any]:
    """Order one object's properties: discriminator, identity, required, rest.

    Dict insertion order survives ``json.dumps`` and the MCP serialisation, so
    this is the only lever available for schema readability. The ordering is a
    pure function of the property names, keeping the live schema hashes stable
    across repeated discovery passes.
    """
    required_names = [name for name in required if isinstance(name, str)] if isinstance(
        required, list
    ) else []
    ranked: list[str] = []
    for name in _DISCRIMINATOR_NAMES:
        if name in properties:
            ranked.append(name)
    for name in _IDENTITY_FIELD_ORDER:
        if name in properties and name not in ranked:
            ranked.append(name)
    for name in required_names:
        if name in properties and name not in ranked:
            ranked.append(name)
    for name in properties:
        if name not in ranked:
            ranked.append(name)
    return {name: properties[name] for name in ranked}


def _resolve_local_ref(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    """Resolve a document-local ``$ref`` (or single-``allOf`` wrapper) once.

    Pydantic sometimes emits the union behind a reference. The root input schema
    must be a concrete object schema for MCP, so the reference is followed for
    the root only; nested references stay intact and keep resolving against the
    ``$defs`` carried along with them.
    """
    seen: set[str] = set()
    current = schema
    while isinstance(current, dict):
        members = current.get("allOf")
        if (
            set(current) <= {"allOf", "title", "description", "default"}
            and isinstance(members, list)
            and len(members) == 1
            and isinstance(members[0], dict)
        ):
            current = members[0]
            continue
        reference = current.get("$ref")
        if not isinstance(reference, str) or not reference.startswith("#/"):
            break
        if reference in seen:
            break
        seen.add(reference)
        resolved: Any = root
        for part in reference[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(resolved, dict) or part not in resolved:
                return current
            resolved = resolved[part]
        if not isinstance(resolved, dict):
            break
        current = resolved
    return current


def _branch_discriminator(branches: list[Any], root: dict[str, Any]) -> tuple[str, list[str]]:
    """Return the shared discriminator name and its full value set.

    Hoisting the discriminator to the root ``properties`` means a client that
    does not traverse ``oneOf`` still sees ``operation`` (or ``action``) and its
    legal values. It is redundant with, and never wider than, the per-branch
    ``const``, so it cannot loosen validation.
    """
    for discriminator in _DISCRIMINATOR_NAMES:
        values: list[str] = []
        for branch in branches:
            resolved = _resolve_local_ref(branch, root) if isinstance(branch, dict) else None
            if not isinstance(resolved, dict):
                return "", []
            declared = (resolved.get("properties") or {}).get(discriminator)
            if not isinstance(declared, dict):
                values = []
                break
            if "const" in declared:
                values.append(str(declared["const"]))
            elif isinstance(declared.get("enum"), list):
                values.extend(str(item) for item in declared["enum"])
            else:
                values = []
                break
        if values:
            # Preserve declaration order; it matches the union's own ordering.
            deduplicated = list(dict.fromkeys(values))
            return discriminator, deduplicated
    return "", []


def flatten_request_input_schema(root: dict[str, Any]) -> dict[str, Any] | None:
    """Hoist a ``{"request": ...}`` envelope schema to the argument root.

    Returns ``None`` when the schema is not a single mandatory ``request``
    envelope, which leaves already-flat tools such as ``cancel_run`` untouched.
    """
    if not isinstance(root, dict):
        return None
    properties = root.get("properties")
    if not isinstance(properties, dict) or set(properties) != {REQUEST_ENVELOPE_PROPERTY}:
        return None
    required = root.get("required")
    if not isinstance(required, list) or list(required) != [REQUEST_ENVELOPE_PROPERTY]:
        return None
    envelope = properties[REQUEST_ENVELOPE_PROPERTY]
    if not isinstance(envelope, dict):
        return None

    inner = _resolve_local_ref(envelope, root)
    if not isinstance(inner, dict):
        return None

    # ``title`` named the wrapper parameter ("Request"), so it is dropped;
    # any ``description`` is real field documentation and is kept.
    body = {
        key: value
        for key, value in inner.items()
        if key not in {"title", "default"}
    }
    definitions = root.get("$defs")

    flat: dict[str, Any] = {"type": "object"}
    branches = body.get("oneOf") or body.get("anyOf")
    if isinstance(branches, list) and branches:
        discriminator, values = _branch_discriminator(branches, root)
        if discriminator:
            flat["properties"] = {
                discriminator: {
                    "type": "string",
                    "enum": values,
                    "description": "Selects the gateway operation; the matching "
                    "variant below defines the remaining fields.",
                }
            }
            flat["required"] = [discriminator]
    flat.update({key: value for key, value in body.items() if key != "type"})
    if isinstance(definitions, dict) and "$defs" not in flat:
        flat["$defs"] = definitions

    rewritten = _rewrite_schema(flat)
    if not isinstance(rewritten, dict):
        return None
    rewritten["type"] = "object"
    return rewritten


def normalize_gateway_arguments(
    arguments: dict[str, Any], *, tool_name: str = ""
) -> dict[str, Any]:
    """Accept the flat public form, still unwrapping legacy ``request`` calls.

    No public operation model declares a field named ``request``, so a lone
    ``request`` object is unambiguously the legacy envelope. Anything else that
    mentions ``request`` is rejected rather than merged, because silently
    picking one of two payloads would hide a caller bug.
    """
    if not isinstance(arguments, dict) or REQUEST_ENVELOPE_PROPERTY not in arguments:
        return arguments

    label = f"{tool_name}: " if tool_name else ""
    wrapped = arguments[REQUEST_ENVELOPE_PROPERTY]
    if len(arguments) != 1:
        conflicting = sorted(key for key in arguments if key != REQUEST_ENVELOPE_PROPERTY)
        raise ToolError(
            f"{label}arguments mix the flat form with a legacy 'request' envelope "
            f"(also received {conflicting}). Send the operation fields at the root, "
            "or send 'request' alone."
        )
    if not isinstance(wrapped, dict):
        raise ToolError(
            f"{label}legacy 'request' envelope must be an object, got "
            f"{type(wrapped).__name__}. Prefer sending the operation fields at the root."
        )
    return wrapped


class FlatGatewayTool(FunctionTool):
    """A gateway tool that advertises flat arguments and re-wraps on the way in.

    ``FunctionTool.run`` validates ``arguments`` against the wrapped function's
    real signature, so restoring the envelope here — rather than validating
    separately — keeps the discriminated union as the single source of truth for
    what a payload may contain. Result projection is inherited untouched.
    """

    async def run(self, arguments: dict[str, Any]) -> Any:
        normalized = normalize_gateway_arguments(arguments, tool_name=self.name)
        try:
            return await super().run({REQUEST_ENVELOPE_PROPERTY: normalized})
        except (ValidationError, PydanticValidationError) as exc:
            raise ValidationError(_reroot_validation_message(str(exc))) from None


def _reroot_validation_message(message: str) -> str:
    """Report validation error locations against the flat arguments.

    Pydantic reports locations relative to the re-applied envelope, e.g.
    ``request.preflight.repo_name``. Callers never send that envelope any more,
    so the prefix is stripped to keep the error pointing at what they actually
    sent. Only the zero-indented location lines carry the prefix; the indented
    detail lines are left exactly as pydantic wrote them.
    """
    lines: list[str] = []
    for line in message.splitlines():
        if line == REQUEST_ENVELOPE_PROPERTY:
            lines.append("(arguments)")
        elif line.startswith(f"{REQUEST_ENVELOPE_PROPERTY}."):
            lines.append(line[len(REQUEST_ENVELOPE_PROPERTY) + 1 :])
        else:
            lines.append(line)
    return "\n".join(lines)
