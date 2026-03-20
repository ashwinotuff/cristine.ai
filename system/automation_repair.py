from __future__ import annotations

import json
import re
from typing import Any


# Public JSON contract:
# ToolOutcome:
#   ok: bool
#   error_kind: str | None
#   message: str
#   raw: Any
#   artifacts: list[dict[str, Any]]
#
# RepairPlan:
#   classification: selector_changed|permission_missing|timeout|network|blocked|unknown
#   decision: retry|patch_and_retry|request_opt_in|ask_user|abort
#   reason: str (1 sentence)
#   user_message: str (<= 15 words, HUD-friendly)
#   patch_ops: list[dict] (allowlisted ops only)
#   risk: safe|needs_approval
#   persistable: bool


_CLASSIFICATIONS = {
    "selector_changed",
    "permission_missing",
    "timeout",
    "network",
    "blocked",
    "unknown",
}

_DECISIONS = {"retry", "patch_and_retry", "request_opt_in", "ask_user", "abort"}
_RISKS = {"safe", "needs_approval"}
_PATCH_OPS = {"update_step_params", "replace_step", "insert_steps_after", "request_setting"}


def _safe_str(x: Any, limit: int = 800) -> str:
    try:
        s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=True)
    except Exception:
        try:
            s = str(x)
        except Exception:
            s = repr(x)
    s = (s or "").strip()
    return s if len(s) <= limit else (s[: limit - 3] + "...")


def _step_tool(step: dict) -> str:
    return str(step.get("tool") or step.get("name") or "").strip()


def _params_key(step: dict) -> str:
    # Preserve whichever key the author used.
    if isinstance(step.get("parameters"), dict):
        return "parameters"
    if isinstance(step.get("params"), dict):
        return "params"
    # Default to "parameters" for patches/persistence.
    return "parameters"


def _step_params(step: dict) -> dict:
    p = step.get("parameters")
    if isinstance(p, dict):
        return p
    p = step.get("params")
    if isinstance(p, dict):
        return p
    return {}


def _set_step_params(step: dict, params: dict) -> None:
    key = _params_key(step)
    step[key] = dict(params or {})
    # Keep the other key in sync if it exists to reduce surprises.
    other = "params" if key == "parameters" else "parameters"
    if other in step:
        step[other] = dict(step[key])


_RE_PERMISSION = re.compile(
    r"(disabled in background-safe mode|on-screen automation is disabled|requires on-screen automation|requires on-screen control)",
    re.IGNORECASE,
)
_RE_TIMEOUT = re.compile(r"(timed out|timeout loading:|timeout)", re.IGNORECASE)
_RE_NETWORK = re.compile(r"(dns|name or service not known|connection (?:reset|refused)|network|offline)", re.IGNORECASE)
_RE_BLOCKED = re.compile(r"(blocked for safety|unsafe)", re.IGNORECASE)
_RE_INVALID = re.compile(r"^(please specify|please describe|please provide|unknown action:)", re.IGNORECASE)


_SIGS: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    "browser_control": [
        ("timeout", re.compile(r"(browser action timed out\.|timeout loading:)", re.IGNORECASE)),
        ("selector_not_found", re.compile(r"(element not found|could not find)", re.IGNORECASE)),
        ("click_error", re.compile(r"^click error:", re.IGNORECASE)),
        ("type_error", re.compile(r"^type error:", re.IGNORECASE)),
        ("nav_error", re.compile(r"navigation error:", re.IGNORECASE)),
        ("browser_error", re.compile(r"^browser error:", re.IGNORECASE)),
        ("page_text_error", re.compile(r"could not get page text:", re.IGNORECASE)),
    ],
    "cmd_control": [
        ("timeout", re.compile(r"^command timed out after \\d+s\\.", re.IGNORECASE)),
        ("blocked", re.compile(r"^blocked for safety:", re.IGNORECASE)),
        ("exec_error", re.compile(r"^(execution error:|could not generate command:)", re.IGNORECASE)),
    ],
    "file_controller": [
        ("fs_permission", re.compile(r"^permission denied:", re.IGNORECASE)),
        ("not_found", re.compile(r"^(file not found|not found|path not found):", re.IGNORECASE)),
        ("wrong_type", re.compile(r"^(not a file|not a directory):", re.IGNORECASE)),
        ("tool_error", re.compile(r"^(could not |error listing files:|search error:|file controller error:)", re.IGNORECASE)),
    ],
    "computer_control": [
        ("permission_missing", re.compile(r"disabled in background-safe mode", re.IGNORECASE)),
    ],
    "desktop_control": [
        ("permission_missing", re.compile(r"requires on-screen", re.IGNORECASE)),
    ],
    "computer_settings": [
        ("permission_missing", re.compile(r"on-screen automation is disabled", re.IGNORECASE)),
    ],
    "send_message": [
        ("permission_missing", re.compile(r"requires on-screen automation|enable preferences -> advanced -> 'allow on-screen automation'", re.IGNORECASE)),
    ],
    "youtube_video": [
        ("invalid_params", re.compile(r"^unknown youtube action:", re.IGNORECASE)),
        ("tool_error", re.compile(r"(try searching to get started|keyboard shortcuts|subtitles and closed captions)", re.IGNORECASE)),
    ],
    "flight_finder": [
        ("invalid_params", re.compile(r"^please provide both origin and destination", re.IGNORECASE)),
        ("invalid_params", re.compile(r"^please provide a departure date", re.IGNORECASE)),
        ("tool_error", re.compile(r"^flight search failed", re.IGNORECASE)),
    ],
    "emotional_companion": [
        ("tool_error", re.compile(r"moment of trouble listening", re.IGNORECASE)),
    ],
}


