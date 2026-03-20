from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from system.automation_repair import normalize_tool_outcome


ToolRunner = Callable[[str, dict], Any]
LogFn = Callable[[str], None]


def _base_dir() -> Path:
    # Mirror other modules (frozen vs source) without importing UI.
    import sys

    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _has_gemini_key() -> bool:
    base = _base_dir()
    p = base / "config" / "api_keys.json"
    try:
        if not p.exists():
            return False
        data = json.loads(p.read_text(encoding="utf-8"))
        return bool(str(data.get("gemini_api_key") or "").strip())
    except Exception:
        return False


def _pref_bool(prefs: dict, key: str, default: bool = False) -> bool:
    try:
        return bool((prefs or {}).get(key, default))
    except Exception:
        return default


@dataclass
class ToolTest:
    tool: str
    params: dict
    label: str
    requires_api_key: bool = False
    requires_ui_opt_in: bool = False
    intrusive: bool = False
    slow: bool = False
    # For "validation-only" checks: a tool may intentionally reject params.
    # If the outcome is a known/acceptable error kind or message, treat it as PASS.
    accept_error_kinds: tuple[str, ...] = ()
    accept_message_substrings: tuple[str, ...] = ()


def _default_tests() -> list[ToolTest]:
    base = _base_dir()
    diag_root = base / "memory" / "_diagnostics"
    diag_root_parent = diag_root.parent
    diag_file_name = "file_controller_test.txt"
    diag_root_str = str(diag_root)
    diag_parent_str = str(diag_root_parent)

    # Keep tests safe and reversible. Anything that sends messages or visibly
    # changes the user's environment is marked intrusive and skipped in smoke mode.
    return [
        ToolTest("system_monitor", {"action": "stats"}, "System Monitor (stats)"),
        ToolTest("cmd_control", {"command": "echo CRISTINE_DIAG_OK", "timeout": 10, "visible": False}, "CMD Control (echo)"),

        # File controller expects (path=directory, name=filename/foldername). Keep everything inside memory/_diagnostics.
        ToolTest("file_controller", {"action": "create_folder", "path": diag_parent_str, "name": "_diagnostics"}, "File Controller (create folder)"),
        ToolTest("file_controller", {"action": "create_file", "path": diag_root_str, "name": diag_file_name, "content": "OK"}, "File Controller (create file)"),
        ToolTest("file_controller", {"action": "read", "path": diag_root_str, "name": diag_file_name}, "File Controller (read file)"),
        ToolTest("file_controller", {"action": "write", "path": diag_root_str, "name": diag_file_name, "content": "UPDATED", "append": False}, "File Controller (write file)"),
        ToolTest("file_controller", {"action": "delete", "path": diag_root_str, "name": diag_file_name}, "File Controller (delete file)"),
        ToolTest("file_controller", {"action": "delete", "path": diag_parent_str, "name": "_diagnostics"}, "File Controller (delete folder)"),

        ToolTest("browser_control", {"action": "go_to", "url": "https://example.com", "headless": True, "result_timeout_s": 30}, "Browser Control (headless go_to)"),
        ToolTest("browser_control", {"action": "get_text", "headless": True, "result_timeout_s": 30}, "Browser Control (headless get_text)"),

        ToolTest("web_search", {"query": "Example Domain", "mode": "search"}, "Web Search (query)", slow=True),

        ToolTest("query_knowledge_graph", {"search_term": "test"}, "Knowledge Graph (query)"),

        ToolTest("add_task", {"task": "DIAG: task add works"}, "Tasks (add)"),
        ToolTest("show_tasks", {}, "Tasks (show)"),
        # complete/delete require a real id; diagnostics will attempt to resolve automatically.

        ToolTest("real_time_translation", {"mode": "text", "text": "Hello world", "target_lang": "es"}, "Translation", requires_api_key=True),
        ToolTest(
            "project_planner",
            {"project_description": "Create a tiny 3-step plan titled 'Diagnostics Plan'.", "output_format": "markdown"},
            "Project Planner",
            requires_api_key=True,
            slow=True,
        ),
        ToolTest("emotional_companion", {"text": "Diagnostics: say one calming sentence."}, "Emotional Companion", requires_api_key=True),
        ToolTest("code_helper", {"action": "explain", "code": "def add(a,b):\n    return a+b\n"}, "Code Helper (explain)", requires_api_key=True, slow=True),

        # UI / intrusive tools (full mode only)
        ToolTest("open_app", {"app_name": "notepad"}, "Open App (Notepad)", intrusive=True),
        ToolTest("weather_report", {"city": "Dubai", "time": "today"}, "Weather Report (opens browser)", intrusive=True),
        ToolTest("youtube_video", {"action": "trending", "region": "US"}, "YouTube (trending)", intrusive=True, slow=True),
        ToolTest("screen_process", {"angle": "screen", "text": "Describe what is on screen."}, "Screen Process (vision)", intrusive=True, slow=True),
        ToolTest("computer_settings", {"description": "set volume to 10%"}, "Computer Settings (volume)", intrusive=True),
        ToolTest("desktop_control", {"action": "stats"}, "Desktop Control (stats)"),
        ToolTest("computer_control", {"action": "screenshot"}, "Computer Control (screenshot)", requires_ui_opt_in=True, intrusive=True),
        ToolTest("app_switcher", {"app_keyword": "notepad"}, "App Switcher", requires_ui_opt_in=True, intrusive=True),
        ToolTest("app_cheatsheet", {"app_name": "notepad"}, "App Cheatsheet"),
        ToolTest(
            "send_message",
            {"receiver": "", "message_text": "diag", "platform": "whatsapp"},
            "Send Message (validation only)",
            accept_error_kinds=("invalid_params",),
            accept_message_substrings=("please specify",),
        ),
        ToolTest(
            "reminder",
            {"title": "Diagnostics Reminder", "time": "invalid"},
            "Reminder (validation only)",
            accept_error_kinds=("invalid_params",),
            accept_message_substrings=("couldn't understand", "invalid date", "invalid time"),
        ),
        ToolTest(
            "flight_finder",
            {"origin": "Dubai", "destination": "London", "date": "2026-04-15", "passengers": 1, "cabin": "economy", "save": False},
            "Flight Finder",
            slow=True,
            intrusive=True,
            requires_api_key=True,
        ),
        ToolTest("dev_agent", {"description": "Diagnostics: create a tiny hello-world script."}, "Dev Agent", requires_api_key=True, slow=True, intrusive=True),
        ToolTest("agent_task", {"goal": "Diagnostics: report the current time."}, "Agent Task", requires_api_key=True, slow=True, intrusive=True),
    ]


