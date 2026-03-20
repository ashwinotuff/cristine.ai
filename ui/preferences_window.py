"""
Preferences Window for Cristine
Handles user-configurable settings for Dream Mode, Interface, Advanced options, and User Profile
"""

import json
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from pathlib import Path
import sys
import threading
from memory.user_profile_manager import get_profile_manager
from ui.user_profile_page import show_import_dialog, show_data_viewer


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
PREFS_PATH = BASE_DIR / "config" / "preferences.json"

# UI Colors (match HUD theme)
C_BG_TOP = "#03060A"
C_BG_BOT = "#0A1220"
C_PRI = "#4FD1FF"
C_SEC = "#A66CFF"
C_ACC = "#52FFA8"
C_GLASS_BG = "#0D1B2E"
C_GLASS_BORDER = "#3A5A7E"
C_TEXT_PRI = "#CBEFFF"
C_TEXT_SEC = "#7FAAC9"
C_DIM = "#1B2D44"
C_DIMMER = "#0D1520"
C_WARN = "#FFB020"
C_SUCCESS = "#52FFA8"

def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = (h or "").strip().lstrip("#")
    if len(h) != 6:
        return (0, 0, 0)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except Exception:
        return (0, 0, 0)

def _rgb_to_hex(r: int, g: int, b: int) -> str:
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))
    return f"#{r:02X}{g:02X}{b:02X}"

def _shade(hex_color: str, amount: float) -> str:
    """
    amount in [-1..1]
      >0: blend toward white (lighter)
      <0: blend toward black (darker)
    """
    r, g, b = _hex_to_rgb(hex_color)
    a = float(amount)
    a = max(-1.0, min(1.0, a))
    if a >= 0:
        r = r + (255 - r) * a
        g = g + (255 - g) * a
        b = b + (255 - b) * a
    else:
        r = r * (1.0 + a)
        g = g * (1.0 + a)
        b = b * (1.0 + a)
    return _rgb_to_hex(r, g, b)

# Depth layers
C_GLASS_BG_L1 = _shade(C_GLASS_BG, 0.06)
C_GLASS_BG_L2 = _shade(C_GLASS_BG, 0.12)
C_EDGE_HI = _shade(C_GLASS_BORDER, 0.30)
C_EDGE_LO = _shade(C_DIMMER, -0.35)
C_PANEL_SHADOW = _shade(C_BG_TOP, -0.55)