def normalize_tool_outcome(tool: str, step: dict | None, raw: Any, exc: Exception | None = None) -> dict[str, Any]:
    tool = (tool or "").strip()
    step = step if isinstance(step, dict) else None

    if exc is not None:
        msg = _safe_str(f"{type(exc).__name__}: {exc}", limit=800)
        return {
            "ok": False,
            "error_kind": "exception",
            "message": msg,
            "raw": msg,
            "artifacts": [],
        }

    # Treat None/empty as success for tools that are "fire-and-forget".
    if raw is None:
        return {"ok": True, "error_kind": None, "message": "", "raw": raw, "artifacts": []}

    artifacts: list[dict[str, Any]] = []
    msg = _safe_str(raw, limit=1200)

    # Structured tool returns: recognize common patterns.
    if isinstance(raw, dict):
        if raw.get("ok") is False or "error" in raw:
            return {"ok": False, "error_kind": "tool_error", "message": msg, "raw": raw, "artifacts": []}
        return {"ok": True, "error_kind": None, "message": msg, "raw": raw, "artifacts": []}

    # Strings: apply failure signatures.
    err_kind = None
    if isinstance(raw, str):
        text = raw.strip()
        low = text.lower()
        # If the tool returns a JSON object string, treat status/error fields as authoritative.
        if text.startswith("{") and text.endswith("}"):
            try:
                j = json.loads(text)
                if isinstance(j, dict):
                    status = str(j.get("status") or "").strip().lower()
                    if status and status not in ("success", "ok"):
                        err_kind = status if status in ("not_found", "blocked") else "tool_error"
                    if ("error" in j) and not status:
                        err_kind = "tool_error"
                    # Prefer the JSON message for display.
                    if isinstance(j.get("message"), str) and j.get("message").strip():
                        msg = _safe_str(j.get("message"), limit=1200)
            except Exception:
                pass
        if _RE_INVALID.search(text) or (low.startswith("no ") and "provided" in low):
            err_kind = "invalid_params"
        if tool in _SIGS:
            for kind, rx in _SIGS[tool]:
                if rx.search(text):
                    err_kind = kind
                    break
        if err_kind is None:
            # Generic fail markers (conservative).
            if (
                low.startswith("error:")
                or low.startswith("tool '")
                or low.startswith("execution error:")
                or (("error:" in low) and (0 <= low.find("error:") < 40))
                or low.startswith("failed")
                or (("failed:" in low) and (0 <= low.find("failed:") < 40))
                or low.startswith("could not ")
            ):
                err_kind = "tool_error"
            elif _RE_PERMISSION.search(text):
                err_kind = "permission_missing"
            elif _RE_BLOCKED.search(text):
                err_kind = "blocked"
            elif _RE_TIMEOUT.search(text) and ("timeout" in low or "timed out" in low):
                err_kind = "timeout"

        # Attach a couple of optional artifacts for common browser outputs.
        if step and tool == "browser_control":
            params = _step_params(step)
            action = str(params.get("action") or "").lower().strip()
            if action == "get_text" and err_kind is None and isinstance(raw, str) and raw.strip():
                artifacts.append({"kind": "page_text", "text": raw[:8000]})
            if action in ("go_to", "search") and isinstance(raw, str):
                m = re.search(r"(https?://\\S+)", raw)
                if m:
                    artifacts.append({"kind": "url", "url": m.group(1)})

    ok = err_kind is None
    return {"ok": ok, "error_kind": err_kind, "message": msg, "raw": raw, "artifacts": artifacts}


