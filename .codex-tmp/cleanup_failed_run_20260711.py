from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "20260711T022807Z_codex_implement_task_efec3efd"
RESULT_PATH = ROOT / "runs" / RUN_ID / "result.json"
PRESERVE = {
    "scripts/configure_runpod_wan_ssh.ps1",
    "tests/pytest_tmp_probe/a.tmp",
}


def current_untracked() -> set[str]:
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths: set[str] = set()
    for record in completed.stdout.split(b"\0"):
        if record.startswith(b"?? "):
            paths.add(record[3:].decode("utf-8", errors="strict").replace("\\", "/"))
    return paths


def main() -> None:
    payload = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    introduced = {str(path).replace("\\", "/") for path in payload.get("introduced_changes", [])}
    candidates = sorted((introduced & current_untracked()) - PRESERVE)
    removed: list[str] = []
    skipped: list[dict[str, str]] = []
    root = ROOT.resolve()

    for relative in candidates:
        target = (root / relative).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            skipped.append({"path": relative, "reason": "outside repository"})
            continue
        if relative.startswith("runs/") or relative.startswith(".git/"):
            skipped.append({"path": relative, "reason": "protected path"})
            continue
        if not target.exists():
            continue
        if target.is_symlink() or not target.is_file():
            skipped.append({"path": relative, "reason": "not a regular file"})
            continue
        if target.stat().st_size > 16:
            skipped.append({"path": relative, "reason": "larger than temp-artifact limit"})
            continue
        target.unlink()
        removed.append(relative)

    print(json.dumps({
        "ok": not skipped,
        "run_id": RUN_ID,
        "candidate_count": len(candidates),
        "removed_count": len(removed),
        "removed": removed,
        "skipped": skipped,
        "preserved": sorted(PRESERVE),
    }, indent=2))


if __name__ == "__main__":
    main()