class PreferencesWindow:
    """Preferences window for Cristine settings."""

    def __init__(self, parent, prefs_callback=None, log_callback=None):
        self.parent = parent
        self.prefs_callback = prefs_callback
        self.log_callback = log_callback
        self.preferences = self._load_preferences()
        self.window = None
        self.vars = {}  # Store tk variables for tracking changes

    def _handle_close(self) -> None:
        """Close the preferences window and clear stale references."""
        w = self.window
        self.window = None
        try:
            if w is not None and w.winfo_exists():
                w.destroy()
        except tk.TclError:
            # Already destroyed.
            pass
        except Exception:
            pass

    def _load_preferences(self) -> dict:
        """Load preferences from JSON file."""
        if PREFS_PATH.exists():
            try:
                with open(PREFS_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[Prefs] Error loading preferences: {e}")
        
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
            "dream_desktop_organization": True,
            "dream_downloads_organization": True,
            "dream_max_execution_hours": 3,
            "interface_compact_mode": False,
            "interface_panel_telemetry": True,
            "interface_panel_logs": True,
            "interface_panel_memory": True,
            "interface_panel_context": True,
            "general_speech_mode": True,
            "general_auto_update": True,
            "advanced_debug_mode": False,
            "advanced_api_timeout": 30,
            "ai_personality_tone": "friendly",
            "ai_personality_verbosity": "balanced",
            "ai_personality_humor": "light",
            "ai_personality_style": "jarvis",
            # Startup / background
            "startup_run_on_boot": False,
            "background_tray_enabled": False,
            "background_start_minimized": False,
            # Automation (background-safe defaults)
            "automation_allow_ui": False,
            "automation_browser_headless": True,
            "automation_cmd_visible": False,
        }

    def _save_preferences(self) -> None:
        """Save preferences to JSON file."""
        PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(PREFS_PATH, "w", encoding="utf-8") as f:
                json.dump(self.preferences, f, indent=2)
            print("[Prefs] 💾 Preferences saved")
            
            # Notify parent of changes
            if self.prefs_callback:
                self.prefs_callback(self.preferences)
        except Exception as e:
            print(f"[Prefs] ⚠️ Error saving preferences: {e}")

    def open(self, section: str | None = None) -> None:
        """Open the preferences window."""
        if self.window is not None:
            try:
                if self.window.winfo_exists():
                    self.window.lift()
                    return
            except tk.TclError:
                pass
            except Exception:
                pass
            # Window was destroyed but reference remained.
            self.window = None

        self.window = tk.Toplevel(self.parent)
        self.window.title("CRISTINE PREFERENCES")
        self.window.geometry("780x720")
        self.window.resizable(True, True)
        self.window.configure(bg=C_BG_TOP)
        
        # Configure custom style
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", background=C_GLASS_BG, foreground=C_TEXT_PRI,
                       fieldbackground=C_GLASS_BG, borderwidth=0)
        style.configure("Treeview.Heading", background=C_DIM, foreground=C_TEXT_PRI,
                       borderwidth=1)
        
        # Main frame
        main_frame = tk.Frame(self.window, bg=C_BG_TOP)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Title
        title = tk.Label(main_frame, text="⚙️ PREFERENCES", fg=C_PRI, bg=C_BG_TOP,
                        font=("Courier", 14, "bold"))
        title.pack(pady=(0, 15))

        # Sidebar navigation + content pane (avoids cramped horizontal tabs).
        body = tk.Frame(main_frame, bg=C_BG_TOP)
        body.pack(fill="both", expand=True)

        # Depth: shadow -> border -> surface
        nav_shadow = tk.Frame(body, bg=C_PANEL_SHADOW)
        nav_shadow.pack(side="left", fill="y")
        nav_shadow.configure(width=172)
        nav_shadow.pack_propagate(False)

        nav_border = tk.Frame(nav_shadow, bg=C_GLASS_BORDER)
        nav_border.pack(fill="both", expand=True, padx=(0, 3), pady=(0, 3))
        nav = tk.Frame(nav_border, bg=C_GLASS_BG)
        nav.pack(fill="both", expand=True, padx=1, pady=1)

        # Top sheen highlight
        tk.Frame(nav, bg=C_GLASS_BG_L1, height=2).pack(fill="x")
        nav_inner = tk.Frame(nav, bg=C_GLASS_BG)
        nav_inner.pack(fill="both", expand=True)

        nav_title = tk.Label(nav_inner, text="SECTIONS", fg=C_SEC, bg=C_GLASS_BG, font=("Courier", 9, "bold"))
        nav_title.pack(anchor="w", padx=10, pady=(10, 6))
        tk.Frame(nav_inner, bg=C_GLASS_BORDER, height=1).pack(fill="x", padx=8, pady=(0, 10))

        content_shadow = tk.Frame(body, bg=C_PANEL_SHADOW)
        content_shadow.pack(side="left", fill="both", expand=True, padx=(10, 0))
        content_border = tk.Frame(content_shadow, bg=C_GLASS_BORDER)
        content_border.pack(fill="both", expand=True, padx=(0, 3), pady=(0, 3))
        content = tk.Frame(content_border, bg=C_GLASS_BG)
        content.pack(fill="both", expand=True, padx=1, pady=1)

        tk.Frame(content, bg=C_GLASS_BG_L1, height=2).pack(fill="x")
        content_inner = tk.Frame(content, bg=C_GLASS_BG)
        content_inner.pack(fill="both", expand=True)

        pages = {}
        nav_buttons = {}
        active_section = {"key": None}

        sections = [
            ("general", "General", self._build_general_tab),
            ("dream", "Dream Mode", self._build_dream_tab),
            ("interface", "Interface", self._build_interface_tab),
            ("advanced", "Advanced", self._build_advanced_tab),
            ("ai", "AI Personality", self._build_ai_personality_tab),
            ("profile", "User Profile", self._build_user_profile_tab),
            ("voice", "Voice Commands", self._build_voice_commands_tab),
        ]

        for key, _label, build_fn in sections:
            page = tk.Frame(content_inner, bg=C_GLASS_BG)
            pages[key] = page
            build_fn(page)

        def _style_nav_button(btn: tk.Button, *, active: bool, hover: bool = False) -> None:
            if active:
                btn.config(bg=C_DIMMER, fg=C_PRI)
            elif hover:
                btn.config(bg=C_GLASS_BG_L1, fg=C_TEXT_PRI)
            else:
                btn.config(bg=C_GLASS_BG, fg=C_TEXT_PRI)

        def show_section(key: str) -> None:
            active_section["key"] = key
            for k, p in pages.items():
                p.pack_forget()
            for k, b in nav_buttons.items():
                _style_nav_button(b, active=(k == key), hover=False)
            pages[key].pack(fill="both", expand=True)

        for key, label, _build_fn in sections:
            btn = tk.Button(
                nav_inner,
                text=label.upper(),
                command=lambda k=key: show_section(k),
                bg=C_GLASS_BG,
                fg=C_TEXT_PRI,
                activebackground=C_DIM,
                activeforeground=C_PRI,
                font=("Courier", 9, "bold"),
                borderwidth=0,
                padx=10,
                pady=8,
                anchor="w",
                cursor="hand2",
            )
            btn.pack(fill="x", padx=8, pady=3)
            btn.bind("<Enter>", lambda _e, b=btn, k=key: _style_nav_button(b, active=(active_section["key"] == k), hover=(active_section["key"] != k)))
            btn.bind("<Leave>", lambda _e, b=btn, k=key: _style_nav_button(b, active=(active_section["key"] == k), hover=False))
            nav_buttons[key] = btn

        # Default view (or requested jump)
        target = (section or "general").strip().lower()
        if target not in pages:
            target = "general"
        show_section(target)

        # Button frame
        button_frame = tk.Frame(main_frame, bg=C_BG_TOP)
        button_frame.pack(fill="x", pady=(10, 0))

        save_btn = tk.Button(button_frame, text="💾 SAVE", command=self._handle_save,
                            bg=C_ACC, fg=C_BG_TOP, font=("Courier", 10, "bold"),
                            padx=20, pady=8, borderwidth=0, cursor="hand2")
        save_btn.pack(side="left", padx=(0, 5))

        cancel_btn = tk.Button(button_frame, text="✕ CLOSE", command=self._handle_close,
                              bg=C_DIM, fg=C_TEXT_PRI, font=("Courier", 10, "bold"),
                              padx=20, pady=8, borderwidth=0, cursor="hand2")
        cancel_btn.pack(side="left")

        # Hover polish: small lightness bump makes controls feel interactive.
        def _hover(btn: tk.Button, *, on_bg: str, off_bg: str, on_fg: str | None = None, off_fg: str | None = None) -> None:
            try:
                btn.bind("<Enter>", lambda _e: btn.config(bg=on_bg, fg=(on_fg if on_fg is not None else btn.cget("fg"))))
                btn.bind("<Leave>", lambda _e: btn.config(bg=off_bg, fg=(off_fg if off_fg is not None else btn.cget("fg"))))
            except Exception:
                pass

        _hover(save_btn, on_bg=_shade(C_ACC, 0.08), off_bg=C_ACC, on_fg=C_BG_TOP, off_fg=C_BG_TOP)
        _hover(cancel_btn, on_bg=_shade(C_DIM, 0.10), off_bg=C_DIM, on_fg=C_TEXT_PRI, off_fg=C_TEXT_PRI)

        self.window.protocol("WM_DELETE_WINDOW", self._handle_close)

    def _log(self, msg: str) -> None:
        """Log to parent UI if available, else stdout."""
        try:
            if callable(self.log_callback):
                self.log_callback(msg, tag="sys")
                return
        except Exception:
            pass
        try:
            print(f"[Prefs] {msg}")
        except Exception:
            pass

    def _ui_set(self, var: tk.StringVar, value: str) -> None:
        """Safely set a StringVar from any thread."""
        if self.window and self.window.winfo_exists():
            self.window.after(0, lambda: var.set(value))

    def _ui_set_btn_state(self, btn: tk.Button, state: str) -> None:
        if self.window and self.window.winfo_exists():
            self.window.after(0, lambda: btn.config(state=state))

    def _build_integrations_tab(self, parent) -> None:
        """Build Integrations tab (currently unused)."""
        frame = tk.Frame(parent, bg=C_GLASS_BG)
        frame.pack(fill="both", expand=True, padx=15, pady=15)

        box = tk.LabelFrame(
            frame,
            text="Integrations",
            bg=C_GLASS_BG,
            fg=C_PRI,
            font=("Courier", 10, "bold"),
            borderwidth=1,
            padx=10,
            pady=10,
        )
        box.pack(fill="x", pady=(0, 10))

        tk.Label(
            box,
            text="No integrations are enabled in this build.",
            bg=C_GLASS_BG,
            fg=C_TEXT_SEC,
            font=("Courier", 9),
            justify="left",
        ).pack(anchor="w", pady=(2, 4))

    def _build_general_tab(self, parent) -> None:
        """Build General preferences tab."""
        frame = tk.Frame(parent, bg=C_GLASS_BG)
        frame.pack(fill="both", expand=True, padx=15, pady=15)

        # Speech Mode
        self.vars["general_speech_mode"] = tk.BooleanVar(
            value=self.preferences.get("general_speech_mode", True)
        )
        chk = tk.Checkbutton(frame, text="Enable Speech Input (Microphone)",
                            variable=self.vars["general_speech_mode"],
                            bg=C_GLASS_BG, fg=C_TEXT_PRI, selectcolor=C_DIM,
                            font=("Courier", 10), activebackground=C_DIM,
                            activeforeground=C_PRI)
        chk.pack(anchor="w", pady=10)

        # Auto Update
        self.vars["general_auto_update"] = tk.BooleanVar(
            value=self.preferences.get("general_auto_update", True)
        )
        chk = tk.Checkbutton(frame, text="Enable Auto-Updates",
                            variable=self.vars["general_auto_update"],
                            bg=C_GLASS_BG, fg=C_TEXT_PRI, selectcolor=C_DIM,
                            font=("Courier", 10), activebackground=C_DIM,
                            activeforeground=C_PRI)
        chk.pack(anchor="w", pady=10)

        # Startup & background behavior (Windows-focused; safely no-ops elsewhere)
        startup_box = tk.LabelFrame(
            frame,
            text="Startup & Background",
            bg=C_GLASS_BG,
            fg=C_PRI,
            font=("Courier", 9, "bold"),
            borderwidth=1,
            padx=10,
            pady=10,
        )
        startup_box.pack(fill="x", pady=(15, 5))

        self.vars["startup_run_on_boot"] = tk.BooleanVar(
            value=self.preferences.get("startup_run_on_boot", False)
        )
        chk = tk.Checkbutton(
            startup_box,
            text="Start Cristine on system startup",
            variable=self.vars["startup_run_on_boot"],
            bg=C_GLASS_BG,
            fg=C_TEXT_PRI,
            selectcolor=C_DIM,
            font=("Courier", 10),
            activebackground=C_DIM,
            activeforeground=C_PRI,
        )
        chk.pack(anchor="w", pady=6)

        self.vars["background_tray_enabled"] = tk.BooleanVar(
            value=self.preferences.get("background_tray_enabled", False)
        )
        chk = tk.Checkbutton(
            startup_box,
            text="Enable tray icon (run in background when closed)",
            variable=self.vars["background_tray_enabled"],
            bg=C_GLASS_BG,
            fg=C_TEXT_PRI,
            selectcolor=C_DIM,
            font=("Courier", 10),
            activebackground=C_DIM,
            activeforeground=C_PRI,
        )
        chk.pack(anchor="w", pady=6)

        self.vars["background_start_minimized"] = tk.BooleanVar(
            value=self.preferences.get("background_start_minimized", False)
        )
        chk = tk.Checkbutton(
            startup_box,
            text="Start minimized to tray (when tray icon is enabled)",
            variable=self.vars["background_start_minimized"],
            bg=C_GLASS_BG,
            fg=C_TEXT_SEC,
            selectcolor=C_DIM,
            font=("Courier", 9),
            activebackground=C_DIM,
            activeforeground=C_PRI,
        )
        chk.pack(anchor="w", pady=6)

        # Info label
        info_lbl = tk.Label(frame, text="General settings for Cristine behavior and input modes.",
                           bg=C_GLASS_BG, fg=C_TEXT_SEC, font=("Courier", 9))
        info_lbl.pack(anchor="w", pady=(20, 0))

    def _build_dream_tab(self, parent) -> None:
        """Build Dream Mode preferences tab."""
        frame = tk.Frame(parent, bg=C_GLASS_BG)
        frame.pack(fill="both", expand=True, padx=15, pady=15)

        # Dream Mode Enabled
        self.vars["dream_mode_enabled"] = tk.BooleanVar(
            value=self.preferences.get("dream_mode_enabled", False)
        )
        header = tk.Checkbutton(frame, text="🌙 Enable Dream Mode",
                               variable=self.vars["dream_mode_enabled"],
                               bg=C_GLASS_BG, fg=C_ACC, selectcolor=C_DIM,
                               font=("Courier", 11, "bold"), activebackground=C_DIM,
                               activeforeground=C_ACC)
        header.pack(anchor="w", pady=(0, 15))

        # Sub-options frame
        subframe = tk.Frame(frame, bg=C_DIMMER, relief="solid", borderwidth=1)
        subframe.pack(fill="x", pady=(0, 10))

        inner = tk.Frame(subframe, bg=C_DIMMER)
        inner.pack(fill="both", expand=True, padx=10, pady=10)

        # File Organization
        self.vars["dream_file_organization"] = tk.BooleanVar(
            value=self.preferences.get("dream_file_organization", True)
        )
        chk = tk.Checkbutton(inner, text="📁 File Organization (Desktop, Downloads)",
                            variable=self.vars["dream_file_organization"],
                            bg=C_DIMMER, fg=C_TEXT_PRI, selectcolor=C_DIM,
                            font=("Courier", 9), activebackground=C_DIMMER,
                            activeforeground=C_PRI)
        chk.pack(anchor="w", pady=5)

        # Knowledge Graph Improvement
        self.vars["dream_knowledge_graph_improvement"] = tk.BooleanVar(
            value=self.preferences.get("dream_knowledge_graph_improvement", True)
        )
        chk = tk.Checkbutton(inner, text="🧠 Knowledge Graph Optimization",
                            variable=self.vars["dream_knowledge_graph_improvement"],
                            bg=C_DIMMER, fg=C_TEXT_PRI, selectcolor=C_DIM,
                            font=("Courier", 9), activebackground=C_DIMMER,
                            activeforeground=C_PRI)
        chk.pack(anchor="w", pady=5)

        # Self Learning
        self.vars["dream_self_learning"] = tk.BooleanVar(
            value=self.preferences.get("dream_self_learning", False)
        )
        chk = tk.Checkbutton(inner, text="🔍 Self Learning (Online Research)",
                            variable=self.vars["dream_self_learning"],
                            bg=C_DIMMER, fg=C_TEXT_PRI, selectcolor=C_DIM,
                            font=("Courier", 9), activebackground=C_DIMMER,
                            activeforeground=C_PRI)
        chk.pack(anchor="w", pady=5)

        # Time scheduling frame
        sched_frame = tk.LabelFrame(frame, text="⏰ Night Schedule",
                                   bg=C_GLASS_BG, fg=C_PRI, font=("Courier", 9, "bold"),
                                   borderwidth=1, padx=10, pady=10)
        sched_frame.pack(fill="x", pady=10)

        # Start Hour
        start_frame = tk.Frame(sched_frame, bg=C_GLASS_BG)
        start_frame.pack(fill="x", pady=5)
        tk.Label(start_frame, text="Start Hour (24h):", bg=C_GLASS_BG, fg=C_TEXT_PRI,
                font=("Courier", 9)).pack(side="left")
        self.vars["dream_start_hour"] = tk.IntVar(
            value=self.preferences.get("dream_start_hour", 2)
        )
        spinbox = tk.Spinbox(start_frame, from_=0, to=23, textvariable=self.vars["dream_start_hour"],
                            bg=C_DIMMER, fg=C_TEXT_PRI, width=5, font=("Courier", 10))
        spinbox.pack(side="left", padx=(10, 0))

        # End Hour
        end_frame = tk.Frame(sched_frame, bg=C_GLASS_BG)
        end_frame.pack(fill="x", pady=5)
        tk.Label(end_frame, text="End Hour (24h):  ", bg=C_GLASS_BG, fg=C_TEXT_PRI,
                font=("Courier", 9)).pack(side="left")
        self.vars["dream_end_hour"] = tk.IntVar(
            value=self.preferences.get("dream_end_hour", 5)
        )
        spinbox = tk.Spinbox(end_frame, from_=0, to=23, textvariable=self.vars["dream_end_hour"],
                            bg=C_DIMMER, fg=C_TEXT_PRI, width=5, font=("Courier", 10))
        spinbox.pack(side="left", padx=(10, 0))

        # Max Execution Hours
        max_frame = tk.Frame(sched_frame, bg=C_GLASS_BG)
        max_frame.pack(fill="x", pady=5)
        tk.Label(max_frame, text="Max Duration (hours):", bg=C_GLASS_BG, fg=C_TEXT_PRI,
                font=("Courier", 9)).pack(side="left")
        self.vars["dream_max_execution_hours"] = tk.IntVar(
            value=self.preferences.get("dream_max_execution_hours", 3)
        )
        spinbox = tk.Spinbox(max_frame, from_=1, to=12, textvariable=self.vars["dream_max_execution_hours"],
                            bg=C_DIMMER, fg=C_TEXT_PRI, width=5, font=("Courier", 10))
        spinbox.pack(side="left", padx=(10, 0))

    def _build_interface_tab(self, parent) -> None:
        """Build Interface preferences tab."""
        frame = tk.Frame(parent, bg=C_GLASS_BG)
        frame.pack(fill="both", expand=True, padx=15, pady=15)

        # Compact Mode
        self.vars["interface_compact_mode"] = tk.BooleanVar(
            value=self.preferences.get("interface_compact_mode", False)
        )
        chk = tk.Checkbutton(frame, text="Compact Mode (minimized HUD)",
                            variable=self.vars["interface_compact_mode"],
                            bg=C_GLASS_BG, fg=C_TEXT_PRI, selectcolor=C_DIM,
                            font=("Courier", 10), activebackground=C_DIM,
                            activeforeground=C_PRI)
        chk.pack(anchor="w", pady=10)

    def _build_advanced_tab(self, parent) -> None:
        """Build Advanced preferences tab."""
        frame = tk.Frame(parent, bg=C_GLASS_BG)
        frame.pack(fill="both", expand=True, padx=15, pady=15)

        # Debug Mode
        self.vars["advanced_debug_mode"] = tk.BooleanVar(
            value=self.preferences.get("advanced_debug_mode", False)
        )
        chk = tk.Checkbutton(frame, text="Enable Debug Mode (verbose logging)",
                            variable=self.vars["advanced_debug_mode"],
                            bg=C_GLASS_BG, fg=C_WARN, selectcolor=C_DIM,
                            font=("Courier", 10), activebackground=C_DIM,
                            activeforeground=C_WARN)
        chk.pack(anchor="w", pady=10)

        # API Timeout
        timeout_frame = tk.Frame(frame, bg=C_GLASS_BG)
        timeout_frame.pack(fill="x", pady=15)
        tk.Label(timeout_frame, text="API Timeout (seconds):", bg=C_GLASS_BG, fg=C_TEXT_PRI,
                font=("Courier", 10)).pack(side="left")
        self.vars["advanced_api_timeout"] = tk.IntVar(
            value=self.preferences.get("advanced_api_timeout", 30)
        )
        spinbox = tk.Spinbox(timeout_frame, from_=5, to=120, textvariable=self.vars["advanced_api_timeout"],
                            bg=C_DIMMER, fg=C_TEXT_PRI, width=5, font=("Courier", 10))
        spinbox.pack(side="left", padx=(10, 0))

        # Automation (background-safe defaults)
        tk.Frame(frame, bg=C_GLASS_BORDER, height=1).pack(fill="x", pady=(22, 14))
        tk.Label(frame, text="AUTOMATION", bg=C_GLASS_BG, fg=C_PRI, font=("Courier", 10, "bold")).pack(anchor="w")

        self.vars["automation_allow_ui"] = tk.BooleanVar(
            value=self.preferences.get("automation_allow_ui", False)
        )
        chk = tk.Checkbutton(
            frame,
            text="Allow on-screen automation (mouse/keyboard control)",
            variable=self.vars["automation_allow_ui"],
            bg=C_GLASS_BG,
            fg=C_WARN,
            selectcolor=C_DIM,
            font=("Courier", 10),
            activebackground=C_DIM,
            activeforeground=C_WARN,
        )
        chk.pack(anchor="w", pady=(10, 4))
        tk.Label(
            frame,
            text="Keeping this OFF lets Cristine run tools in the background without stealing focus.",
            bg=C_GLASS_BG,
            fg=C_TEXT_SEC,
            font=("Courier", 9),
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        self.vars["automation_browser_headless"] = tk.BooleanVar(
            value=self.preferences.get("automation_browser_headless", True)
        )
        chk = tk.Checkbutton(
            frame,
            text="Prefer headless browser automation (no visible browser window)",
            variable=self.vars["automation_browser_headless"],
            bg=C_GLASS_BG,
            fg=C_TEXT_PRI,
            selectcolor=C_DIM,
            font=("Courier", 10),
            activebackground=C_DIM,
            activeforeground=C_PRI,
        )
        chk.pack(anchor="w", pady=6)

        self.vars["automation_cmd_visible"] = tk.BooleanVar(
            value=self.preferences.get("automation_cmd_visible", False)
        )
        chk = tk.Checkbutton(
            frame,
            text="Open visible terminal windows for CMD tool runs",
            variable=self.vars["automation_cmd_visible"],
            bg=C_GLASS_BG,
            fg=C_TEXT_PRI,
            selectcolor=C_DIM,
            font=("Courier", 10),
            activebackground=C_DIM,
            activeforeground=C_PRI,
        )
        chk.pack(anchor="w", pady=6)

        # Info label
        info_lbl = tk.Label(frame, text="⚠️ Advanced settings affect system behavior.\nModify only if you know what you're doing.",
                           bg=C_GLASS_BG, fg=C_WARN, font=("Courier", 9),
                           justify="left")
        info_lbl.pack(anchor="w", pady=(26, 0))

    def _build_ai_personality_tab(self, parent) -> None:
        """Build AI Personality preferences tab with scrolling support."""
        # Create canvas with scrollbar for scrollable content
        canvas = tk.Canvas(parent, bg=C_GLASS_BG, highlightthickness=0, borderwidth=0)
        scrollbar = tk.Scrollbar(parent, bg=C_DIM, troughcolor=C_DIMMER, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=C_GLASS_BG)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Enable mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        canvas.pack(side="left", fill="both", expand=True, padx=(15, 0), pady=15)
        scrollbar.pack(side="right", fill="y", padx=(0, 15), pady=15)
        
        # Title
        title = tk.Label(scrollable_frame, text="🤖 AI Personality Settings", fg=C_PRI, bg=C_GLASS_BG,
                        font=("Courier", 11, "bold"))
        title.pack(anchor="w", pady=(0, 15))
        
        # Description
        desc = tk.Label(scrollable_frame, text="Customize how Cristine communicates with you.",
                       fg=C_TEXT_SEC, bg=C_GLASS_BG, font=("Courier", 9))
        desc.pack(anchor="w", pady=(0, 20))
        
        # Tone Selection
        tone_frame = tk.Frame(scrollable_frame, bg=C_GLASS_BG)
        tone_frame.pack(fill="x", pady=(0, 15))
        tk.Label(tone_frame, text="Tone", bg=C_GLASS_BG, fg=C_PRI,
                font=("Courier", 10, "bold")).pack(anchor="w", pady=(0, 5))
        
        tone_opts = ["Professional", "Friendly", "Casual", "Technical"]
        self.vars["ai_personality_tone"] = tk.StringVar(
            value=self.preferences.get("ai_personality_tone", "friendly").capitalize()
        )
        for tone in tone_opts:
            rb = tk.Radiobutton(tone_frame, text=tone, variable=self.vars["ai_personality_tone"],
                              value=tone, bg=C_GLASS_BG, fg=C_TEXT_PRI, selectcolor=C_DIM,
                              font=("Courier", 9), activebackground=C_DIM, activeforeground=C_PRI)
            rb.pack(anchor="w", pady=3)
        
        # Verbosity Selection
        verbosity_frame = tk.Frame(scrollable_frame, bg=C_GLASS_BG)
        verbosity_frame.pack(fill="x", pady=(0, 15))
        tk.Label(verbosity_frame, text="Verbosity (Response Length)", bg=C_GLASS_BG, fg=C_PRI,
                font=("Courier", 10, "bold")).pack(anchor="w", pady=(0, 5))
        
        verbosity_opts = ["Short", "Balanced", "Detailed"]
        self.vars["ai_personality_verbosity"] = tk.StringVar(
            value=self.preferences.get("ai_personality_verbosity", "balanced").capitalize()
        )
        for verb in verbosity_opts:
            rb = tk.Radiobutton(verbosity_frame, text=verb, variable=self.vars["ai_personality_verbosity"],
                              value=verb, bg=C_GLASS_BG, fg=C_TEXT_PRI, selectcolor=C_DIM,
                              font=("Courier", 9), activebackground=C_DIM, activeforeground=C_PRI)
            rb.pack(anchor="w", pady=3)
        
        # Humor Level Selection
        humor_frame = tk.Frame(scrollable_frame, bg=C_GLASS_BG)
        humor_frame.pack(fill="x", pady=(0, 15))
        tk.Label(humor_frame, text="Humor Level", bg=C_GLASS_BG, fg=C_PRI,
                font=("Courier", 10, "bold")).pack(anchor="w", pady=(0, 5))
        
        humor_opts = ["None", "Light", "Playful"]
        self.vars["ai_personality_humor"] = tk.StringVar(
            value=self.preferences.get("ai_personality_humor", "light").capitalize()
        )
        for humor in humor_opts:
            rb = tk.Radiobutton(humor_frame, text=humor, variable=self.vars["ai_personality_humor"],
                              value=humor, bg=C_GLASS_BG, fg=C_TEXT_PRI, selectcolor=C_DIM,
                              font=("Courier", 9), activebackground=C_DIM, activeforeground=C_PRI)
            rb.pack(anchor="w", pady=3)
        
        # Assistant Style Selection
        style_frame = tk.Frame(scrollable_frame, bg=C_GLASS_BG)
        style_frame.pack(fill="x", pady=(0, 15))
        tk.Label(style_frame, text="Assistant Style", bg=C_GLASS_BG, fg=C_PRI,
                font=("Courier", 10, "bold")).pack(anchor="w", pady=(0, 5))
        
        style_opts = ["Neutral AI", "Jarvis-like", "Friendly Companion", "Technical Expert"]
        style_values = ["neutral", "jarvis", "companion", "technical"]
        current_style = self.preferences.get("ai_personality_style", "jarvis")
        current_display = next((opt for opt, val in zip(style_opts, style_values) if val == current_style), "Jarvis-like")
        
        self.vars["ai_personality_style"] = tk.StringVar(value=current_display)
        for style, value in zip(style_opts, style_values):
            rb = tk.Radiobutton(style_frame, text=style, variable=self.vars["ai_personality_style"],
                              value=style, bg=C_GLASS_BG, fg=C_TEXT_PRI, selectcolor=C_DIM,
                              font=("Courier", 9), activebackground=C_DIM, activeforeground=C_PRI)
            rb.pack(anchor="w", pady=3)
        
        # Info label
        info_lbl = tk.Label(scrollable_frame, text="💡 Personality settings only affect response style, not system behavior.\nChanges apply immediately.",
                           bg=C_GLASS_BG, fg=C_TEXT_SEC, font=("Courier", 8), justify="left")
        info_lbl.pack(anchor="w", pady=(20, 0))

    def _build_user_profile_tab(self, parent) -> None:
        """Build User Profile preferences tab."""
        frame = tk.Frame(parent, bg=C_GLASS_BG)
        frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Title
        title = tk.Label(frame, text="Personal Data Management", fg=C_PRI, bg=C_GLASS_BG,
                        font=("Courier", 11, "bold"))
        title.pack(anchor="w", pady=(0, 10))
        
        # Description
        desc = tk.Label(frame, text="Import personal data from other AI assistants\nto help Cristine understand you better.",
                       fg=C_TEXT_SEC, bg=C_GLASS_BG, font=("Courier", 9), justify="left")
        desc.pack(anchor="w", pady=(0, 15))
        
        # Get profile manager
        profile_manager = get_profile_manager()
        
        # Button frame 1
        btn_frame1 = tk.Frame(frame, bg=C_GLASS_BG)
        btn_frame1.pack(fill="x", pady=5)
        
        import_btn = tk.Button(btn_frame1, text="📥 IMPORT DATA FROM ANOTHER AI",
                              command=lambda: self._open_import_dialog(profile_manager),
                              bg=C_DIM, fg=C_ACC, font=("Courier", 9, "bold"),
                              borderwidth=0, padx=15, pady=8, cursor="hand2",
                              activebackground=C_ACC, activeforeground=C_BG_TOP)
        import_btn.pack(fill="x")
        
        # Button frame 2
        btn_frame2 = tk.Frame(frame, bg=C_GLASS_BG)
        btn_frame2.pack(fill="x", pady=5)
        
        view_btn = tk.Button(btn_frame2, text="👁️ VIEW STORED DATA",
                            command=lambda: self._open_data_viewer(profile_manager),
                            bg=C_DIM, fg=C_PRI, font=("Courier", 9, "bold"),
                            borderwidth=0, padx=15, pady=8, cursor="hand2",
                            activebackground=C_PRI, activeforeground=C_BG_TOP)
        view_btn.pack(fill="x")
        
        # Info section
        info_frame = tk.LabelFrame(frame, text="ℹ️ Data Privacy", bg=C_GLASS_BG, 
                                  fg=C_TEXT_SEC, font=("Courier", 9, "bold"),
                                  borderwidth=1, padx=10, pady=10)
        info_frame.pack(fill="x", pady=(20, 0))
        
        privacy_text = """✓ All personal data is stored locally
✓ Data is never uploaded to external servers
✓ Data is not automatically used in web searches
✓ You have full control to view, edit, or delete"""
        
        info_label = tk.Label(info_frame, text=privacy_text, fg=C_TEXT_PRI, bg=C_GLASS_BG,
                             font=("Courier", 8), justify="left")
        info_label.pack(anchor="w")
    
    def _build_voice_commands_tab(self, parent) -> None:
        """Build Voice Commands preferences tab."""
        from core.voice_commands import get_voice_command_manager
        
        frame = tk.Frame(parent, bg=C_GLASS_BG)
        frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Title
        title = tk.Label(frame, text="🎙️ Custom Voice Commands", fg=C_PRI, bg=C_GLASS_BG,
                        font=("Courier", 11, "bold"))
        title.pack(anchor="w", pady=(0, 10))
        
        # Description
        desc = tk.Label(frame, text="Define voice commands to perform actions.\nExamples: 'open spotify', 'minimize', 'clear logs'",
                       fg=C_TEXT_SEC, bg=C_GLASS_BG, font=("Courier", 9), justify="left")
        desc.pack(anchor="w", pady=(0, 15))
        
        # Get voice command manager
        vcm = get_voice_command_manager()
        
        # Add command frame
        cmd_frame = tk.LabelFrame(frame, text="➕ Add New Command", bg=C_GLASS_BG,
                                 fg=C_PRI, font=("Courier", 10, "bold"),
                                 borderwidth=1, padx=10, pady=10)
        cmd_frame.pack(fill="x", pady=(0, 15))
        
        # Phrase input
        tk.Label(cmd_frame, text="Voice Phrase:", bg=C_GLASS_BG, fg=C_TEXT_PRI,
                font=("Courier", 9)).pack(anchor="w", pady=(0, 3))
        phrase_entry = tk.Entry(cmd_frame, bg=C_DIMMER, fg=C_TEXT_PRI, insertbackground=C_PRI,
                               font=("Courier", 9), borderwidth=0, relief="solid")
        phrase_entry.pack(fill="x", pady=(0, 10))
        
        # Action type selection
        tk.Label(cmd_frame, text="Action Type:", bg=C_GLASS_BG, fg=C_TEXT_PRI,
                font=("Courier", 9)).pack(anchor="w", pady=(0, 3))
        action_var = tk.StringVar(value="open_app")
        action_frame = tk.Frame(cmd_frame, bg=C_GLASS_BG)
        action_frame.pack(fill="x", pady=(0, 10))
        
        for action in ["open_app", "run_function", "run_safe_script"]:
            tk.Radiobutton(action_frame, text=action, variable=action_var, value=action,
                          bg=C_GLASS_BG, fg=C_TEXT_PRI, selectcolor=C_DIM,
                          font=("Courier", 9), activebackground=C_DIM, activeforeground=C_PRI
                          ).pack(anchor="w", pady=2)
        
        # Target input
        tk.Label(cmd_frame, text="Target (app name, function, or script):", bg=C_GLASS_BG, fg=C_TEXT_PRI,
                font=("Courier", 9)).pack(anchor="w", pady=(0, 3))
        target_entry = tk.Entry(cmd_frame, bg=C_DIMMER, fg=C_TEXT_PRI, insertbackground=C_PRI,
                               font=("Courier", 9), borderwidth=0, relief="solid")
        target_entry.pack(fill="x", pady=(0, 10))
        
        # Safe apps/functions info
        info_text = "Safe apps: " + ", ".join(vcm.get_safe_app_list()[:3]) + "...\n"
        info_text += "Safe functions: " + ", ".join(vcm.get_safe_function_list()[:3]) + "..."
        info_lbl = tk.Label(cmd_frame, text=info_text, bg=C_GLASS_BG, fg=C_TEXT_SEC,
                           font=("Courier", 8), justify="left")
        info_lbl.pack(anchor="w", pady=(5, 0))
        
        # Add command button
        def add_command():
            phrase = phrase_entry.get()
            action = action_var.get()
            target = target_entry.get()
            
            if vcm.add_command(phrase, action, target):
                phrase_entry.delete(0, tk.END)
                target_entry.delete(0, tk.END)
                refresh_command_list()
                status_lbl.config(text=f"✓ Command '{phrase}' added!", fg=C_SUCCESS)
            else:
                status_lbl.config(text="✗ Failed to add command", fg=C_WARN)
        
        add_btn = tk.Button(cmd_frame, text="✓ ADD COMMAND", command=add_command,
                           bg=C_ACC, fg=C_BG_TOP, font=("Courier", 9, "bold"),
                           borderwidth=0, padx=15, pady=6, cursor="hand2",
                           activebackground=C_PRI, activeforeground=C_BG_TOP)
        add_btn.pack(fill="x", pady=(10, 0))
        
        # Status label
        status_lbl = tk.Label(frame, text="", bg=C_GLASS_BG, fg=C_SUCCESS,
                             font=("Courier", 8))
        status_lbl.pack(anchor="w", pady=(5, 10))
        
        # Commands list frame
        list_frame = tk.LabelFrame(frame, text="📋 Your Commands", bg=C_GLASS_BG,
                                  fg=C_PRI, font=("Courier", 10, "bold"),
                                  borderwidth=1, padx=10, pady=10)
        list_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        # Listbox with scrollbar
        scrollbar = tk.Scrollbar(list_frame, bg=C_DIM, troughcolor=C_DIMMER)
        scrollbar.pack(side="right", fill="y")
        
        cmd_listbox = tk.Listbox(list_frame, bg=C_DIMMER, fg=C_TEXT_PRI,
                                selectbackground=C_ACC, selectforeground=C_BG_TOP,
                                font=("Courier", 9), borderwidth=0,
                                yscrollcommand=scrollbar.set)
        cmd_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=cmd_listbox.yview)
        
        # Refresh function
        def refresh_command_list():
            cmd_listbox.delete(0, tk.END)
            commands = vcm.get_all_commands()
            for cmd in commands:
                text = f"  '{cmd['phrase']}' → {cmd['action']}: {cmd['target']}"
                cmd_listbox.insert(tk.END, text)
        
        refresh_command_list()
        
        # Delete button frame
        del_frame = tk.Frame(list_frame, bg=C_GLASS_BG)
        del_frame.pack(fill="x", pady=(10, 0))
        
        def delete_selected():
            selection = cmd_listbox.curselection()
            if selection:
                commands = vcm.get_all_commands()
                phrase = commands[selection[0]]["phrase"]
                if vcm.delete_command(phrase):
                    status_lbl.config(text=f"✓ Command '{phrase}' deleted!", fg=C_SUCCESS)
                    refresh_command_list()
                else:
                    status_lbl.config(text="✗ Failed to delete command", fg=C_WARN)
        
        delete_btn = tk.Button(del_frame, text="🗑️ DELETE SELECTED", command=delete_selected,
                              bg=C_DIM, fg=C_WARN, font=("Courier", 9, "bold"),
                              borderwidth=0, padx=15, pady=6, cursor="hand2",
                              activebackground=C_WARN, activeforeground=C_BG_TOP)
        delete_btn.pack(fill="x")
    
    def _open_import_dialog(self, profile_manager):
        """Open the import dialog"""
        show_import_dialog(self.window, profile_manager)
    
    def _open_data_viewer(self, profile_manager):
        """Open the data viewer"""
        show_data_viewer(self.window, profile_manager)

    def _handle_save(self) -> None:
        """Save all preferences from UI variables."""
        for key, var in self.vars.items():
            if isinstance(var, tk.BooleanVar):
                self.preferences[key] = var.get()
            elif isinstance(var, tk.IntVar):
                self.preferences[key] = var.get()
            elif isinstance(var, tk.StringVar):
                value = var.get()
                # Normalize personality settings to lowercase
                if key.startswith("ai_personality_"):
                    if key == "ai_personality_style":
                        # Convert display names back to values
                        style_map = {"Neutral AI": "neutral", "Jarvis-like": "jarvis", 
                                   "Friendly Companion": "companion", "Technical Expert": "technical"}
                        value = style_map.get(value, "jarvis")
                    else:
                        value = value.lower()
                self.preferences[key] = value

        self._save_preferences()
        
        # Close window after save
        if self.window:
            self.window.destroy()

