from __future__ import annotations

import copy
import json
import time
from typing import Any, Callable

from system.automation_repair import (
    analyze_failure,
    normalize_tool_outcome,
    validate_repair_plan,
)


ToolRunner = Callable[[str, dict], Any]
LogFn = Callable[[str], None]
ApprovalFn = Callable[[dict], bool]


def _step_tool(step: dict) -> str:
    return str(step.get("tool") or step.get("name") or "").strip()


def _params_key(step: dict) -> str:
    if isinstance(step.get("parameters"), dict):
        return "parameters"
    if isinstance(step.get("params"), dict):
        return "params"
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
    other = "params" if key == "parameters" else "parameters"
    if other in step:
        step[other] = dict(step[key])


def _apply_patch_ops(
    steps: list[dict],
    index: int,
    patch_ops: list[dict],
) -> tuple[list[str], dict[str, Any]]:
    """
    Apply allowlisted patch ops to the in-memory steps list.

    Returns (applied_ops, meta)
    """
    applied: list[str] = []
    meta: dict[str, Any] = {}
    if not (0 <= index < len(steps)):
        return applied, meta

    for op in patch_ops:
        if not isinstance(op, dict):
            continue
        kind = op.get("op")
        if kind == "update_step_params":
            step = steps[index]
            params = dict(_step_params(step))
            for k, v in (op.get("set") or {}).items():
                params[str(k)] = v
            for k in (op.get("unset") or []):
                try:
                    params.pop(str(k), None)
                except Exception:
                    pass
            _set_step_params(step, params)
            applied.append("update_step_params")

        elif kind == "replace_step":
            new_step = op.get("step")
            if isinstance(new_step, dict):
                steps[index] = copy.deepcopy(new_step)
                applied.append("replace_step")

        elif kind == "insert_steps_after":
            insert_steps = op.get("steps") or []
            if isinstance(insert_steps, list):
                to_insert = [copy.deepcopy(s) for s in insert_steps if isinstance(s, dict)]
                if to_insert:
                    steps[index + 1 : index + 1] = to_insert
                    applied.append("insert_steps_after")
                    meta["inserted_count"] = len(to_insert)

        elif kind == "request_setting":
            # Runner does not auto-apply settings; caller must opt-in.
            applied.append("request_setting")

    return applied, meta


