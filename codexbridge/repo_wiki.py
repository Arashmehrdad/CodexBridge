from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

WIKI_VERSION = 1
MAX_SOURCE_FILES = 2_000
MAX_SOURCE_FILE_BYTES = 250_000
MAX_WIKI_READ_BYTES = 150_000

_BLOCKED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".idea",
    ".vscode",
    "dist",
    "build",
    "coverage",
    "htmlcov",
    "runs",
    "secrets",
    "credentials",
}
_BLOCKED_FILES = {
    ".env",
    ".env.local",
    ".env.production",
    "id_rsa",
    "id_ed25519",
}
_BLOCKED_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".pyc",
    ".pyo",
    ".db",
    ".sqlite",
    ".sqlite3",
}
_TEXT_SUFFIXES = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".md",
    ".rst",
    ".txt",
    ".ini",
    ".cfg",
    ".conf",
    ".sh",
    ".ps1",
    ".bat",
    ".cmd",
    ".sql",
    ".html",
    ".css",
    ".scss",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".cs",
    ".cpp",
    ".c",
    ".h",
}
_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.MULTILINE
)
_JS_IMPORT_RE = re.compile(r"(?:from\s+|require\s*\(\s*)['\"]([^'\"]+)['\"]")
_JS_SYMBOL_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)


def _normalize_search_text(value: str) -> str:
    """Normalize punctuation and spacing for deterministic wiki search."""
    return " ".join(re.findall(r"[^\W_]+", value.casefold(), flags=re.UNICODE))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _safe_relative_page(page: str) -> PurePosixPath:
    normalized = page.replace("\\", "/").strip()
    candidate = PurePosixPath(normalized)
    if not normalized or candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Invalid wiki page: {page!r}")
    if candidate.suffix.lower() not in {".md", ".json"}:
        raise ValueError("Wiki pages must be Markdown or JSON")
    return candidate


