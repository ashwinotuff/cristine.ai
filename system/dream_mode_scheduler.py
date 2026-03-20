"""
Dream Mode Scheduler for Cristine
Monitors system state and determines when to run Dream Mode tasks
"""

import psutil
import time
import threading
from datetime import datetime
from pathlib import Path
import sys
import json


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
PREFS_PATH = BASE_DIR / "config" / "preferences.json"


class DreamModeScheduler:
    """Monitors conditions for Dream Mode execution."""

    def __init__(self, dream_mode_callback=None):
        """
        Initialize the scheduler.
        
        Args:
            dream_mode_callback: Function to call when Dream Mode should execute
                                (receives a dict of enabled tasks)
        """
        self.dream_mode_callback = dream_mode_callback
        self.preferences = self._load_preferences()
        self._running = False
        self._thread = None
        self._idle_threshold_seconds = 300  # 5 minutes of no keyboard/mouse
        self._last_input_time = time.time()
        self._monitor_thread = None

    def _load_preferences(self) -> dict:
        """Load preferences from JSON."""
        if PREFS_PATH.exists():
            try:
                with open(PREFS_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[DreamScheduler] Error loading preferences: {e}")
        
        return self._get_default_preferences()

    def _get_default_preferences(self) -> dict:
        """Return default preferences."""
        return {
            "dream_mode_enabled": False,
            "dream_file_organization": True,
            "dream_knowledge_graph_improvement": True,
            "dream_self_learning": False,
            "dream_start_hour": 2,
            "dream_end_hour": 5,
            "dream_max_execution_hours": 3,
        }

    def reload_preferences(self) -> None:
        """Reload preferences from file."""
        self.preferences = self._load_preferences()
        print("[DreamScheduler] 🔄 Preferences reloaded")

    def is_dream_mode_enabled(self) -> bool:
        """Check if Dream Mode is enabled."""
        return self.preferences.get("dream_mode_enabled", False)

    def is_system_idle(self) -> bool:
        """Check if system is idle (low CPU and no recent user input)."""
        try:
            # Check CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            if cpu_percent > 20:  # CPU more than 20% means user activity
                return False
            
            # Check memory usage
            memory_percent = psutil.virtual_memory().percent
            if memory_percent > 90:  # System is under memory pressure
                return False
            
            # Check for recent user input (mouse/keyboard)
            idle_time = self._get_system_idle_time()
            if idle_time < self._idle_threshold_seconds:
                return False
            
            return True
        except Exception as e:
            print(f"[DreamScheduler] Error checking idle state: {e}")
            return False

    def _get_system_idle_time(self) -> int:
        """
        Get system idle time in seconds.
        Works on Windows by checking the last input time.
        """
        try:
            import ctypes
            
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
            
            # Get tick count (milliseconds since boot)
            tick_count = ctypes.windll.kernel32.GetTickCount()
            idle_ms = tick_count - lii.dwTime
            idle_seconds = idle_ms // 1000
            
            return idle_seconds
        except Exception:
            # Fallback: assume system is not idle if we can't determine
            return 0

    def is_within_dream_hours(self) -> bool:
        """Check if current time is within Dream Mode hours."""
        try:
            now = datetime.now()
            start_hour = self.preferences.get("dream_start_hour", 2)
            end_hour = self.preferences.get("dream_end_hour", 5)
            
            current_hour = now.hour
            
            # Handle case where end_hour < start_hour (e.g., 2AM-5AM wrapping midnight)
            if start_hour < end_hour:
                return start_hour <= current_hour < end_hour
            else:
                # Wrapping around midnight
                return current_hour >= start_hour or current_hour < end_hour
        except Exception as e:
            print(f"[DreamScheduler] Error checking dream hours: {e}")
            return False

    def should_run_dream_mode(self) -> bool:
        """
        Determine if Dream Mode should run now.
        Returns True if:
        - Dream Mode is enabled
        - System is idle OR within dream hours
        - CPU usage is low
        """
        if not self.is_dream_mode_enabled():
            return False
        
        is_idle = self.is_system_idle()
        is_dream_hour = self.is_within_dream_hours()
        
        return is_idle or is_dream_hour

    def get_enabled_tasks(self) -> dict:
        """Get which Dream Mode tasks are enabled."""
        return {
            "file_organization": self.preferences.get("dream_file_organization", True),
            "knowledge_graph": self.preferences.get("dream_knowledge_graph_improvement", True),
            "self_learning": self.preferences.get("dream_self_learning", False),
        }

    def start(self) -> None:
        """Start the scheduler background thread."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True, name="DreamScheduler")
        self._thread.start()
        print("[DreamScheduler] ✅ Started")

    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        print("[DreamScheduler] 🔴 Stopped")

    def _scheduler_loop(self) -> None:
        """Main scheduler loop."""
        check_interval = 60  # Check every minute
        
        while self._running:
            try:
                # Reload preferences each iteration to pick up changes
                self.reload_preferences()
                
                # Check if Dream Mode should run
                if self.should_run_dream_mode():
                    enabled_tasks = self.get_enabled_tasks()
                    
                    if enabled_tasks.get("file_organization") or enabled_tasks.get("knowledge_graph") or enabled_tasks.get("self_learning"):
                        print(f"[DreamScheduler] 🌙 Dream Mode triggered! Enabled tasks: {enabled_tasks}")
                        
                        # Call the callback
                        if self.dream_mode_callback:
                            self.dream_mode_callback(enabled_tasks)
                
                # Sleep before next check
                time.sleep(check_interval)
            except Exception as e:
                print(f"[DreamScheduler] ⚠️ Error in scheduler loop: {e}")
                time.sleep(check_interval)