def run_feature_diagnostics(
    *,
    tool_runner: ToolRunner,
    log: LogFn | None = None,
    prefs: dict | None = None,
    mode: str = "smoke",
) -> dict[str, Any]:
    """
    Runs a best-effort feature check across all tools.

    mode:
      - smoke: skips intrusive tools, runs fast background-safe checks
      - full : runs everything (still best-effort; some tools may require user attention)
    """
    prefs = dict(prefs or {})
    mode = (mode or "smoke").strip().lower()
    full = mode == "full"

    allow_ui = _pref_bool(prefs, "automation_allow_ui", False)
    have_key = _has_gemini_key()

    def _log(msg: str) -> None:
        if log:
            try:
                log(msg)
            except Exception:
                pass

    tests = _default_tests()

    # Resolve task id for complete/delete later.
    last_task_id: str | None = None

    start = time.time()
    results: list[dict[str, Any]] = []

    _log(f"[diag] Starting feature diagnostics (mode={mode}, allow_ui={allow_ui}, gemini_key={'yes' if have_key else 'no'})")

    for t in tests:
        if (t.intrusive or t.slow) and not full:
            results.append({"tool": t.tool, "label": t.label, "status": "SKIP", "reason": "smoke_mode"})
            continue

        if t.requires_ui_opt_in and not allow_ui:
            results.append({"tool": t.tool, "label": t.label, "status": "SKIP", "reason": "ui_opt_in_disabled"})
            continue

        if t.requires_api_key and not have_key:
            results.append({"tool": t.tool, "label": t.label, "status": "SKIP", "reason": "missing_gemini_key"})
            continue

        # Special handling: after add_task, grab the newest task id from TaskManager.
        raw = None
        exc: Exception | None = None
        try:
            _log(f"[diag] -> {t.label} [{t.tool}]")
            raw = tool_runner(t.tool, dict(t.params or {}))
        except Exception as e:
            exc = e

        out = normalize_tool_outcome(t.tool, {"tool": t.tool, "parameters": t.params}, raw, exc)
        ok = bool(out.get("ok"))
        err_kind = str(out.get("error_kind") or "")
        msg = str(out.get("message") or "")

        if (not ok) and (t.accept_error_kinds or t.accept_message_substrings):
            if (err_kind and err_kind in set(t.accept_error_kinds)) or any(s in msg.lower() for s in [x.lower() for x in t.accept_message_substrings]):
                ok = True

        # Treat "opt-in disabled" message as SKIP, not FAIL.
        if not ok and ("on-screen automation is disabled" in msg.lower() or "disabled in background-safe mode" in msg.lower()):
            results.append({"tool": t.tool, "label": t.label, "status": "SKIP", "reason": "ui_opt_in_required", "message": msg[:240]})
            continue

        status = "PASS" if ok else "FAIL"
        rec = {"tool": t.tool, "label": t.label, "status": status, "message": msg[:500]}
        results.append(rec)

        if t.tool == "add_task" and ok:
            try:
                from memory.task_manager import get_task_manager

                tm = get_task_manager()
                if tm.tasks:
                    last_task_id = tm.tasks[-1].id
            except Exception:
                pass

    # Attempt complete/delete using the most recent task id from TaskManager, if any.
    try:
        if last_task_id:
            for tool_name, label in [("complete_task", "Tasks (complete)"), ("delete_task", "Tasks (delete)")]:
                _log(f"[diag] -> {label} [{tool_name}]")
                raw = None
                exc = None
                try:
                    raw = tool_runner(tool_name, {"task_id": last_task_id})
                except Exception as e:
                    exc = e
                out = normalize_tool_outcome(tool_name, {"tool": tool_name, "parameters": {"task_id": last_task_id}}, raw, exc)
                ok = bool(out.get("ok"))
                msg = str(out.get("message") or "")
                results.append({"tool": tool_name, "label": label, "status": "PASS" if ok else "FAIL", "message": msg[:500]})
        else:
            results.append({"tool": "complete_task", "label": "Tasks (complete)", "status": "SKIP", "reason": "no_task_id"})
            results.append({"tool": "delete_task", "label": "Tasks (delete)", "status": "SKIP", "reason": "no_task_id"})
    except Exception:
        pass

    elapsed_s = round(time.time() - start, 2)
    pass_n = sum(1 for r in results if r.get("status") == "PASS")
    fail_n = sum(1 for r in results if r.get("status") == "FAIL")
    skip_n = sum(1 for r in results if r.get("status") == "SKIP")

    report = {
        "mode": mode,
        "started_at": start,
        "elapsed_s": elapsed_s,
        "pass": pass_n,
        "fail": fail_n,
        "skip": skip_n,
        "results": results,
    }

    _log(f"[diag] Done. PASS={pass_n} FAIL={fail_n} SKIP={skip_n} elapsed={elapsed_s}s")
    return report
