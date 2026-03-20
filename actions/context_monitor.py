import os
import time
import threading
import json
import psutil
from pathlib import Path
from datetime import datetime

# Windows-specific imports for high-precision context gathering
import ctypes
from ctypes import wintypes

class ContextMonitor:
    """
    Cristine AI Situation Awareness Engine
    --------------------------------------
    Gathers high-level contextual information about the user's environment
    in a lightweight background thread.
    """
    def __init__(self, interval=5):
        self.interval = interval
        self.running = True
        self.context = {
            "active_app": "N/A",
            "window_title": "N/A",
            "project": "None",
            "focus_time_minutes": 0,
            "idle_seconds": 0,
            "time_of_day": "Morning",
            "clipboard_preview": ""
        }
        self._current_app_start = time.time()
        self._last_app = ""
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def _get_idle_time(self):
        """Returns the time in seconds since the last user input (mouse/keyboard)."""
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
        
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return millis / 1000.0
        return 0

    def _get_active_window_info(self):
        """Uses Win32 API to get the foreground window title and process name."""
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd: return "System", "Idle"
            
            # Get Window Title
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value
            
            # Get Process Name
            pid = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            process = psutil.Process(pid.value)
            app_name = process.name().replace(".exe", "")
            
            return app_name, title
        except Exception:
            return "Unknown", "Unknown"

    def _infer_project(self, app, title):
        """Heuristic to guess the project name from window titles."""
        if not title or title == "Unknown": return "None"
        
        # Common patterns for IDEs and Editors
        if app.lower() in ["code", "visual studio", "pycharm", "sublime_text"]:
            parts = title.split(" - ")
            if len(parts) >= 2:
                # Usually: [File] - [Project] - [App]
                return parts[1] if len(parts) > 2 else parts[0]
        
        # Browsers: usually [Site] - [Tab Name] - [Browser]
        if app.lower() in ["chrome", "msedge", "firefox"]:
            if " - " in title:
                return title.split(" - ")[0]
                
        return "None"

    def _get_clipboard(self):
        """Safely retrieves a snippet of the clipboard."""
        try:
            import pyperclip
            text = pyperclip.paste()
            if text:
                return text[:40].replace("\n", " ") + ("..." if len(text) > 40 else "")
        except Exception:
            pass
        return ""

    def _monitor_loop(self):
        """Background loop to update context."""
        while self.running:
            try:
                app, title = self._get_active_window_info()
                
                # Update Focus Time
                if app == self._last_app:
                    focus_sec = time.time() - self._current_app_start
                    self.context["focus_time_minutes"] = int(focus_sec // 60)
                else:
                    self._current_app_start = time.time()
                    self._last_app = app
                    self.context["focus_time_minutes"] = 0
                
                # Update Context Object
                self.context["active_app"] = app
                self.context["window_title"] = title[:50] + "..." if len(title) > 50 else title
                self.context["project"] = self._infer_project(app, title)
                self.context["idle_seconds"] = int(self._get_idle_time())
                self.context["clipboard_preview"] = self._get_clipboard()
                
                # Time of Day
                hr = datetime.now().hour
                if 5 <= hr < 12: self.context["time_of_day"] = "Morning"
                elif 12 <= hr < 18: self.context["time_of_day"] = "Afternoon"
                elif 18 <= hr < 22: self.context["time_of_day"] = "Evening"
                else: self.context["time_of_day"] = "Night"
                
            except Exception as e:
                print(f"[ContextMonitor] ⚠️ Update error: {e}")
            
            time.sleep(self.interval)

    def get_current_context(self):
        """Thread-safe access to the gathered context."""
        return self.context.copy()

    def stop(self):
        self.running = False

# Singleton instance
monitor = ContextMonitor()