class RepoWikiService:
    """Generate and query a deterministic, repository-local knowledge wiki."""

    def __init__(self, repo_root: Path, repo_name: str):
        self.repo_root = Path(repo_root).resolve()
        self.repo_name = repo_name
        self.wiki_root = self.repo_root / ".codexbridge" / "wiki"
        self.manifest_path = self.wiki_root / "manifest.json"

    def refresh(self, *, force: bool = False) -> dict[str, Any]:
        source_files, truncated = self._scan_source_files()
        fingerprint = {item["path"]: item["sha256"] for item in source_files}
        previous = self._load_manifest()
        previous_fingerprint = {
            item.get("path", ""): item.get("sha256", "")
            for item in previous.get("source_files", [])
            if isinstance(item, dict)
        }

        if not force and previous and fingerprint == previous_fingerprint:
            return {
                "ok": True,
                "repo_name": self.repo_name,
                "status": "unchanged",
                "wiki_root": ".codexbridge/wiki",
                "pages": list(previous.get("pages", [])),
                "source_file_count": len(source_files),
                "changed_source_files": [],
                "scan_truncated": bool(previous.get("scan_truncated", truncated)),
                "error": "",
            }

        changed = sorted(
            path
            for path in set(fingerprint) | set(previous_fingerprint)
            if fingerprint.get(path) != previous_fingerprint.get(path)
        )
        analysis = self._analyse(source_files)
        pages = {
            "overview.md": self._render_overview(source_files, analysis, truncated),
            "architecture.md": self._render_architecture(analysis),
            "modules.md": self._render_modules(analysis),
            "validation.md": self._render_validation(source_files, analysis),
        }
        for relative, content in pages.items():
            _atomic_write(self.wiki_root / relative, content)

        manifest = {
            "version": WIKI_VERSION,
            "repo_name": self.repo_name,
            "generated_at": _utc_now(),
            "wiki_root": ".codexbridge/wiki",
            "pages": sorted(pages),
            "source_file_count": len(source_files),
            "scan_truncated": truncated,
            "source_files": source_files,
        }
        _atomic_write(
            self.manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        return {
            "ok": True,
            "repo_name": self.repo_name,
            "status": "generated" if not previous else "refreshed",
            "wiki_root": ".codexbridge/wiki",
            "pages": sorted(pages),
            "source_file_count": len(source_files),
            "changed_source_files": changed,
            "scan_truncated": truncated,
            "error": "",
        }

    def read_page(self, page: str = "overview.md") -> dict[str, Any]:
        relative = _safe_relative_page(page)
        path = (self.wiki_root / Path(*relative.parts)).resolve()
        try:
            path.relative_to(self.wiki_root.resolve())
        except ValueError as exc:
            raise ValueError("Wiki page resolves outside the wiki root") from exc
        if not path.is_file():
            raise FileNotFoundError(f"Wiki page not found: {relative.as_posix()}")
        data = path.read_bytes()
        truncated = len(data) > MAX_WIKI_READ_BYTES
        content = data[:MAX_WIKI_READ_BYTES].decode("utf-8", errors="replace")
        if truncated:
            content += "\n[truncated]\n"
        return {
            "ok": True,
            "repo_name": self.repo_name,
            "page": relative.as_posix(),
            "content": content,
            "size_bytes": len(data),
            "truncated": truncated,
            "error": "",
        }

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        raw_query = query.strip()
        needle = _normalize_search_text(raw_query)
        if not needle:
            raise ValueError("query must not be empty")
        hits: list[dict[str, Any]] = []
        maximum = max(1, min(limit, 100))
        if not self.wiki_root.exists():
            return hits
        for path in sorted(self.wiki_root.rglob("*.md")):
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if needle in _normalize_search_text(line):
                    hits.append(
                        {
                            "source": "wiki",
                            "page": path.relative_to(self.wiki_root).as_posix(),
                            "line": line_number,
                            "snippet": line.strip()[:500],
                        }
                    )
                    if len(hits) >= maximum:
                        return hits
        return hits

    def _load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            return {}
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _scan_source_files(self) -> tuple[list[dict[str, Any]], bool]:
        records: list[dict[str, Any]] = []
        truncated = False
        for root, dirnames, filenames in os.walk(
            self.repo_root, topdown=True, followlinks=False
        ):
            root_path = Path(root)
            dirnames[:] = sorted(
                name
                for name in dirnames
                if name not in _BLOCKED_DIRS
                and not (
                    root_path == self.repo_root / ".codexbridge" and name == "wiki"
                )
                and not (root_path / name).is_symlink()
            )
            for filename in sorted(filenames):
                if len(records) >= MAX_SOURCE_FILES:
                    truncated = True
                    return records, truncated
                path = root_path / filename
                if not self._is_source_candidate(path):
                    continue
                try:
                    data = path.read_bytes()
                except OSError:
                    continue
                if len(data) > MAX_SOURCE_FILE_BYTES or b"\x00" in data[:8192]:
                    continue
                relative = path.relative_to(self.repo_root).as_posix()
                records.append(
                    {
                        "path": relative,
                        "sha256": _sha256_bytes(data),
                        "size_bytes": len(data),
                    }
                )
        return records, truncated

    def _is_source_candidate(self, path: Path) -> bool:
        if path.is_symlink() or not path.is_file():
            return False
        lowered_name = path.name.lower()
        if lowered_name in _BLOCKED_FILES or path.suffix.lower() in _BLOCKED_SUFFIXES:
            return False
        lowered_parts = {
            part.lower() for part in path.relative_to(self.repo_root).parts
        }
        if lowered_parts & _BLOCKED_DIRS:
            return False
        if any(part in {"secrets", "credentials"} for part in lowered_parts):
            return False
        return path.suffix.lower() in _TEXT_SUFFIXES or lowered_name in {
            "dockerfile",
            "makefile",
            "justfile",
            "procfile",
            "license",
            "readme",
        }

    def _analyse(self, source_files: list[dict[str, Any]]) -> dict[str, Any]:
        paths = [item["path"] for item in source_files]
        path_set = set(paths)
        language_counts = Counter(self._language_for_path(path) for path in paths)
        top_level = Counter(path.split("/", 1)[0] for path in paths if "/" in path)
        important = [path for path in paths if self._is_important_file(path)]
        project_types = self._project_types(path_set)
        modules: list[dict[str, Any]] = []
        dependency_edges: set[tuple[str, str]] = set()
        local_python_modules = {
            self._python_module_name(path): path
            for path in paths
            if Path(path).suffix.lower() in {".py", ".pyi"}
        }
        local_roots = {name.split(".", 1)[0] for name in local_python_modules}

        for path in paths:
            suffix = Path(path).suffix.lower()
            if suffix not in {".py", ".pyi", ".js", ".jsx", ".ts", ".tsx"}:
                continue
            absolute = self.repo_root / path
            try:
                text = absolute.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if suffix in {".py", ".pyi"}:
                module = self._analyse_python(path, text)
                source_name = module["module"]
                for imported in module.pop("imports"):
                    root = imported.split(".", 1)[0]
                    if root in local_roots and root != source_name.split(".", 1)[0]:
                        dependency_edges.add((source_name.split(".", 1)[0], root))
                modules.append(module)
            else:
                modules.append(self._analyse_javascript(path, text))

        return {
            "language_counts": dict(
                sorted(language_counts.items(), key=lambda item: (-item[1], item[0]))
            ),
            "top_level": dict(
                sorted(top_level.items(), key=lambda item: (-item[1], item[0]))
            ),
            "important_files": important,
            "project_types": project_types,
            "modules": sorted(modules, key=lambda item: item["path"]),
            "dependency_edges": sorted(dependency_edges),
            "entry_points": self._entry_points(path_set),
        }

    def _analyse_python(self, path: str, text: str) -> dict[str, Any]:
        classes: list[str] = []
        functions: list[str] = []
        imports: list[str] = []
        summary = ""
        try:
            tree = ast.parse(text)
            summary = (ast.get_docstring(tree) or "").strip().split("\n", 1)[0][:240]
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    classes.append(node.name)
                elif isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
        except SyntaxError:
            for left, right in _IMPORT_RE.findall(text):
                imports.append(left or right)
        return {
            "path": path,
            "module": self._python_module_name(path),
            "kind": "python",
            "summary": summary,
            "classes": classes[:50],
            "functions": functions[:80],
            "imports": imports,
        }

    def _analyse_javascript(self, path: str, text: str) -> dict[str, Any]:
        imports = [match for match in _JS_IMPORT_RE.findall(text) if match]
        symbols = _JS_SYMBOL_RE.findall(text)
        return {
            "path": path,
            "module": path,
            "kind": "javascript"
            if Path(path).suffix.lower() in {".js", ".jsx"}
            else "typescript",
            "summary": "",
            "classes": [],
            "functions": symbols[:80],
            "imports": imports[:100],
        }

    def _render_overview(
        self,
        source_files: list[dict[str, Any]],
        analysis: dict[str, Any],
        truncated: bool,
    ) -> str:
        lines = [
            f"# {self.repo_name} repository wiki",
            "",
            "> Generated from the live repository by CodexBridge. Verify critical details against source code before editing.",
            "",
            "## Snapshot",
            "",
            f"- Source files indexed: **{len(source_files)}**",
            f"- Scan truncated: **{'yes' if truncated else 'no'}**",
            f"- Project types: **{', '.join(analysis['project_types']) or 'unclassified'}**",
            "",
            "## Languages and formats",
            "",
        ]
        for language, count in analysis["language_counts"].items():
            lines.append(f"- {language}: {count}")
        lines.extend(["", "## Top-level areas", ""])
        for name, count in list(analysis["top_level"].items())[:30]:
            lines.append(f"- `{name}/`: {count} indexed files")
        lines.extend(["", "## Important files", ""])
        for path in analysis["important_files"][:80]:
            lines.append(f"- `{path}`")
        lines.extend(
            [
                "",
                "## Wiki pages",
                "",
                "- [Architecture](architecture.md)",
                "- [Modules](modules.md)",
                "- [Validation](validation.md)",
                "",
            ]
        )
        return "\n".join(lines)

    def _render_architecture(self, analysis: dict[str, Any]) -> str:
        lines = [
            f"# {self.repo_name} architecture",
            "",
            "## Detected entry points",
            "",
        ]
        if analysis["entry_points"]:
            lines.extend(f"- `{path}`" for path in analysis["entry_points"])
        else:
            lines.append("- No conventional entry point was detected.")
        lines.extend(["", "## Local dependency map", "", "```mermaid", "graph LR"])
        edges = analysis["dependency_edges"][:120]
        if edges:
            for source, target in edges:
                lines.append(
                    f"    {self._mermaid_id(source)}[{source}] --> {self._mermaid_id(target)}[{target}]"
                )
        else:
            lines.append("    repo[Repository] --> modules[Modules]")
        lines.extend(["```", "", "## Architectural module summary", ""])
        for module in analysis["modules"][:120]:
            parts = []
            if module["classes"]:
                parts.append(f"classes: {', '.join(module['classes'][:8])}")
            if module["functions"]:
                parts.append(f"functions: {', '.join(module['functions'][:10])}")
            detail = "; ".join(parts) or module["summary"] or module["kind"]
            lines.append(f"- `{module['path']}` — {detail}")
        lines.append("")
        return "\n".join(lines)

    def _render_modules(self, analysis: dict[str, Any]) -> str:
        lines = [f"# {self.repo_name} modules", ""]
        for module in analysis["modules"][:400]:
            lines.extend([f"## `{module['path']}`", ""])
            if module["summary"]:
                lines.extend([module["summary"], ""])
            lines.append(f"- Kind: {module['kind']}")
            if module["classes"]:
                lines.append(f"- Classes: {', '.join(module['classes'])}")
            if module["functions"]:
                lines.append(f"- Functions/symbols: {', '.join(module['functions'])}")
            lines.append("")
        if len(analysis["modules"]) > 400:
            lines.extend(
                [
                    f"_Module list truncated: {len(analysis['modules']) - 400} additional modules._",
                    "",
                ]
            )
        return "\n".join(lines)

    def _render_validation(
        self, source_files: list[dict[str, Any]], analysis: dict[str, Any]
    ) -> str:
        path_set = {item["path"] for item in source_files}
        commands: list[str] = []
        if (
            "pyproject.toml" in path_set
            or "pytest.ini" in path_set
            or "tox.ini" in path_set
        ):
            commands.append("python -m pytest -q")
        if (
            "pyproject.toml" in path_set
            or "ruff.toml" in path_set
            or ".ruff.toml" in path_set
        ):
            commands.extend(
                ["python -m ruff format --check .", "python -m ruff check ."]
            )
        if "mypy.ini" in path_set or "pyproject.toml" in path_set:
            commands.append("python -m mypy .")
        if "package.json" in path_set:
            commands.extend(["npm test", "npm run lint"])
        if "Cargo.toml" in path_set:
            commands.extend(["cargo test", "cargo clippy --all-targets --all-features"])
        if "go.mod" in path_set:
            commands.extend(["go test ./...", "go vet ./..."])
        commands.append("git diff --check")
        unique_commands = list(dict.fromkeys(commands))
        lines = [
            f"# {self.repo_name} validation",
            "",
            "> These commands are inferred from repository configuration. Prefer project documentation and configured scripts when they differ.",
            "",
            "## Detected project types",
            "",
        ]
        lines.extend(
            f"- {item}" for item in analysis["project_types"] or ["unclassified"]
        )
        lines.extend(["", "## Suggested checks", ""])
        lines.extend(f"- `{command}`" for command in unique_commands)
        lines.extend(["", "## Relevant configuration", ""])
        validation_names = {
            "pyproject.toml",
            "pytest.ini",
            "tox.ini",
            "noxfile.py",
            "ruff.toml",
            ".ruff.toml",
            "mypy.ini",
            "package.json",
            "tsconfig.json",
            "eslint.config.js",
            "biome.json",
            "Cargo.toml",
            "go.mod",
            "Makefile",
            "justfile",
        }
        for path in sorted(path_set):
            if Path(path).name in validation_names:
                lines.append(f"- `{path}`")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _language_for_path(path: str) -> str:
        suffix = Path(path).suffix.lower()
        names = {
            ".py": "Python",
            ".pyi": "Python",
            ".js": "JavaScript",
            ".jsx": "JavaScript",
            ".ts": "TypeScript",
            ".tsx": "TypeScript",
            ".md": "Markdown",
            ".json": "JSON",
            ".toml": "TOML",
            ".yaml": "YAML",
            ".yml": "YAML",
            ".ps1": "PowerShell",
            ".sh": "Shell",
            ".go": "Go",
            ".rs": "Rust",
            ".java": "Java",
            ".cs": "C#",
        }
        return names.get(suffix, suffix.lstrip(".").upper() or "Text")

    @staticmethod
    def _python_module_name(path: str) -> str:
        value = path
        if value.endswith("/__init__.py"):
            value = value[: -len("/__init__.py")]
        elif value.endswith(".py"):
            value = value[:-3]
        elif value.endswith(".pyi"):
            value = value[:-4]
        return value.replace("/", ".") or "root"

    @staticmethod
    def _project_types(paths: set[str]) -> list[str]:
        types: list[str] = []
        if (
            "pyproject.toml" in paths
            or "requirements.txt" in paths
            or any(path.endswith(".py") for path in paths)
        ):
            types.append("Python")
        if "package.json" in paths:
            types.append("Node.js")
        if "Cargo.toml" in paths:
            types.append("Rust")
        if "go.mod" in paths:
            types.append("Go")
        if (
            any(Path(path).name == "Dockerfile" for path in paths)
            or "docker-compose.yml" in paths
            or "compose.yaml" in paths
        ):
            types.append("Containerized")
        return types

    @staticmethod
    def _entry_points(paths: set[str]) -> list[str]:
        conventional = {
            "main.py",
            "app.py",
            "server.py",
            "manage.py",
            "cli.py",
            "index.js",
            "index.ts",
            "src/index.js",
            "src/index.ts",
            "src/main.py",
            "src/main.rs",
            "cmd/main.go",
        }
        result = [
            path
            for path in sorted(paths)
            if path in conventional or Path(path).name in {"__main__.py", "main.go"}
        ]
        return result[:50]

    @staticmethod
    def _is_important_file(path: str) -> bool:
        name = Path(path).name.lower()
        return name in {
            "readme.md",
            "pyproject.toml",
            "package.json",
            "dockerfile",
            "docker-compose.yml",
            "compose.yaml",
            "makefile",
            "justfile",
            "agents.md",
            "contributing.md",
            "architecture.md",
            "cargo.toml",
            "go.mod",
        }

    @staticmethod
    def _mermaid_id(value: str) -> str:
        return "n_" + re.sub(r"[^A-Za-z0-9_]", "_", value)
