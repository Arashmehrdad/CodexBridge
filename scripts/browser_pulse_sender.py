from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from soma.events import redact_and_truncate
from soma.supervisor_store import SupervisorStore, validate_supervisor_id


HANDOFF_STATUSES = {"needs_input", "completed", "failed", "cancelled"}
DEFAULT_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_PROMPT_LIMIT = 12000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_chat_url(chat_url: str) -> str:
    parsed = urlparse(chat_url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "chatgpt.com"
        or not parsed.path.startswith("/c/")
    ):
        raise ValueError(
            "chat_url must be a real ChatGPT chat URL like https://chatgpt.com/c/..."
        )
    return chat_url


def validate_local_cdp_url(cdp_url: str) -> str:
    parsed = urlparse(cdp_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("CDP URL must be local, for example http://127.0.0.1:9222")
    return cdp_url


def is_handoff_status(status: str) -> bool:
    return status in HANDOFF_STATUSES


def supervisor_prompt_path(runs_dir: Path, supervisor_id: str) -> Path:
    validate_supervisor_id(supervisor_id)
    return runs_dir / "supervisors" / supervisor_id / "resume_prompt.txt"


def build_prompt(
    *, runs_dir: Path, supervisor_id: str, status: str, override_prompt: str = ""
) -> str:
    validate_supervisor_id(supervisor_id)
    if override_prompt:
        return str(redact_and_truncate(override_prompt, limit=DEFAULT_PROMPT_LIMIT))

    path = supervisor_prompt_path(runs_dir, supervisor_id)
    if path.exists():
        return str(
            redact_and_truncate(
                path.read_text(encoding="utf-8"), limit=DEFAULT_PROMPT_LIMIT
            )
        )

    fallback = (
        "Soma supervisor handoff.\n"
        f"supervisor_id: {supervisor_id}\n"
        f"status: {status}\n"
        "Please retrieve the supervisor status, events, result, and resume prompt from Soma."
    )
    return str(redact_and_truncate(fallback, limit=DEFAULT_PROMPT_LIMIT))


def safe_log_event(
    *,
    supervisor_id: str,
    status: str,
    success: bool,
    log_file: Path | None = None,
) -> dict[str, Any]:
    event = {
        "supervisor_id": supervisor_id,
        "status": status,
        "timestamp": utc_now(),
        "success": bool(success),
    }
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def _fill_chatgpt_composer(page: Any, prompt: str) -> None:
    selectors = [
        "div[contenteditable='true']",
        "textarea",
        "[data-testid='composer-textarea']",
    ]
    last_error: Exception | None = None
    for selector in selectors:
        try:
            locator = page.locator(selector).last
            locator.wait_for(state="visible", timeout=15000)
            locator.click()
            locator.fill(prompt)
            return
        except (
            Exception
        ) as exc:  # pragma: no cover - exercised only with a real browser
            last_error = exc
    raise RuntimeError(f"Unable to find ChatGPT composer: {last_error}")


def _click_chatgpt_send(page: Any) -> None:
    selectors = [
        "[data-testid='send-button']",
        "button[aria-label='Send prompt']",
        "button[aria-label='Send message']",
    ]
    last_error: Exception | None = None
    for selector in selectors:
        try:
            locator = page.locator(selector).last
            locator.wait_for(state="visible", timeout=15000)
            locator.click()
            return
        except (
            Exception
        ) as exc:  # pragma: no cover - exercised only with a real browser
            last_error = exc
    raise RuntimeError(f"Unable to find ChatGPT send button: {last_error}")


def send_prompt_via_cdp(
    *, cdp_url: str, chat_url: str, prompt: str, close_tab: bool = False
) -> None:
    validate_local_cdp_url(cdp_url)
    validate_chat_url(chat_url)
    try:
        from playwright.sync_api import sync_playwright
    except (
        ImportError
    ) as exc:  # pragma: no cover - depends on local optional dependency
        raise RuntimeError(
            'Playwright is required for send mode. Install with: python -m pip install "playwright"'
        ) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        try:
            page.goto(chat_url, wait_until="domcontentloaded", timeout=30000)
            _fill_chatgpt_composer(page, prompt)
            _click_chatgpt_send(page)
            page.wait_for_timeout(1000)
        finally:
            if close_tab:
                page.close()
            browser.close()


def load_supervisor(store: SupervisorStore, supervisor_id: str) -> dict[str, Any]:
    validate_supervisor_id(supervisor_id)
    return store.get_supervisor(supervisor_id)


def run_once(
    *,
    store: SupervisorStore,
    runs_dir: Path,
    supervisor_id: str,
    chat_url: str,
    cdp_url: str = DEFAULT_CDP_URL,
    dry_run: bool = True,
    close_tab: bool = False,
    override_prompt: str = "",
    log_file: Path | None = None,
) -> dict[str, Any]:
    validate_chat_url(chat_url)
    validate_local_cdp_url(cdp_url)
    supervisor = load_supervisor(store, supervisor_id)
    status = str(supervisor["status"])
    if not is_handoff_status(status):
        event = safe_log_event(
            supervisor_id=supervisor_id, status=status, success=False, log_file=log_file
        )
        return {**event, "sent": False, "reason": "status is not a handoff state"}

    prompt = build_prompt(
        runs_dir=runs_dir,
        supervisor_id=supervisor_id,
        status=status,
        override_prompt=override_prompt,
    )
    if not dry_run:
        send_prompt_via_cdp(
            cdp_url=cdp_url, chat_url=chat_url, prompt=prompt, close_tab=close_tab
        )
    event = safe_log_event(
        supervisor_id=supervisor_id, status=status, success=True, log_file=log_file
    )
    return {**event, "sent": not dry_run, "dry_run": dry_run}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send a local browser pulse for a Soma supervisor handoff."
    )
    parser.add_argument("--runs-dir", default="runs")
    parser.add_argument("--supervisor-id", required=True)
    parser.add_argument("--chat-url", required=True)
    parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--close-tab", action="store_true")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--log-file", default="")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--send", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runs_dir = Path(args.runs_dir).resolve()
    store = SupervisorStore(runs_dir)
    log_file = (
        Path(args.log_file).resolve()
        if args.log_file
        else runs_dir / "browser_pulse_sender.jsonl"
    )

    while True:
        try:
            result = run_once(
                store=store,
                runs_dir=runs_dir,
                supervisor_id=args.supervisor_id,
                chat_url=args.chat_url,
                cdp_url=args.cdp_url,
                dry_run=args.dry_run,
                close_tab=args.close_tab,
                override_prompt=args.prompt,
                log_file=log_file,
            )
        except Exception as exc:
            safe_log_event(
                supervisor_id=args.supervisor_id,
                status="unknown",
                success=False,
                log_file=log_file,
            )
            print(
                json.dumps({"success": False, "error": str(exc)}, sort_keys=True),
                file=sys.stderr,
            )
            return 1

        print(json.dumps(result, sort_keys=True))
        if args.once or result.get("sent") or result.get("dry_run"):
            return 0 if result["success"] else 1
        time.sleep(max(1.0, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