def validate_repair_plan(plan: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(plan, dict):
        return False, "plan not dict"

    classification = plan.get("classification")
    decision = plan.get("decision")
    risk = plan.get("risk")
    persistable = plan.get("persistable")
    patch_ops = plan.get("patch_ops")

    if classification not in _CLASSIFICATIONS:
        return False, "bad classification"
    if decision not in _DECISIONS:
        return False, "bad decision"
    if risk not in _RISKS:
        return False, "bad risk"
    if not isinstance(persistable, bool):
        return False, "persistable must be bool"
    if not isinstance(patch_ops, list):
        return False, "patch_ops must be list"
    for op in patch_ops:
        if not isinstance(op, dict):
            return False, "patch_op not dict"
        if op.get("op") not in _PATCH_OPS:
            return False, "patch_op op not allowlisted"
    # Keep user_message HUD friendly.
    um = str(plan.get("user_message") or "").strip()
    if not um:
        return False, "missing user_message"
    if len(um.split()) > 15:
        return False, "user_message too long"
    return True, "OK"


def _clamp_int(val: Any, default: int, *, lo: int, hi: int) -> int:
    try:
        n = int(val)
    except Exception:
        n = int(default)
    if n < lo:
        return lo
    if n > hi:
        return hi
    return n


def analyze_failure(step: dict, outcome: dict[str, Any], attempt: int = 1, context: dict | None = None) -> dict[str, Any]:
    """
    Rule-based Repair Plan generator for automation steps.
    Only emits allowlisted patch operations.
    """
    context = context or {}
    attempt = int(attempt or 1)

    tool = _step_tool(step)
    params = _step_params(step)
    critical = bool(step.get("critical", False))
    msg = str(outcome.get("message") or "")
    low = msg.lower()
    err_kind = str(outcome.get("error_kind") or "")

    # File-system permission errors (not UI automation permissions).
    if err_kind == "fs_permission":
        return {
            "classification": "permission_missing",
            "decision": "ask_user",
            "reason": "The step lacks filesystem permission for the requested path.",
            "user_message": "Permission denied; choose a different path.",
            "patch_ops": [],
            "risk": "safe",
            "persistable": False,
        }

    # 1) Permission missing: request opt-in
    if err_kind == "permission_missing" or _RE_PERMISSION.search(msg):
        plan = {
            "classification": "permission_missing",
            "decision": "request_opt_in",
            "reason": "This step requires on-screen automation, but it is disabled.",
            "user_message": "Approve on-screen automation to continue.",
            "patch_ops": [
                {"op": "request_setting", "key": "automation_allow_ui", "value": True},
            ],
            "risk": "needs_approval",
            "persistable": False,
        }
        ok, _ = validate_repair_plan(plan)
        return plan if ok else _abort_plan("unknown", "Invalid repair plan.", "Repair plan invalid.")

    # 2) Browser selector changed -> smart_* retarget
    if tool == "browser_control":
        action = str(params.get("action") or "").lower().strip()
        selector = params.get("selector")
        text = params.get("text")

        selectorish = bool(selector) or bool(text)
        looks_like_selector_failure = (
            err_kind in ("selector_not_found", "click_error", "type_error")
            or "element not found" in low
            or "not clickable" in low
            or low.startswith("type error:")
            or low.startswith("click error:")
            or "could not find input" in low
            or "could not find:" in low
        )

        if action in ("click", "type") and selectorish and looks_like_selector_failure:
            # Best available description for smart_*.
            desc = (
                str(step.get("description") or "").strip()
                or str(params.get("description") or "").strip()
                or str(text or "").strip()
            )
            if not desc:
                # Fall back to selector itself (not ideal, but better than empty).
                desc = str(selector or "").strip()

            if action == "click":
                plan = {
                    "classification": "selector_changed",
                    "decision": "patch_and_retry",
                    "reason": "Target element was not found; selector likely changed.",
                    "user_message": "Retargeting click and retrying.",
                    "patch_ops": [
                        {
                            "op": "update_step_params",
                            "set": {"action": "smart_click", "description": desc},
                            "unset": ["selector", "text"],
                        }
                    ],
                    "risk": "safe",
                    "persistable": True,
                }
                ok, _ = validate_repair_plan(plan)
                return plan if ok else _abort_plan("unknown", "Invalid repair plan.", "Repair plan invalid.")

            if action == "type":
                plan = {
                    "classification": "selector_changed",
                    "decision": "patch_and_retry",
                    "reason": "Input target was not found; selector likely changed.",
                    "user_message": "Retargeting input and retrying.",
                    "patch_ops": [
                        {
                            "op": "update_step_params",
                            "set": {"action": "smart_type", "description": desc, "text": str(params.get("text", ""))},
                            "unset": ["selector"],
                        }
                    ],
                    "risk": "safe",
                    "persistable": True,
                }
                ok, _ = validate_repair_plan(plan)
                return plan if ok else _abort_plan("unknown", "Invalid repair plan.", "Repair plan invalid.")

    # 3) Timeout -> increase and retry (cmd/browser)
    if err_kind == "timeout" or (("timed out" in low or "timeout loading:" in low) and _RE_TIMEOUT.search(msg)):
        if tool == "cmd_control":
            cur_timeout = _clamp_int(params.get("timeout", None), 20, lo=5, hi=600)
            new_timeout = min(600, max(cur_timeout + 5, cur_timeout * 2))
            plan = {
                "classification": "timeout",
                "decision": "patch_and_retry",
                "reason": "The command timed out before completing.",
                "user_message": "Increasing timeout and retrying.",
                "patch_ops": [
                    {"op": "update_step_params", "set": {"timeout": int(new_timeout)}, "unset": []},
                ],
                "risk": "safe",
                "persistable": True,
            }
            ok, _ = validate_repair_plan(plan)
            return plan if ok else _abort_plan("unknown", "Invalid repair plan.", "Repair plan invalid.")

        if tool == "browser_control":
            # Two knobs: playwright action timeout_ms, and thread result timeout (result_timeout_s).
            cur_ms = _clamp_int(params.get("timeout_ms", None), 8000, lo=1000, hi=120000)
            cur_res = _clamp_int(params.get("result_timeout_s", None), 30, lo=5, hi=300)
            new_ms = min(120000, max(cur_ms + 1000, cur_ms * 2))
            new_res = min(300, max(cur_res + 5, cur_res * 2))
            plan = {
                "classification": "timeout",
                "decision": "patch_and_retry",
                "reason": "The browser step timed out before completing.",
                "user_message": "Increasing browser timeouts and retrying.",
                "patch_ops": [
                    {"op": "update_step_params", "set": {"timeout_ms": int(new_ms), "result_timeout_s": int(new_res)}, "unset": []},
                ],
                "risk": "safe",
                "persistable": True,
            }
            ok, _ = validate_repair_plan(plan)
            return plan if ok else _abort_plan("unknown", "Invalid repair plan.", "Repair plan invalid.")

        # Generic timeout: retry once or abort if critical and repeated.
        if attempt < 2:
            plan = {
                "classification": "timeout",
                "decision": "retry",
                "reason": "The step timed out; retrying may succeed.",
                "user_message": "Retrying after a timeout.",
                "patch_ops": [],
                "risk": "safe",
                "persistable": False,
            }
            ok, _ = validate_repair_plan(plan)
            return plan if ok else _abort_plan("unknown", "Invalid repair plan.", "Repair plan invalid.")

    # 4) Blocked for safety
    if err_kind == "blocked" or _RE_BLOCKED.search(msg):
        plan = {
            "classification": "blocked",
            "decision": "abort",
            "reason": "The step was blocked for safety and cannot be auto-fixed.",
            "user_message": "Blocked for safety; aborting automation.",
            "patch_ops": [],
            "risk": "safe",
            "persistable": False,
        }
        ok, _ = validate_repair_plan(plan)
        return plan if ok else _abort_plan("unknown", "Invalid repair plan.", "Repair plan invalid.")

    # 5) Network-ish: quick retry
    if err_kind == "network" or _RE_NETWORK.search(msg):
        plan = {
            "classification": "network",
            "decision": "retry" if attempt < 2 else ("abort" if critical else "ask_user"),
            "reason": "Network error detected; retrying may help.",
            "user_message": "Network issue; retrying.",
            "patch_ops": [],
            "risk": "safe",
            "persistable": False,
        }
        ok, _ = validate_repair_plan(plan)
        return plan if ok else _abort_plan("unknown", "Invalid repair plan.", "Repair plan invalid.")

    # Default: ask user or abort based on criticality.
    if critical:
        return _abort_plan("unknown", "Unhandled failure; this step is critical.", "Critical step failed; aborting.")
    return {
        "classification": "unknown",
        "decision": "ask_user",
        "reason": "Unhandled failure; user input is required.",
        "user_message": "Automation needs attention; check logs.",
        "patch_ops": [],
        "risk": "safe",
        "persistable": False,
    }


def _abort_plan(classification: str, reason: str, user_message: str) -> dict[str, Any]:
    classification = classification if classification in _CLASSIFICATIONS else "unknown"
    plan = {
        "classification": classification,
        "decision": "abort",
        "reason": str(reason)[:200],
        "user_message": str(user_message)[:80],
        "patch_ops": [],
        "risk": "safe",
        "persistable": False,
    }
    ok, _ = validate_repair_plan(plan)
    return plan if ok else {
        "classification": "unknown",
        "decision": "abort",
        "reason": "Repair plan invalid.",
        "user_message": "Automation aborted.",
        "patch_ops": [],
        "risk": "safe",
        "persistable": False,
    }