def run_steps_with_self_heal(
    steps: list[dict],
    *,
    tool_runner: ToolRunner,
    log: LogFn | None = None,
    request_approval: ApprovalFn | None = None,
    context: dict | None = None,
    max_step_attempts: int = 3,
    healing_budget: int = 6,
) -> tuple[bool, list[dict], dict[str, Any]]:
    """
    Executes a list of automation steps with a bounded self-healing loop.

    Returns:
      (ok, steps_after_patches, report)

    report:
      {
        "healed": int,
        "patches_applied": bool,
        "persistable_success": bool,
        "last_plan": dict | None,
      }
    """
    context = dict(context or {})
    steps_work = copy.deepcopy(list(steps or []))

    def _log(msg: str) -> None:
        if log:
            try:
                log(msg)
            except Exception:
                pass

    healed = 0
    patches_applied = False
    persistable_success = False
    last_plan: dict | None = None

    i = 0
    while i < len(steps_work):
        step = steps_work[i]
        if not isinstance(step, dict):
            i += 1
            continue

        tool = _step_tool(step)
        if not tool:
            i += 1
            continue

        attempt = 1
        patched_this_step = False
        patched_persistable = False

        while attempt <= max_step_attempts:
            params = dict(_step_params(step))

            _log(f"[automation] -> {tool} (attempt {attempt})")
            raw = None
            exc: Exception | None = None
            try:
                raw = tool_runner(tool, params)
            except Exception as e:
                exc = e

            outcome = normalize_tool_outcome(tool, step, raw, exc)
            if outcome.get("ok"):
                # Mark persistable patches as successful if the step recovered.
                if patched_this_step and patched_persistable:
                    persistable_success = True
                # Emit short output for traceability.
                try:
                    msg = str(outcome.get("message") or "")
                    if msg:
                        _log(msg[:500])
                except Exception:
                    pass
                break

            # Failure: analyze + attempt healing.
            try:
                fail_msg = str(outcome.get("message") or "")
                if fail_msg:
                    _log("[autoheal] Failure: " + fail_msg[:600])
            except Exception:
                pass
            plan = analyze_failure(step, outcome, attempt=attempt, context=context)
            last_plan = plan
            ok, vmsg = validate_repair_plan(plan)
            if not ok:
                _log(f"[autoheal] Invalid RepairPlan: {vmsg}")
                return False, steps_work, {"healed": healed, "patches_applied": patches_applied, "persistable_success": persistable_success, "last_plan": last_plan}

            _log("[autoheal] RepairPlan: " + json.dumps(plan, ensure_ascii=True))

            decision = plan.get("decision")
            risk = plan.get("risk")
            patch_ops = plan.get("patch_ops") or []
            critical = bool(step.get("critical", False))

            if decision == "retry":
                attempt += 1
                time.sleep(0.6)
                continue

            if decision == "patch_and_retry":
                if risk == "needs_approval":
                    approved = False
                    if request_approval:
                        try:
                            approved = bool(request_approval(plan))
                        except Exception:
                            approved = False
                    if not approved:
                        if critical:
                            _log("[autoheal] User denied required approval; aborting.")
                            return False, steps_work, {"healed": healed, "patches_applied": patches_applied, "persistable_success": persistable_success, "last_plan": last_plan}
                        _log("[autoheal] User denied approval; skipping non-critical step.")
                        break
                elif risk != "safe":
                    _log("[autoheal] Patch risk unknown; aborting this run.")
                    return False, steps_work, {"healed": healed, "patches_applied": patches_applied, "persistable_success": persistable_success, "last_plan": last_plan}
                if healing_budget <= 0:
                    _log("[autoheal] Healing budget exhausted; aborting.")
                    return False, steps_work, {"healed": healed, "patches_applied": patches_applied, "persistable_success": persistable_success, "last_plan": last_plan}

                applied, _meta = _apply_patch_ops(steps_work, i, patch_ops)
                if applied:
                    healed += 1
                    healing_budget -= 1
                    patches_applied = True
                    patched_this_step = True
                    patched_persistable = bool(plan.get("persistable", False))
                    _log(f"[autoheal] Applied: {', '.join(applied)}  (budget left: {healing_budget})")
                    # Refresh step reference after replacement.
                    step = steps_work[i]
                    attempt += 1
                    continue

                _log("[autoheal] No patch ops applied; aborting.")
                return False, steps_work, {"healed": healed, "patches_applied": patches_applied, "persistable_success": persistable_success, "last_plan": last_plan}

            if decision == "request_opt_in":
                if risk != "needs_approval":
                    _log("[autoheal] Opt-in must be needs_approval; aborting.")
                    return False, steps_work, {"healed": healed, "patches_applied": patches_applied, "persistable_success": persistable_success, "last_plan": last_plan}

                approved = False
                if request_approval:
                    try:
                        approved = bool(request_approval(plan))
                    except Exception:
                        approved = False

                if not approved:
                    if critical:
                        _log("[autoheal] User denied required approval; aborting.")
                        return False, steps_work, {"healed": healed, "patches_applied": patches_applied, "persistable_success": persistable_success, "last_plan": last_plan}
                    _log("[autoheal] User denied approval; skipping non-critical step.")
                    break

                # Approval granted: caller should have applied requested settings.
                attempt += 1
                continue

            if decision == "ask_user":
                _log("[autoheal] " + str(plan.get("user_message") or "Automation needs attention."))
                return False, steps_work, {"healed": healed, "patches_applied": patches_applied, "persistable_success": persistable_success, "last_plan": last_plan}

            # abort
            _log("[autoheal] " + str(plan.get("user_message") or "Automation aborted."))
            return False, steps_work, {"healed": healed, "patches_applied": patches_applied, "persistable_success": persistable_success, "last_plan": last_plan}

        else:
            # Attempts exhausted without a break -> failure.
            _log("[autoheal] Max attempts reached; aborting.")
            return False, steps_work, {"healed": healed, "patches_applied": patches_applied, "persistable_success": persistable_success, "last_plan": last_plan}

        i += 1

    return True, steps_work, {"healed": healed, "patches_applied": patches_applied, "persistable_success": persistable_success, "last_plan": last_plan}
