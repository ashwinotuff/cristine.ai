import sys
from pathlib import Path
from typing import Tuple


APP_NAME = "Cristine"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _startup_command(start_minimized: bool = False) -> str:
    """
    Build the HKCU Run command string.

    - Frozen: run the packaged exe.
    - Source: use pythonw.exe to avoid a console window.
    """
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        cmd = f"\"{exe}\""
    else:
        py = Path(sys.executable)
        pyw = py.with_name("pythonw.exe")
        exe = pyw if pyw.exists() else py
        script = _base_dir() / "main.py"
        cmd = f"\"{exe}\" \"{script}\""

    # Note: we intentionally do not append CLI args here; the UI reads preferences.json
    # and applies start-minimized behavior itself when tray mode is enabled.
    return cmd


def set_run_on_startup(enabled: bool, *, start_minimized: bool = False) -> Tuple[bool, str]:
    """Enable/disable running Cristine at user login (Windows HKCU Run)."""
    if sys.platform != "win32":
        return False, "Startup registration is supported on Windows only."

    try:
        import winreg  # type: ignore

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _startup_command(start_minimized=start_minimized))
                return True, "Enabled startup launch."
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
            return True, "Disabled startup launch."
    except Exception as e:
        return False, f"Startup registration failed: {str(e)[:160]}"


def is_run_on_startup_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            _v, _t = winreg.QueryValueEx(key, APP_NAME)
        return True
    except Exception:
        return False
