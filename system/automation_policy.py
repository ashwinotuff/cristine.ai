import os


def _truthy(val: str | None) -> bool:
    if val is None:
        return False
    return str(val).strip().lower() in ("1", "true", "yes", "y", "on")


def ui_automation_allowed(player=None) -> bool:
    """
    Returns whether Cristine is allowed to use on-screen automation (mouse/keyboard).
    Default is False to avoid disrupting whatever the user is doing.
    """
    env = os.environ.get("CRISTINE_ALLOW_UI_AUTOMATION")
    if env is not None:
        return _truthy(env)
    try:
        prefs = getattr(player, "preferences", {}) or {}
        return bool(prefs.get("automation_allow_ui", False))
    except Exception:
        return False


def prefer_headless_browser(player=None) -> bool:
    """
    Returns whether browser automation should default to headless mode (no visible window).
    Default is True.
    """
    env = os.environ.get("CRISTINE_BROWSER_HEADLESS")
    if env is not None:
        return _truthy(env)
    try:
        prefs = getattr(player, "preferences", {}) or {}
        return bool(prefs.get("automation_browser_headless", True))
    except Exception:
        return True


def prefer_visible_terminal(player=None) -> bool:
    """
    Returns whether cmd_control should default to opening a visible terminal window.
    Default is False (run silently).
    """
    env = os.environ.get("CRISTINE_CMD_VISIBLE")
    if env is not None:
        return _truthy(env)
    try:
        prefs = getattr(player, "preferences", {}) or {}
        return bool(prefs.get("automation_cmd_visible", False))
    except Exception:
        return False

