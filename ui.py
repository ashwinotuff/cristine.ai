import os, json, time, math, random, threading
import tkinter as tk
from collections import deque
from PIL import Image, ImageTk, ImageDraw
import sys
from pathlib import Path
import psutil
from actions.context_monitor import monitor as context_monitor
from threading import Event
from ui.preferences_window import PreferencesWindow
from memory.task_manager import get_task_manager
from agent.task_queue import get_queue

def get_base_dir():
    if getattr(sys, "frozen", False): return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

SYSTEM_NAME, MODEL_BADGE = "CRISTINE", "Cristine"
# Holographic Glass Theme Colors
C_BG_TOP, C_BG_BOT = "#03060A", "#0A1220"
C_PRI, C_SEC, C_ACC = "#4FD1FF", "#A66CFF", "#52FFA8"
C_GLASS_BG = "#0D1B2E"  # Approximated glass background
C_GLASS_BORDER = "#3A5A7E" # Approximated glass border
C_TEXT_PRI, C_TEXT_SEC = "#CBEFFF", "#7FAAC9"
C_WARN, C_ERR, C_SUCCESS = "#FFB020", "#FF4A6E", "#52FFA8"
C_DIM, C_DIMMER = "#1B2D44", "#0D1520"

# ============================================================================
# EXPANDABLE PANEL SYSTEM
# ============================================================================

class ExpandablePanel:
    """Base class for animated expandable panels with smooth transitions."""

    def __init__(self, panel_id, x, y, collapsed_w, collapsed_h, expanded_w, expanded_h,
                 title="PANEL", theme_color=C_SEC, expanded_renderer=None, collapsed_renderer=None):
        self.panel_id = panel_id
        self.x = x
        self.y = y
        self.collapsed_w = collapsed_w
        self.collapsed_h = collapsed_h
        self.expanded_w = expanded_w
        self.expanded_h = expanded_h

        self.current_x = x
        self.current_y = y
        self.current_w = collapsed_w
        self.current_h = collapsed_h

        self.is_expanded = False
        self.anim_progress = 1.0
        self.anim_target = None
        self.anim_speed = 0.033
        self.alpha = 1.0

        self.title = title
        self.theme_color = theme_color
        self.expanded_renderer = expanded_renderer
        self.collapsed_renderer = collapsed_renderer

        self.is_dragging = False
        self.drag_offset_x = 0
        self.drag_offset_y = 0
        self.canvas_items = []
        self.close_items = []
        self.close_button_rect = None
        self.text_item = None  # Reference to the content text canvas item

    def toggle(self, target_expanded=None):
        """Toggle panel state with animation."""
        if target_expanded is None:
            self.anim_target = not self.is_expanded
        else:
            self.anim_target = target_expanded
        self.anim_progress = 0.0

    def update(self):
        """Update animation state. Call each frame from main loop."""
        if self.anim_target is None:
            return

        # Advance animation
        self.anim_progress += self.anim_speed
        if self.anim_progress >= 1.0:
            self.anim_progress = 1.0
            # Finalize state to target
            if self.anim_target is not None:
                self.is_expanded = self.anim_target
            self.anim_target = None

        # Easing: ease-out cubic
        t = 1.0 - pow(1.0 - self.anim_progress, 3)

        # Interpolate geometry
        start_w = self.collapsed_w if self.anim_target else self.expanded_w
        start_h = self.collapsed_h if self.anim_target else self.expanded_h
        target_w = self.expanded_w if self.anim_target else self.collapsed_w
        target_h = self.expanded_h if self.anim_target else self.collapsed_h

        self.current_w = start_w + (target_w - start_w) * t
        self.current_h = start_h + (target_h - start_h) * t

        # Position: Keep top-left anchor stable during expansion (grows right and down)
        # If we want centered expansion, we'd adjust x,y too. For now, anchor top-left.
        # self.current_x = self.x  # unchanged
        # self.current_y = self.y  # unchanged

        # Fade effect (optional - keep solid)
        self.alpha = 0.7 + 0.3 * t  # Fade in to 1.0

    def draw(self, canvas):
        """Render panel on canvas. Efficiently updates existing items."""
        print(f"[TRACE] draw called for {self.panel_id}, items count {len(self.canvas_items)}")
        items = self.canvas_items
        x, y, w, h = int(self.current_x), int(self.current_y), int(self.current_w), int(self.current_h)

        # Ensure minimum dimensions
        if w < 10 or h < 10:
            return

        # Create or update canvas items
        bg_color = C_GLASS_BG
        is_selected = bool(getattr(self, "is_selected", False))
        border_color = self.theme_color if is_selected else C_GLASS_BORDER
        title_color = self.theme_color if is_selected else C_SEC

        if len(items) == 0:
            # Create new items
            # Background rectangle
            items.append(canvas.create_rectangle(x, y, x + w, y + h, fill=bg_color, outline=border_color, width=1))
            # Top-left corner accents
            items.append(canvas.create_line(x, y, x + w, y, fill=C_PRI, width=1))
            items.append(canvas.create_line(x, y, x, y + 20, fill=C_PRI, width=2))
            # Title
            if self.title:
                items.append(canvas.create_text(x + 10, y + 12, text=self.title, fill=title_color,
                                               font=("Courier", 9, "bold"), anchor="w"))
                items.append(canvas.create_line(x + 5, y + 22, x + w - 5, y + 22,
                                               fill=border_color, width=1))
            # Content area (must be created before close button so close button can be appended without affecting index)
            content_item = canvas.create_text(x + 10, y + 35, text="", fill=C_TEXT_PRI,
                                              font=("Courier", 8), anchor="nw", width=w-20)
            items.append(content_item)
            self.text_item = content_item  # Store reference to text item for later updates
            # Close button (only when expanded and not dragging)
            self._create_close_button(canvas, x, y, w, h, items)
            # Set close button visibility for initial state
            self._update_close_button(canvas, x, y, w, h)
        else:
            # Update existing items
            canvas.coords(items[0], x, y, x + w, y + h)
            canvas.itemconfig(items[0], fill=bg_color, outline=border_color)
            canvas.coords(items[1], x, y, x + w, y)
            canvas.itemconfig(items[1], fill=C_PRI)
            canvas.coords(items[2], x, y, x, y + 20)
            canvas.itemconfig(items[2], fill=C_PRI)
            if self.title and len(items) > 3:
                canvas.coords(items[3], x + 10, y + 12)
                canvas.coords(items[4], x + 5, y + 22, x + w - 5, y + 22)
            # Update close button
            self._update_close_button(canvas, x, y, w, h)
            # Update content text item position
            if self.text_item is not None:
                canvas.coords(self.text_item, x + 10, y + 35)
                canvas.itemconfig(self.text_item, width=w-20)

        # Render content based on state
        if self.text_item is not None:
            # Configure text item properties for state
            if self.is_expanded:
                canvas.itemconfig(self.text_item, anchor="nw", width=w-20, font=("Courier", 8))
            else:
                canvas.itemconfig(self.text_item, anchor="center", width=0, font=("Courier", 7))
            # Call appropriate renderer
            if not self.is_expanded and self.collapsed_renderer:
                try:
                    self.collapsed_renderer(canvas, x, y, w, h, self.text_item)
                except Exception as e:
                    print(f"[Panel:{self.panel_id}] Collapsed render error: {e}")
            elif self.is_expanded and self.expanded_renderer:
                try:
                    self.expanded_renderer(canvas, x, y, w, h, self.text_item)
                except Exception as e:
                    print(f"[Panel:{self.panel_id}] Expanded render error: {e}")

        # Keep the panel above any other canvas items that are recreated each frame.
        for item_id in items:
            try:
                canvas.tag_raise(item_id)
            except Exception:
                pass

    def _create_close_button(self, canvas, x, y, w, h, items):
        """Create close button (X) in top-right corner."""
        btn_size = 16
        btn_x = x + w - btn_size - 8
        btn_y = y + 8
        # Create button items and store IDs
        bg_id = canvas.create_rectangle(btn_x, btn_y, btn_x + btn_size, btn_y + btn_size,
                                         fill=C_ERR, outline="", width=0)
        line1_id = canvas.create_line(btn_x + 4, btn_y + 4, btn_x + btn_size - 4, btn_y + btn_size - 4,
                                       fill="white", width=2)
        line2_id = canvas.create_line(btn_x + btn_size - 4, btn_y + 4, btn_x + 4, btn_y + btn_size - 4,
                                       fill="white", width=2)
        items.append(bg_id)
        items.append(line1_id)
        items.append(line2_id)
        self.close_items = [bg_id, line1_id, line2_id]
        self.close_button_rect = (btn_x, btn_y, btn_x + btn_size, btn_y + btn_size)

    def _update_close_button(self, canvas, x, y, w, h):
        """Update close button position and visibility using stored item IDs."""
        if not self.close_items:
            return
        bg_id, line1_id, line2_id = self.close_items
        btn_size = 16
        btn_x = x + w - btn_size - 8
        btn_y = y + 8
        # Update positions
        canvas.coords(bg_id, btn_x, btn_y, btn_x + btn_size, btn_y + btn_size)
        canvas.coords(line1_id, btn_x + 4, btn_y + 4, btn_x + btn_size - 4, btn_y + btn_size - 4)
        canvas.coords(line2_id, btn_x + btn_size - 4, btn_y + 4, btn_x + 4, btn_y + btn_size - 4)
        self.close_button_rect = (btn_x, btn_y, btn_x + btn_size, btn_y + btn_size)
        # Show only when expanded and not dragging
        state = 'normal' if (self.is_expanded and not self.is_dragging) else 'hidden'
        canvas.itemconfig(bg_id, state=state)
        canvas.itemconfig(line1_id, state=state)
        canvas.itemconfig(line2_id, state=state)

    def contains(self, x, y):
        """Check if point is inside panel bounds."""
        return (self.current_x <= x <= self.current_x + self.current_w and
                self.current_y <= y <= self.current_y + self.current_h)

    def close_button_clicked(self, x, y):
        """Check if close button was clicked."""
        if not hasattr(self, 'close_button_rect'):
            return False
        bx1, by1, bx2, by2 = self.close_button_rect
        return bx1 <= x <= bx2 and by1 <= y <= by2

    def start_drag(self, e_x, e_y):
        """Start dragging this panel."""
        self.is_dragging = True
        self.drag_offset_x = e_x - self.current_x
        self.drag_offset_y = e_y - self.current_y

    def drag(self, e_x, e_y):
        """Update panel position while dragging."""
        if self.is_dragging:
            self.current_x = e_x - self.drag_offset_x
            self.current_y = e_y - self.drag_offset_y
            self.current_x = max(0, min(self.current_x, 984 - self.current_w))
            self.current_y = max(0, min(self.current_y, 816 - self.current_h))

    def stop_drag(self):
        """Stop dragging."""
        self.is_dragging = False


# ============================================================================
# PANEL CONTENT RENDERERS
# ============================================================================

def _ascii_bar(pct: float, width: int = 18) -> str:
    """ASCII progress bar (avoids Unicode glyph rendering glitches)."""
    try:
        pct_f = float(pct)
    except Exception:
        pct_f = 0.0
    pct_f = max(0.0, min(100.0, pct_f))
    width = max(4, int(width))
    filled = int(round((pct_f / 100.0) * width))
    filled = max(0, min(width, filled))
    return "#" * filled + "-" * (width - filled)


def _panel_max_chars(panel_w_px: int) -> int:
    return max(16, int((max(0, panel_w_px) - 20) / 7))


def _bar_width_for_panel(panel_w_px: int, reserved_chars: int, max_width: int = 18) -> int:
    width = _panel_max_chars(panel_w_px) - max(0, int(reserved_chars))
    return max(6, min(int(max_width), width))


def _fit_panel_lines(lines: list[str], panel_w_px: int) -> str:
    """
    Clamp long lines so Canvas text can't spill outside panels.
    Tk only wraps on spaces; border strings (──────) otherwise leak.
    """
    max_chars = _panel_max_chars(panel_w_px)
    out: list[str] = []
    for ln in lines:
        ln = (ln or "").replace("\t", "  ").replace("\r", "")
        if len(ln) > max_chars:
            out.append(ln[: max_chars - 3] + "...")
        else:
            out.append(ln)
    return "\n".join(out)

def render_system_monitor(canvas, x, y, w, h, text_item):
    """Render detailed system monitor content."""
    ui = getattr(render_system_monitor, 'ui', None)
    if not ui:
        return

    stats = ui.system_stats
    cpu = stats.get('cpu', 0)
    ram = stats.get('ram', 0)
    bat = stats.get('bat', 0)
    plugged = stats.get('plugged', False)

    physical = psutil.cpu_count(logical=False) or 0
    logical = psutil.cpu_count() or 0

    lines: list[str] = []
    lines.append("CPU")
    bar_w = _bar_width_for_panel(w, reserved_chars=14)
    lines.append(f"Usage: {cpu:3.0f}% [{_ascii_bar(cpu, width=bar_w)}]")
    lines.append(f"Cores: {physical}p/{logical}l")
    lines.append("")

    vm = psutil.virtual_memory()
    used_gb = vm.used / (1024**3)
    total_gb = vm.total / (1024**3)
    lines.append("MEMORY")
    bar_w = _bar_width_for_panel(w, reserved_chars=14)
    lines.append(f"Usage: {ram:3.0f}% [{_ascii_bar(ram, width=bar_w)}]")
    lines.append(f"{used_gb:4.1f}GB / {total_gb:4.1f}GB")
    lines.append("")

    lines.append("STORAGE")
    try:
        root_path = os.environ.get("SystemDrive", "C:") + "\\"
        disk = psutil.disk_usage(root_path)
        disk_pct = disk.percent
        free_gb = disk.free / (1024**3)
        total_gb = disk.total / (1024**3)
        bar_w = _bar_width_for_panel(w, reserved_chars=14)
        lines.append(f"Usage: {disk_pct:3.0f}% [{_ascii_bar(disk_pct, width=bar_w)}]")
        lines.append(f"{free_gb:4.1f}GB free / {total_gb:4.1f}GB")
    except Exception:
        lines.append("Storage: N/A")
    lines.append("")

    lines.append("BATTERY")
    if bat and bat != 0:
        bar_w = max(6, min(10, _bar_width_for_panel(w, reserved_chars=16, max_width=10)))
        lines.append(f"Charge: {bat:3.0f}% [{_ascii_bar(bat, width=bar_w)}]")
        lines.append(f"Status: {'CHARGING' if plugged else 'DISCHARGING'}")
    else:
        lines.append("Battery: N/A")

    status = "HEALTHY" if cpu < 80 and ram < 85 else "HIGH LOAD"
    lines.append("")
    lines.append(f"STATUS: {status}")

    canvas.itemconfig(text_item, text=_fit_panel_lines(lines, w))

def render_system_monitor_collapsed(canvas, x, y, w, h, text_item):
    """Render compact system monitor widget."""
    ui = getattr(render_system_monitor_collapsed, 'ui', None)
    if not ui:
        canvas.itemconfig(text_item, text="NO DATA")
        return

    stats = ui.system_stats
    cpu = stats.get('cpu', 0)
    ram = stats.get('ram', 0)
    bat = stats.get('bat', 0)

    # Single line summary
    text = f"CPU:{cpu:3.0f}%  RAM:{ram:3.0f}%  BAT:{bat:3.0f}%"
    canvas.itemconfig(text_item, text=text, anchor="center", font=("Courier", 8))
    # Re-position to center of panel
    canvas.coords(text_item, x + w//2, y + h//2)


def render_task_manager(canvas, x, y, w, h, text_item):
    """Render task manager expanded content."""
    task_mgr = get_task_manager()
    tasks = task_mgr.get_all_tasks()

    pending = [t for t in tasks if t['status'] == 'pending']
    completed = [t for t in tasks if t['status'] == 'completed']

    lines = []
    lines.append("┌─ TASK MANAGER ─────────┐")
    lines.append(f"│ Pending: {len(pending):3d}            │")
    lines.append(f"│ Done:    {len(completed):3d}            │")
    lines.append("├────────────────────────┤")

    if pending:
        lines.append("│ PENDING TASKS:         │")
        for t in pending[:5]:
            task_text = t['task'][:18]
            lines.append(f"│ □ {task_text:<18} │")
        if len(pending) > 5:
            lines.append(f"│ ...and {len(pending)-5} more           │")

    if completed and len(pending) < 5:
        lines.append("│ COMPLETED:             │")
        for t in completed[:3]:
            task_text = t['task'][:18]
            lines.append(f"│ ✓ {task_text:<18} │")

    lines.append("└─────────────────────────┘")
    lines.append("[Double-click to add]")

    canvas.itemconfig(text_item, text="\n".join(lines))

def render_task_manager_collapsed(canvas, x, y, w, h, text_item):
    """Compact task count widget."""
    task_mgr = get_task_manager()
    tasks = task_mgr.get_all_tasks()
    pending = [t for t in tasks if t['status'] == 'pending']
    text = f"TASKS: {len(pending)} PENDING"
    canvas.itemconfig(text_item, text=text, anchor="center", font=("Courier", 8))
    canvas.coords(text_item, x + w//2, y + h//2)


def render_memory_viewer(canvas, x, y, w, h, text_item):
    """Render memory expanded content."""
    lines: list[str] = ["MEMORY DATABASE"]

    mem_path = BASE_DIR / "memory" / "long_term.json"
    facts = 0
    try:
        if mem_path.exists():
            data = json.loads(mem_path.read_text(encoding="utf-8"))
            facts = (len(data.get("identity", {})) + len(data.get("preferences", {})) +
                    len(data.get("relationships", {})) + len(data.get("notes", {})))
    except:
        pass

    nodes = 0
    db_path = BASE_DIR / "memory" / "knowledge_graph.db"
    try:
        if db_path.exists():
            import sqlite3
            with sqlite3.connect(db_path) as conn:
                res = conn.execute("SELECT COUNT(*) FROM triplets").fetchone()
                nodes = res[0] if res else 0
    except:
        pass

    lines.append(f"Facts: {facts}")
    lines.append(f"Nodes: {nodes}")
    lines.append("")
    lines.append("RECENT FACTS:")
    if facts > 0:
        lines.append("(stored in long_term.json)")
        lines.append("(open memory viewer for details)")
    else:
        lines.append("No facts stored yet")
    lines.append("")
    lines.append("Search: Ctrl+F")

    canvas.itemconfig(text_item, text=_fit_panel_lines(lines, w))

def render_memory_viewer_collapsed(canvas, x, y, w, h, text_item):
    """Compact memory stats widget."""
    mem_path = BASE_DIR / "memory" / "long_term.json"
    facts = 0
    try:
        if mem_path.exists():
            data = json.loads(mem_path.read_text(encoding="utf-8"))
            facts = (len(data.get("identity", {})) + len(data.get("preferences", {})) +
                    len(data.get("relationships", {})) + len(data.get("notes", {})))
    except:
        pass

    nodes = 0
    db_path = BASE_DIR / "memory" / "knowledge_graph.db"
    try:
        if db_path.exists():
            import sqlite3
            with sqlite3.connect(db_path) as conn:
                res = conn.execute("SELECT COUNT(*) FROM triplets").fetchone()
                nodes = res[0] if res else 0
    except:
        pass

    text = f"MEM: {facts} facts | {nodes} nodes"
    canvas.itemconfig(text_item, text=text, anchor="center", font=("Courier", 8))
    canvas.coords(text_item, x + w//2, y + h//2)


def render_agent_dashboard(canvas, x, y, w, h, text_item):
    """Render agent expanded dashboard."""
    from agent.task_queue import get_queue
    queue = get_queue()

    lines: list[str] = ["AGENT DASHBOARD"]

    try:
        all_tasks = queue.get_all_statuses()
        pending = [t for t in all_tasks if t['status'] == 'pending']
        running = [t for t in all_tasks if t['status'] == 'running']
        completed = [t for t in all_tasks if t['status'] == 'completed']
        failed = [t for t in all_tasks if t['status'] == 'failed']

        lines.append(f"Pending: {len(pending)}")
        lines.append(f"Running: {len(running)}")
        lines.append(f"Done:    {len(completed)}")
        lines.append(f"Failed:  {len(failed)}")
        lines.append("")

        if running:
            lines.append("ACTIVE TASKS:")
            for t in running[:3]:
                goal = t['goal'][:18]
                lines.append(f"- {goal}")
            if len(running) > 3:
                lines.append(f"...and {len(running)-3} more")
        else:
            lines.append("No active tasks")

    except Exception as e:
        lines.append(f"Error: {str(e)[:60]}")

    lines.append("")
    lines.append("Pause: Ctrl+P")

    canvas.itemconfig(text_item, text=_fit_panel_lines(lines, w))

def render_agent_dashboard_collapsed(canvas, x, y, w, h, text_item):
    """Compact agent status widget."""
    from agent.task_queue import get_queue
    queue = get_queue()
    try:
        all_tasks = queue.get_all_statuses()
        running = [t for t in all_tasks if t['status'] == 'running']
        text = f"AGENT: {len(running)} ACTIVE"
    except:
        text = "AGENT: N/A"
    canvas.itemconfig(text_item, text=text, anchor="center", font=("Courier", 8))
    canvas.coords(text_item, x + w//2, y + h//2)


# ============================================================================
# CRISTINE UI CLASS
# ============================================================================

class CristineUI:
    def __init__(self):
        print("[DEBUG] CristineUI __init__ start")
        self.root = tk.Tk()
        self.root.title(SYSTEM_NAME)
        self.root.resizable(False, False)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        W, H = min(sw, 984), min(sh, 816)
        self.root.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        self.root.configure(bg=C_BG_TOP)
        self.W, self.H = W, H
        self.FACE_SZ, self.FCX = min(int(H * 0.54), 400), W // 2
        self.FCY = int(H * 0.13) + self.FACE_SZ // 2
        self.speaking, self.scale, self.target_scale, self.halo_a, self.target_halo = False, 1.0, 1.0, 60.0, 60.0
        self.last_t, self.tick, self.scan_angle, self.scan2_angle = time.time(), 0, 0.0, 180.0
        self.rings_spin = [0.0, 120.0, 240.0]
        self.pulse_r = [0.0, self.FACE_SZ * 0.26, self.FACE_SZ * 0.52]
        self.radar_angle, self.data_stream = 0.0, []
        self.status_text, self.status_blink = "INITIALISING", True
        self.system_stats = {"cpu": 0, "ram": 0, "bat": 0, "plugged": False}
        self.memory_stats = {"facts": 0, "triplets": 0}
        # Rolling network counters for KB/s display (updated in _update_system_stats).
        self._net_last_t = None
        self._net_last_sent = None
        self._net_last_recv = None
        self.env_context = {"active_app": "N/A", "project": "None", "focus_time_minutes": 0, "time_of_day": "Morning"}
        self.mic_level = 0.0
        self.last_stats_t, self.compact_mode, self.active_tasks = 0, False, {}
        self.history_stack, self._drag_data = deque(maxlen=5), {"x": 0, "y": 0}
        self.speech_mode, self.text_submit_callback = True, None
        self.typing_queue, self.is_typing, self.current_line_tag = deque(), False, None
        self._face_pil, self._has_face, self._face_scale_cache = None, False, None
        self._load_face(face_path)
        self.preferences_window = None
        self.preferences = self._load_preferences()
        self._startup_enabled = bool(self.preferences.get("startup_run_on_boot", False))
        self.tray_enabled = bool(self.preferences.get("background_tray_enabled", False))
        self._start_minimized = bool(self.preferences.get("background_start_minimized", False))
        self._tray_icon = None
        self.dream_mode_active = False
        self.center_panel_id = None  # Selected menu panel to show details in the center HUD
        self._hovered_button = None  # Track which button is hovered for visual feedback
        self._hovered_panel = None  # Track which panel is hovered
        self.DEBUG_PANELS = True  # Set to True to print panel positions on init

        # Initialize expandable panels
        self.expandable_panels = {}
        self._initialize_panels()
        print("[DEBUG] UI initialized, panels:", list(self.expandable_panels.keys()))
        
        # Apply panel layout system to avoid overlaps
        self._apply_panel_layout()
        
        # Standard panel size definitions (for consistency)
        self.PANEL_SIZES = {
            'small': {'collapsed_w': 200, 'collapsed_h': 60, 'expanded_w': 320, 'expanded_h': 300},
            'medium': {'collapsed_w': 200, 'collapsed_h': 60, 'expanded_w': 380, 'expanded_h': 380},
            'large': {'collapsed_w': 200, 'collapsed_h': 60, 'expanded_w': 420, 'expanded_h': 420}
        }

        # Main Canvas with Background Gradient simulation
        self.bg = tk.Canvas(self.root, width=W, height=H, bg=C_BG_TOP, highlightthickness=0)
        self.bg.place(x=0, y=0)
        self.bg.bind("<Button-1>", self._on_canvas_click)
        self.bg.bind("<B1-Motion>", self._do_drag)
        self.bg.bind("<ButtonRelease-1>", self._on_mouse_release)
        self.bg.bind("<Motion>", self._on_mouse_motion)  # Hover feedback
        self.root.bind("<Control-h>", lambda e: self.toggle_compact())
        self.root.bind("<Control-m>", lambda e: self.toggle_input_mode())
        
        # Glass Styled Log Frame
        self.log_frame = tk.Frame(self.root, bg=C_GLASS_BG, highlightbackground=C_GLASS_BORDER, highlightthickness=1)
        self.log_text = tk.Text(self.log_frame, fg=C_TEXT_PRI, bg=C_GLASS_BG, insertbackground=C_TEXT_PRI, 
                               borderwidth=0, wrap="word", font=("Courier", 10), padx=10, pady=6)
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")
        
        # Glass Styled Input Frame
        self.input_frame = tk.Frame(self.root, bg=C_BG_TOP, highlightthickness=0)
        self.mode_btn = tk.Button(self.input_frame, text="MIC: ON", command=self.toggle_input_mode, 
                                 bg=C_DIM, fg=C_TEXT_PRI, font=("Courier", 8, "bold"), borderwidth=0, 
                                 padx=10, activebackground=C_PRI, activeforeground=C_BG_TOP)
        self.mode_btn.pack(side="left", fill="y", padx=(0, 5))
        
        self.input_entry = tk.Entry(self.input_frame, bg=C_DIMMER, fg=C_TEXT_PRI, insertbackground=C_TEXT_PRI, 
                                   borderwidth=1, highlightbackground=C_GLASS_BORDER, highlightcolor=C_PRI, 
                                   font=("Courier", 11))
        self.input_entry.pack(side="left", fill="both", expand=True)
        self.input_entry.bind("<Return>", self._on_text_submit)
        
        self.log_text.tag_config("you", foreground=C_TEXT_SEC)
        self.log_text.tag_config("ai",  foreground=C_PRI)
        self.log_text.tag_config("sys", foreground=C_SEC)
        self.log_text.tag_config("bold", font=("Courier", 10, "bold"))

        # Place bottom widgets after they exist so we can avoid overlaps.
        self._layout_bottom_widgets()
        self._api_key_ready = Event()
        if not self._api_keys_exist(): 
            self._show_setup_ui()
        else:
            self._api_key_ready.set()
        self._animate()
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)

        self._sync_startup_registration()
        self._sync_tray_state()
        if self.tray_enabled and self._start_minimized and self._api_keys_exist():
            self.root.after(200, self.root.withdraw)

    def _layout_bottom_widgets(self):
        """Place chat log + input so they don't cover the left OPERATIONS column."""
        W, H = self.W, self.H

        left_reserve = 24 + 140 + 24
        right_reserve = 24

        max_w = max(240, W - left_reserve - right_reserve)
        lw = min(int(W * 0.72), max_w)
        lh = 138

        x = (W - lw) // 2
        if x < left_reserve:
            x = left_reserve
            lw = max(240, W - x - right_reserve)

        self.log_frame.place(x=x, y=H - lh - 76, width=lw, height=lh)
        self.input_frame.place(x=x, y=H - 100, width=lw, height=40)

    def update_mic_level(self, level: float):
        """Sets the current mic input level for the HUD visualizer."""
        self.mic_level = max(0.0, min(1.0, level))

    def _on_canvas_click(self, e):
        """Handles both drag starting, panel interactions, and quick-command button clicks."""
        # Check for panel interactions first (top-most panels in reverse order)
        if not self.compact_mode:
            for panel in reversed(list(self.expandable_panels.values())):
                if panel.contains(e.x, e.y):
                    radial_supported = {"system_monitor", "agent", "memory"}
                    if panel.panel_id in radial_supported:
                        # Radial Information Expansion System: render details in the central HUD rings.
                        self.center_panel_id = None if self.center_panel_id == panel.panel_id else panel.panel_id
                        return

                    # Non-radial panels keep normal behavior.
                    if panel.is_expanded and panel.close_button_clicked(e.x, e.y):
                        panel.toggle(False)
                        self._save_panel_preferences()
                    elif not panel.is_dragging:
                        panel.toggle()
                        self._save_panel_preferences()
                    self._start_drag(e)
                    return

        self._start_drag(e)

        # Touch-friendly padding for hit detection
        HIT_PADDING = 8
        if self.compact_mode:
            # Check for Mic Toggle Click in Compact Mode (with touch-friendly padding)
            # Coordinates sync with _draw: bx = (320 - 100) // 2, by = 240 - 45, bw=100, bh=22
            bx, by, bw, bh = 110, 195, 100, 22
            if bx - HIT_PADDING <= e.x <= bx + bw + HIT_PADDING and \
               by - HIT_PADDING <= e.y <= by + bh + HIT_PADDING:
                self.toggle_input_mode()
                return
            return

        # Quick Command Button Check (Screen regions) - Normal Mode
        if not self.compact_mode:
            # Sync coordinates with _draw: bx=24, by=H-155, bw=140, bh=26, step=32
            bx, by, bw, bh = 24, self.H - 155, 140, 26
            for i, cmd in enumerate(["SCREENSHOT", "WEB SEARCH", "EXPLAIN", "NEW TASK"]):
                yy = by + i * 32
                if bx - HIT_PADDING <= e.x <= bx + bw + HIT_PADDING and \
                   yy - HIT_PADDING <= e.y <= yy + bh + HIT_PADDING:
                    print(f"[UI] 🖱️ Quick Cmd Click: {cmd}")
                    mapping = {
                        "SCREENSHOT": "Please capture a screenshot of my screen.",
                        "WEB SEARCH": "Use your web search tool to find information about this.",
                        "EXPLAIN": "Analyze my screen and explain exactly what you see.",
                        "NEW TASK": "I have a new task for you to plan and execute."
                    }
                    if self.text_submit_callback: self.text_submit_callback(mapping[cmd])
                    return

            # Preferences Button Check (with touch-friendly padding)
            pbx, pby, pbw, pbh = 24, self.H - 155 + 32 * 4 + 6, 140, 26
            if pbx - HIT_PADDING <= e.x <= pbx + pbw + HIT_PADDING and \
               pby - HIT_PADDING <= e.y <= pby + pbh + HIT_PADDING:
                print("[UI] 🖱️ Preferences Click")
                self.open_preferences()
                return

            # Note: Old panel toggle coordinates (24-150 x 80-100, 320-340) are deprecated
            # Panels now toggle by clicking directly on them

    def _on_mouse_motion(self, e):
        """Handle mouse motion for hover feedback."""
        if self.compact_mode:
            # Check hover on mic button
            bx, by, bw, bh = 110, 195, 100, 22
            if bx - 8 <= e.x <= bx + bw + 8 and by - 8 <= e.y <= by + bh + 8:
                self.root.config(cursor="hand2")
                self._hovered_button = "mic_compact"
                return
            self.root.config(cursor="")
            self._hovered_button = None
            return

        # Check panel hover first (normal mode)
        panel_hovered = False
        for panel in reversed(list(self.expandable_panels.values())):
            if panel.contains(e.x, e.y):
                self.root.config(cursor="hand2")
                self._hovered_panel = panel.panel_id
                panel_hovered = True
                break

        if panel_hovered:
            return

        # Check quick command buttons
        bx, by, bw, bh = 24, self.H - 155, 140, 26
        hovered = False

        for i in range(4):  # SCREENSHOT, WEB SEARCH, EXPLAIN, NEW TASK
            yy = by + i * 32
            if bx - 8 <= e.x <= bx + bw + 8 and yy - 8 <= e.y <= yy + bh + 8:
                self.root.config(cursor="hand2")
                self._hovered_button = f"quick_{i}"
                hovered = True
                break

        if not hovered:
            # Check preferences button
            pbx, pby, pbw, pbh = 24, self.H - 155 + 32 * 4 + 6, 140, 26
            if pbx - 8 <= e.x <= pbx + pbw + 8 and pby - 8 <= e.y <= pby + pbh + 8:
                self.root.config(cursor="hand2")
                self._hovered_button = "preferences"
                hovered = True

        if not hovered:
            self.root.config(cursor="")
            self._hovered_button = None
            self._hovered_panel = None

    def _on_mouse_release(self, e):
        """Handle mouse button release - stop any panel dragging."""
        for panel in self.expandable_panels.values():
            if panel.is_dragging:
                panel.stop_drag()

    def _load_face(self, path):
        try:
            img = Image.open(path).convert("RGBA").resize((self.FACE_SZ, self.FACE_SZ), Image.LANCZOS)
            mask = Image.new("L", (self.FACE_SZ, self.FACE_SZ), 0)
            ImageDraw.Draw(mask).ellipse((2, 2, self.FACE_SZ-2, self.FACE_SZ-2), fill=255)
            img.putalpha(mask)
            self._face_pil, self._has_face = img, True
        except Exception: self._has_face = False

    def _load_preferences(self):
        """Load preferences from config file."""
        prefs_path = BASE_DIR / "config" / "preferences.json"
        if prefs_path.exists():
            try:
                with open(prefs_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _on_preferences_changed(self, prefs):
        """Called when preferences are saved in the preferences window."""
        self.preferences = prefs
        # Apply interface preferences
        if "interface_compact_mode" in prefs and prefs["interface_compact_mode"] != self.compact_mode:
            self.toggle_compact()
        # Update panel visibility (expanded/collapsed state) for new keys
        for panel_id, panel in self.expandable_panels.items():
            pref_key = f"interface_panel_{panel_id}"
            if pref_key in prefs:
                panel.is_expanded = prefs[pref_key]
                if panel.is_expanded:
                    panel.current_w = panel.expanded_w
                    panel.current_h = panel.expanded_h
                else:
                    panel.current_w = panel.collapsed_w
                    panel.current_h = panel.collapsed_h
        # Backward compatibility: map old keys to new panels
        if "interface_panel_telemetry" in prefs:
            panel = self.expandable_panels.get("system_monitor")
            if panel:
                panel.is_expanded = prefs["interface_panel_telemetry"]
                panel.current_w = panel.expanded_w if panel.is_expanded else panel.collapsed_w
                panel.current_h = panel.expanded_h if panel.is_expanded else panel.collapsed_h
        if "interface_panel_memory" in prefs:
            panel = self.expandable_panels.get("memory")
            if panel:
                panel.is_expanded = prefs["interface_panel_memory"]
                panel.current_w = panel.expanded_w if panel.is_expanded else panel.collapsed_w
                panel.current_h = panel.expanded_h if panel.is_expanded else panel.collapsed_h
        if "interface_panel_logs" in prefs:
            self.show_logs_panel = prefs["interface_panel_logs"]

        # Startup / tray background preferences
        startup = bool(prefs.get("startup_run_on_boot", False))
        start_min = bool(prefs.get("background_start_minimized", False))
        tray = bool(prefs.get("background_tray_enabled", False))

        if startup != getattr(self, "_startup_enabled", False) or start_min != getattr(self, "_start_minimized", False):
            self._startup_enabled = startup
            self._start_minimized = start_min
            self._sync_startup_registration()

        if tray != getattr(self, "tray_enabled", False):
            self.tray_enabled = tray
            self._sync_tray_state()
            if self.tray_enabled and self._start_minimized and self._api_keys_exist():
                self.root.after(200, self.root.withdraw)

        print("[UI] ✅ Preferences updated")

    def _save_panel_preferences(self):
        """Save current panel states to preferences file."""
        try:
            prefs_path = BASE_DIR / "config" / "preferences.json"
            if prefs_path.exists():
                with open(prefs_path, "r", encoding="utf-8") as f:
                    prefs = json.load(f)
            else:
                prefs = {}

            # Update panel expansion states
            for panel_id, panel in self.expandable_panels.items():
                prefs[f"interface_panel_{panel_id}"] = panel.is_expanded

            # Save
            with open(prefs_path, "w", encoding="utf-8") as f:
                json.dump(prefs, f, indent=2)
        except Exception as e:
            print(f"[UI] Failed to save panel preferences: {e}")

    def open_preferences(self):
        """Open the preferences window."""
        if self.preferences_window is None:
            self.preferences_window = PreferencesWindow(
                self.root,
                prefs_callback=self._on_preferences_changed,
                log_callback=self.write_log,
            )
        self.preferences_window.open()

    def _sync_startup_registration(self):
        try:
            from system.startup_manager import set_run_on_startup

            ok, msg = set_run_on_startup(
                bool(getattr(self, "_startup_enabled", False)),
                start_minimized=bool(getattr(self, "_start_minimized", False) and getattr(self, "tray_enabled", False)),
            )
            self.write_log(f"[startup] {msg}", tag="sys")
        except Exception as e:
            try:
                self.write_log(f"[startup] error: {str(e)[:160]}", tag="sys")
            except Exception:
                pass

    def _sync_tray_state(self):
        if bool(getattr(self, "tray_enabled", False)):
            self._ensure_tray_icon()
        else:
            self._stop_tray_icon()

    def _ensure_tray_icon(self):
        if getattr(self, "_tray_icon", None) is not None:
            return

        try:
            import pystray  # type: ignore
        except Exception:
            self.write_log("Tray icon requires 'pystray'. Install dependencies and restart.", tag="sys")
            return

        try:
            from PIL import Image, ImageDraw

            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.ellipse((8, 8, 56, 56), outline=(79, 209, 255, 255), width=3)
            d.ellipse((16, 16, 48, 48), outline=(166, 108, 255, 220), width=2)
            d.line((32, 12, 32, 52), fill=(82, 255, 168, 220), width=2)
            d.line((12, 32, 52, 32), fill=(82, 255, 168, 220), width=2)

            menu = pystray.Menu(
                pystray.MenuItem("Open Cristine", self._tray_open, default=True),
                pystray.MenuItem("Hide", self._tray_hide),
                pystray.MenuItem("Quit", self._tray_quit),
            )
            icon = pystray.Icon("Cristine", img, "Cristine", menu)
            self._tray_icon = icon
            threading.Thread(target=icon.run, daemon=True).start()
            self.write_log("Tray icon enabled. Closing the window will keep Cristine running.", tag="sys")
        except Exception as e:
            self._tray_icon = None
            self.write_log(f"Tray icon failed to start: {str(e)[:160]}", tag="sys")

    def _stop_tray_icon(self):
        icon = getattr(self, "_tray_icon", None)
        self._tray_icon = None
        if not icon:
            return

        def stopper():
            try:
                icon.stop()
            except Exception:
                pass

        threading.Thread(target=stopper, daemon=True).start()

    def _tray_open(self, icon=None, item=None):
        try:
            self.root.after(0, self._show_window)
        except Exception:
            pass

    def _tray_hide(self, icon=None, item=None):
        try:
            self.root.after(0, self.root.withdraw)
        except Exception:
            pass

    def _tray_quit(self, icon=None, item=None):
        try:
            self.root.after(0, self._quit_app)
        except Exception:
            pass

    def _show_window(self):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

    def _on_window_close(self):
        if bool(getattr(self, "tray_enabled", False)) and getattr(self, "_tray_icon", None) is not None:
            try:
                self.root.withdraw()
                self.write_log("Cristine is still running in the tray.", tag="sys")
            except Exception:
                pass
            return
        self._quit_app()

    def _quit_app(self):
        try:
            self._stop_tray_icon()
        except Exception:
            pass
        os._exit(0)

    def _initialize_panels(self):
        """Create all expandable panels with their content renderers."""
        left_x = 24
        telemetry_y = 80
        # Menu stack on the left (no in-place expansion; details render in center HUD rings).
        stack_gap = 14
        
        # Standard panel size definitions (for consistency)
        self.PANEL_SIZES = {
            'small': {'collapsed_w': 200, 'collapsed_h': 60, 'expanded_w': 320, 'expanded_h': 300},
            'medium': {'collapsed_w': 200, 'collapsed_h': 60, 'expanded_w': 380, 'expanded_h': 380},
            'large': {'collapsed_w': 200, 'collapsed_h': 60, 'expanded_w': 420, 'expanded_h': 420}
        }

        collapsed_w = 180
        collapsed_h_small = 60
        expanded_h_large = 320

        system_y = telemetry_y - 10
        agent_y = system_y + (collapsed_h_small + 20) + stack_gap
        memory_y = agent_y + (collapsed_h_small + 20) + stack_gap
        memory_y = max(50, min(memory_y, self.H - (collapsed_h_small + 20) - 10))

        # Attach UI reference to system monitor renderers for live stats
        render_system_monitor.ui = self
        render_system_monitor_collapsed.ui = self

        # System Monitor Panel (replaces CORE TELEMETRY)
        system_panel = ExpandablePanel(
            panel_id="system_monitor",
            x=left_x - 10,
            y=telemetry_y - 10,
            collapsed_w=collapsed_w + 20,
            collapsed_h=collapsed_h_small + 20,
            expanded_w=380,
            expanded_h=expanded_h_large,
            title="CORE TELEMETRY",
            theme_color=C_PRI,
            expanded_renderer=render_system_monitor,
            collapsed_renderer=render_system_monitor_collapsed
        )
        self.expandable_panels["system_monitor"] = system_panel

        # Agent Dashboard Panel (between telemetry and neural link)
        agent_panel = ExpandablePanel(
            panel_id="agent",
            x=left_x - 10,
            y=agent_y,
            collapsed_w=collapsed_w + 20,
            collapsed_h=collapsed_h_small + 20,
            expanded_w=400,
            expanded_h=300,
            title="AGENT DASHBOARD",
            theme_color=C_WARN,
            expanded_renderer=render_agent_dashboard,
            collapsed_renderer=render_agent_dashboard_collapsed
        )
        self.expandable_panels["agent"] = agent_panel

        # Memory Viewer Panel (NEURAL LINK)
        memory_panel = ExpandablePanel(
            panel_id="memory",
            x=left_x - 10,
            y=memory_y,
            collapsed_w=collapsed_w + 20,
            collapsed_h=collapsed_h_small + 20,
            expanded_w=400,
            expanded_h=350,
            title="NEURAL LINK",
            theme_color=C_SUCCESS,
            expanded_renderer=render_memory_viewer,
            collapsed_renderer=render_memory_viewer_collapsed
        )
        self.expandable_panels["memory"] = memory_panel

        # Tasks panel on the right (keeps normal expand/collapse behavior; not radial).
        tasks_x = max(0, self.W - 350 - 10)
        tasks_y = 250
        task_panel = ExpandablePanel(
            panel_id="tasks",
            x=tasks_x,
            y=tasks_y,
            collapsed_w=collapsed_w + 20,
            collapsed_h=collapsed_h_small + 20,
            expanded_w=350,
            expanded_h=400,
            title="TODAY'S TASKS",
            theme_color=C_ACC,
            expanded_renderer=render_task_manager,
            collapsed_renderer=render_task_manager_collapsed
        )
        self.expandable_panels["tasks"] = task_panel

        # Apply preferences
        prefs = self.preferences

        system_panel.is_expanded = prefs.get("interface_panel_system_monitor", prefs.get("interface_panel_telemetry", False))
        system_panel.current_h = system_panel.expanded_h if system_panel.is_expanded else system_panel.collapsed_h
        system_panel.current_w = system_panel.expanded_w if system_panel.is_expanded else system_panel.collapsed_w

        task_panel.is_expanded = prefs.get("interface_panel_tasks", False)
        task_panel.current_h = task_panel.expanded_h if task_panel.is_expanded else task_panel.collapsed_h
        task_panel.current_w = task_panel.expanded_w if task_panel.is_expanded else task_panel.collapsed_w

        memory_panel.is_expanded = prefs.get("interface_panel_memory", False)
        memory_panel.current_h = memory_panel.expanded_h if memory_panel.is_expanded else memory_panel.collapsed_h
        memory_panel.current_w = memory_panel.expanded_w if memory_panel.is_expanded else memory_panel.collapsed_w

        agent_panel.is_expanded = prefs.get("interface_panel_agent", False)
        agent_panel.current_h = agent_panel.expanded_h if agent_panel.is_expanded else agent_panel.collapsed_h
        agent_panel.current_w = agent_panel.expanded_w if agent_panel.is_expanded else agent_panel.collapsed_w

        self.show_logs_panel = prefs.get("interface_panel_logs", True)

        # Debug: print panel positions if enabled
        if self.DEBUG_PANELS:
            for pid, panel in self.expandable_panels.items():
                print(f"[DEBUG] Panel {pid}: pos=({panel.current_x},{panel.current_y}) size={int(panel.current_w)}x{int(panel.current_h)} expanded={panel.is_expanded}")

    def _apply_panel_layout(self):
        """Apply automatic layout to position panels without overlaps."""
        if not self.expandable_panels:
            return
        
        # Define layout columns with safe margins
        margin = 10
        left_col_x = margin
        right_col_x = self.W - margin
        
        # Separate panels into left and right columns
        left_panels = []
        right_panels = []
        
        for panel in self.expandable_panels.values():
            # Use the panel's natural x position to determine column
            # Panels with x < W/2 go to left, others to right
            if panel.x < self.W / 2:
                left_panels.append(panel)
            else:
                right_panels.append(panel)
        
        # Layout left column: stack vertically from top
        current_y = 80  # Start below header
        vertical_spacing = 12
        
        for panel in left_panels:
            # Determine which height to use (expanded or collapsed based on state)
            target_h = panel.expanded_h if panel.is_expanded else panel.collapsed_h
            target_w = panel.expanded_w if panel.is_expanded else panel.collapsed_w
            
            # Apply position
            panel.current_x = left_col_x + 5  # Small offset for visual balance
            panel.current_y = current_y
            
            # Update for next panel
            current_y += target_h + vertical_spacing
        
        # Layout right column: stack vertically from top
        # Leave vertical space for the static SYSTEM LOGS glass panel on the right.
        current_y = 250 if getattr(self, "show_logs_panel", True) else 100
        for panel in right_panels:
            target_h = panel.expanded_h if panel.is_expanded else panel.collapsed_h
            target_w = panel.expanded_w if panel.is_expanded else panel.collapsed_w
            
            # Align right edge
            panel.current_x = right_col_x - target_w
            panel.current_y = current_y
            
            current_y += target_h + vertical_spacing
        
        # Ensure panels don't exceed bottom boundary
        max_y = self.H - 200  # Leave space for footer and other elements
        for panel in self.expandable_panels.values():
            if panel.current_y + panel.current_h > max_y:
                panel.current_y = max(0, max_y - panel.current_h)
        
        if self.DEBUG_PANELS:
            print(f"[LAYOUT] Applied automatic panel layout")

    @staticmethod
    def _ac(r, g, b, a):
        f = a / 255.0
        return f"#{int(r*f):02x}{int(g*f):02x}{int(b*f):02x}"

    def toggle_input_mode(self):
        self.speech_mode = not self.speech_mode
        self.mode_btn.configure(text="MIC: ON" if self.speech_mode else "MIC: OFF", bg=C_DIM if not self.speech_mode else C_SEC)
        self.write_log(f"SYS: Mode set to {'SPEECH' if self.speech_mode else 'TEXT'}", tag="sys")
        if not self.speech_mode: self.input_entry.focus_set()

    def _on_text_submit(self, event):
        txt = self.input_entry.get().strip()
        if txt:
            self.input_entry.delete(0, tk.END); self.write_log(txt, tag="you")
            if self.text_submit_callback: self.text_submit_callback(txt)

    def write_log(self, text: str, tag: str = "ai", is_stream: bool = False):
        # Tkinter is not thread-safe. Many actions run in background threads and
        # will call write_log; marshal those calls onto the UI thread.
        try:
            if threading.current_thread() is not threading.main_thread():
                self.root.after(0, lambda t=text, tg=tag, s=is_stream: self.write_log(t, tag=tg, is_stream=s))
                return
        except Exception:
            # Best-effort fallback (may still work, depending on environment).
            pass

        if text.strip() or not is_stream:
            if not is_stream or (is_stream and self.current_line_tag != tag):
                if text.strip(): self.history_stack.append((tag, text[:35]))
            self.typing_queue.append((text, tag, is_stream))
            if not self.is_typing: self._start_typing()

    def _start_typing(self):
        if not self.typing_queue:
            self.is_typing = False
            if not self.speaking: self.status_text = "ONLINE"
            return
        self.is_typing = True
        txt, tag, is_stream = self.typing_queue.popleft()
        self.log_text.configure(state="normal")
        if self.current_line_tag != tag:
            p = "\nYOU: " if tag == "you" else "\nCRISTINE: " if tag == "ai" else "\nSYS: "
            if self.log_text.index("end-1c") == "1.0": p = p.strip()
            self.log_text.insert(tk.END, p, (tag, "bold")); self.current_line_tag = tag
        self._type_char(txt, 0, tag, is_stream)

    def _type_char(self, t, i, tag, stream):
        if i < len(t):
            self.log_text.insert(tk.END, t[i], tag); self.log_text.see(tk.END)
            self.root.after(5 if stream else 8, self._type_char, t, i+1, tag, stream)
        else:
            if not stream: self.current_line_tag = None
            self.log_text.configure(state="disabled"); self.root.after(10, self._start_typing)

    def _animate(self):
        self.tick += 1
        t, now = self.tick, time.time()
        if now - self.last_t > (0.14 if self.speaking else 0.55):
            if self.speaking: self.target_scale, self.target_halo = random.uniform(1.05, 1.11), random.uniform(138, 182)
            else: self.target_scale, self.target_halo = random.uniform(1.001, 1.007), random.uniform(50, 68)
            self.last_t = now
        sp = 0.35 if self.speaking else 0.16
        self.scale += (self.target_scale - self.scale) * sp
        self.halo_a += (self.target_halo - self.halo_a) * sp
        for i, s in enumerate([1.2, -0.8, 1.9] if self.speaking else [0.5, -0.3, 0.82]): self.rings_spin[i] = (self.rings_spin[i] + s) % 360
        self.scan_angle, self.scan2_angle = (self.scan_angle + (2.8 if self.speaking else 1.2)) % 360, (self.scan2_angle + (-1.7 if self.speaking else -0.68)) % 360
        pspd, limit = (3.8 if self.speaking else 1.8), self.FACE_SZ * 0.72
        new_p = [r + pspd for r in self.pulse_r if r + pspd < limit]
        if len(new_p) < 3 and random.random() < (0.06 if self.speaking else 0.022): new_p.append(0.0)
        self.pulse_r = new_p

        # Mode-specific animations
        if self.speaking:
            if t % 3 == 0: self.data_stream.append([random.randint(0, self.W), 0, random.randint(5, 12), random.choice("01ABCDEF")])
            self.data_stream = [[x, y + s, s, c] for x, y, s, c in self.data_stream if y < self.H]
        else:
            self.radar_angle = (self.radar_angle + 1.5) % 360
            if self.data_stream: self.data_stream.pop(0)

        if t % 40 == 0: self.status_blink = not self.status_blink
        if now - self.last_stats_t > 3.0: self._update_system_stats(); self.last_stats_t = now

        # Update panel animations
        if not self.compact_mode:
            for panel in self.expandable_panels.values():
                try:
                    panel.update()
                except Exception as e:
                    print(f"[Panel:{panel.panel_id}] Update error: {e}")

        try:
            self._draw()
        except Exception as e:
            print(f"UI Draw Error: {e}")
        self.root.after(16, self._animate)

    def _update_system_stats(self):
        try:
            # --- Core telemetry ---
            cpu = psutil.cpu_percent()
            vm = psutil.virtual_memory()
            ram = vm.percent

            bat_obj = psutil.sensors_battery()
            bat_pct = bat_obj.percent if bat_obj else 0
            plugged = bat_obj.power_plugged if bat_obj else False
            bat_left_min = None
            try:
                if bat_obj and bat_obj.secsleft not in (None, -1, -2) and bat_obj.secsleft > 0:
                    bat_left_min = int(bat_obj.secsleft / 60)
            except Exception:
                pass

            cpu_ghz = None
            try:
                freq = psutil.cpu_freq()
                if freq and getattr(freq, "current", None):
                    cpu_ghz = float(freq.current) / 1000.0
            except Exception:
                pass

            disk_pct = None
            disk_free_gb = None
            try:
                root_path = os.environ.get("SystemDrive", "C:") + "\\"
                du = psutil.disk_usage(root_path)
                disk_pct = float(du.percent)
                disk_free_gb = float(du.free) / (1024**3)
            except Exception:
                pass

            uptime_h = None
            try:
                bt = psutil.boot_time()
                if bt:
                    uptime_h = (time.time() - float(bt)) / 3600.0
            except Exception:
                pass

            net_down_kbps = None
            net_up_kbps = None
            try:
                net = psutil.net_io_counters()
                now = time.time()
                if self._net_last_t is not None and self._net_last_sent is not None and self._net_last_recv is not None:
                    dt = max(0.001, now - float(self._net_last_t))
                    net_up_kbps = max(0.0, (net.bytes_sent - int(self._net_last_sent)) / dt / 1024.0)
                    net_down_kbps = max(0.0, (net.bytes_recv - int(self._net_last_recv)) / dt / 1024.0)
                self._net_last_t = now
                self._net_last_sent = int(net.bytes_sent)
                self._net_last_recv = int(net.bytes_recv)
            except Exception:
                pass

            self.system_stats = {
                "cpu": cpu,
                "ram": ram,
                "bat": bat_pct,
                "plugged": plugged,
                "bat_left_min": bat_left_min,
                "cpu_ghz": cpu_ghz,
                "disk_pct": disk_pct,
                "disk_free_gb": disk_free_gb,
                "uptime_h": uptime_h,
                "net_down_kbps": net_down_kbps,
                "net_up_kbps": net_up_kbps,
            }

            # Context monitor snapshot
            self.env_context = context_monitor.get_current_context()

            # --- Memory stats ---
            mem_path = Path(BASE_DIR) / "memory" / "long_term.json"
            db_path = Path(BASE_DIR) / "memory" / "knowledge_graph.db"

            mem_mtime = None
            kg_mtime = None

            if mem_path.exists():
                try:
                    data = json.loads(mem_path.read_text(encoding="utf-8"))
                    id_n = len(data.get("identity", {}) or {})
                    pref_n = len(data.get("preferences", {}) or {})
                    rel_n = len(data.get("relationships", {}) or {})
                    notes_n = len(data.get("notes", {}) or {})
                    facts = id_n + pref_n + rel_n + notes_n
                    self.memory_stats["facts"] = facts
                    self.memory_stats["facts_identity"] = id_n
                    self.memory_stats["facts_preferences"] = pref_n
                    self.memory_stats["facts_relationships"] = rel_n
                    self.memory_stats["facts_notes"] = notes_n
                except Exception:
                    pass
                try:
                    st = mem_path.stat()
                    self.memory_stats["lt_kb"] = float(st.st_size) / 1024.0
                    mem_mtime = float(st.st_mtime)
                except Exception:
                    pass
            else:
                self.memory_stats.setdefault("facts_identity", 0)
                self.memory_stats.setdefault("facts_preferences", 0)
                self.memory_stats.setdefault("facts_relationships", 0)
                self.memory_stats.setdefault("facts_notes", 0)

            if db_path.exists():
                try:
                    import sqlite3
                    with sqlite3.connect(db_path) as conn:
                        res = conn.execute("SELECT COUNT(*) FROM triplets").fetchone()
                        self.memory_stats["triplets"] = res[0] if res else 0
                except Exception:
                    pass
                try:
                    st = db_path.stat()
                    self.memory_stats["kg_mb"] = float(st.st_size) / (1024.0 * 1024.0)
                    kg_mtime = float(st.st_mtime)
                except Exception:
                    pass

            mt = 0.0
            for ts in (mem_mtime, kg_mtime):
                if ts:
                    mt = max(mt, float(ts))
            self.memory_stats["activity_mins"] = int((time.time() - mt) / 60) if mt else None

        except Exception:
            pass

    def toggle_compact(self):
        self.compact_mode = not self.compact_mode
        if self.compact_mode:
            self.root.overrideredirect(True); self.root.attributes("-topmost", True); self.root.geometry("320x240"); self.log_frame.place_forget(); self.input_frame.place_forget()
        else:
            self.root.overrideredirect(False); self.root.attributes("-topmost", False); sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            self.root.geometry(f"{self.W}x{self.H}+{(sw-self.W)//2}+{(sh-self.H)//2}")
            self._layout_bottom_widgets()
        self.write_log(f"Compact mode {'ENABLED' if self.compact_mode else 'DISABLED'}", tag="sys")

    def set_task_status(self, n, a):
        if a: self.active_tasks[n] = time.time()
        else: self.active_tasks.pop(n, None)

    def _start_drag(self, e):
        """Start dragging - either a panel in normal mode, or the whole window in compact mode."""
        # Check if we're dragging an expanded panel
        if not self.compact_mode:
            for panel in reversed(list(self.expandable_panels.values())):
                if panel.contains(e.x, e.y) and panel.is_expanded:
                    panel.start_drag(e.x, e.y)
                    return

        # Otherwise, start window drag (compact mode or clicked on empty space)
        self._drag_data["x"], self._drag_data["y"] = e.x, e.y

    def _do_drag(self, e):
        """Handle dragging - either panel or window."""
        # First check if a panel is being dragged
        if not self.compact_mode:
            for panel in self.expandable_panels.values():
                if panel.is_dragging:
                    panel.drag(e.x, e.y)
                    return

        # Window dragging (compact mode)
        if self.compact_mode:
            self.root.geometry(f"+{self.root.winfo_x() + (e.x - self._drag_data['x'])}+{self.root.winfo_y() + (e.y - self._drag_data['y'])}")

    def _draw_glass_panel(self, x, y, w, h, title=""):
        c = self.bg
        # Main glass body with proper width enforcement
        x, y, w, h = int(x), int(y), int(w), int(h)
        c.create_rectangle(x, y, x + w, y + h, fill=C_GLASS_BG, outline=C_GLASS_BORDER, width=1)
        # Inner glow / highlights
        c.create_line(x, y, x + w, y, fill=C_PRI, width=1) # Top edge glow
        c.create_line(x, y, x, y + 20, fill=C_PRI, width=2) # Top-left accent
        if title:
            c.create_text(x + 10, y + 12, text=title, fill=C_SEC, font=("Courier", 9, "bold"), anchor="w")
            c.create_line(x + 5, y + 22, x + w - 5, y + 22, fill=C_GLASS_BORDER, width=1)

    def _hex_rgb(self, col: str) -> tuple[int, int, int]:
        col = (col or "").strip()
        if len(col) == 7 and col.startswith("#"):
            try:
                return int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
            except Exception:
                pass
        return 79, 209, 255

    @staticmethod
    def _polar_tk(cx: int, cy: int, r: float, deg: float) -> tuple[float, float]:
        """Tk-style polar: 0°=right, 90°=up, 180°=left, 270°=down."""
        rad = math.radians(deg)
        return cx + r * math.cos(rad), cy - r * math.sin(rad)

    def _draw_text(self, x: float, y: float, *, text: str, fill: str, font, anchor: str = "center"):
        # Subtle shadow so text stays readable on the radar background.
        self.bg.create_text(x + 1, y + 1, text=text, fill=C_BG_TOP, font=font, anchor=anchor)
        self.bg.create_text(x, y, text=text, fill=fill, font=font, anchor=anchor)

    @staticmethod
    def _ring_bbox(cx: int, cy: int, r: int) -> tuple[int, int, int, int]:
        return (cx - r, cy - r, cx + r, cy + r)

    def _draw_ring_gauge(self, cx: int, cy: int, *, r: int, thickness: int, pct: float | None, col_hex: str):
        rr, gg, bb = self._hex_rgb(col_hex)
        track = self._ac(rr, gg, bb, 26)
        glow = self._ac(rr, gg, bb, 70)
        fill = self._ac(rr, gg, bb, 230)
        bbox = self._ring_bbox(cx, cy, r)
        self.bg.create_arc(bbox, start=90, extent=-359.9, style="arc", outline=track, width=thickness)
        if pct is None:
            return
        try:
            pct_f = float(pct)
        except Exception:
            pct_f = 0.0
        pct_f = max(0.0, min(100.0, pct_f))
        extent = -359.9 * (pct_f / 100.0)
        if abs(extent) < 2.0 and pct_f > 0:
            extent = -2.0
        self.bg.create_arc(bbox, start=90, extent=extent, style="arc", outline=glow, width=thickness + 2)
        self.bg.create_arc(bbox, start=90, extent=extent, style="arc", outline=fill, width=thickness)
        end_deg = 90.0 + float(extent)
        ex, ey = self._polar_tk(cx, cy, r, end_deg)
        self.bg.create_oval(ex - 2, ey - 2, ex + 2, ey + 2, fill=fill, outline="")

    def _draw_ring_segment(self, cx: int, cy: int, *, r: int, thickness: int, center_deg: float, span_deg: float, progress: float, col_hex: str):
        rr, gg, bb = self._hex_rgb(col_hex)
        track = self._ac(rr, gg, bb, 26)
        glow = self._ac(rr, gg, bb, 70)
        fill = self._ac(rr, gg, bb, 230)
        bbox = self._ring_bbox(cx, cy, r)
        start = center_deg - (span_deg / 2.0)
        self.bg.create_arc(bbox, start=start, extent=span_deg, style="arc", outline=track, width=thickness)
        p = max(0.0, min(1.0, float(progress)))
        if p <= 0:
            return
        extent = span_deg * p
        if extent < 2.0:
            extent = 2.0
        self.bg.create_arc(bbox, start=start, extent=extent, style="arc", outline=glow, width=thickness + 2)
        self.bg.create_arc(bbox, start=start, extent=extent, style="arc", outline=fill, width=thickness)
        end_deg = float(start) + float(extent)
        ex, ey = self._polar_tk(cx, cy, r, end_deg)
        self.bg.create_oval(ex - 2, ey - 2, ex + 2, ey + 2, fill=fill, outline="")

    def _draw_ring_label(self, cx: int, cy: int, *, r: int, thickness: int, angle_deg: float, title: str, subtitle: str | None, col_hex: str):
        rr, gg, bb = self._hex_rgb(col_hex)
        col = self._ac(rr, gg, bb, 235)
        sub = self._ac(rr, gg, bb, 160)

        mx, my = self._polar_tk(cx, cy, r + (thickness / 2.0) - 2.0, angle_deg)
        self.bg.create_oval(mx - 2, my - 2, mx + 2, my + 2, fill=col, outline="")

        lx, ly = self._polar_tk(cx, cy, r - (thickness / 2.0) + 8.0, angle_deg)
        anchor = "e" if math.cos(math.radians(angle_deg)) < 0 else "w"
        self.bg.create_line(mx, my, lx, ly, fill=sub, width=1)
        self._draw_text(lx, ly - 6, text=title, fill=col, font=("Courier", 9, "bold"), anchor=anchor)
        if subtitle:
            self._draw_text(lx, ly + 8, text=subtitle, fill=sub, font=("Courier", 7, "bold"), anchor=anchor)

    def _draw_center_title(self, cx: int, cy: int, *, title: str, line1: str, line2: str | None, line3: str | None = None, col_hex: str):
        rr, gg, bb = self._hex_rgb(col_hex)
        tcol = self._ac(rr, gg, bb, 235)
        self._draw_text(cx, cy - 18, text=title, fill=tcol, font=("Courier", 11, "bold"), anchor="center")
        self._draw_text(cx, cy + 2, text=line1, fill=C_TEXT_PRI, font=("Courier", 8, "bold"), anchor="center")
        if line2:
            self._draw_text(cx, cy + 18, text=line2, fill=C_TEXT_SEC, font=("Courier", 8), anchor="center")
        if line3:
            self._draw_text(cx, cy + 32, text=line3, fill=C_TEXT_SEC, font=("Courier", 7, "bold"), anchor="center")

    def _draw_radial_info(self, FCX: int, FCY: int, FW: int, tick: int):
        if self.compact_mode or not self.center_panel_id:
            return

        supported = {"system_monitor", "agent", "memory"}
        if self.center_panel_id not in supported:
            return

        panel = self.expandable_panels.get(self.center_panel_id)
        theme_col = getattr(panel, "theme_color", C_PRI) if panel else C_PRI

        # Ring boundaries (match the HUD ring structure).
        r_outer = int(FW * 0.48)
        r_mid = int(FW * 0.40)
        r_inner = int(FW * 0.32)
        r_core = int(FW * 0.26)

        band_outer_r = int((r_outer + r_mid) / 2)
        band_outer_th = max(6, (r_outer - r_mid) - 10)
        band_mid_r = int((r_mid + r_inner) / 2)
        band_mid_th = max(5, (r_mid - r_inner) - 10)
        band_inner_r = int((r_inner + r_core) / 2)
        band_inner_th = max(4, (r_inner - r_core) - 10)

        # Subtle overall glow to "activate" the HUD.
        rr, gg, bb = self._hex_rgb(theme_col)
        pulse = 18 + int(10 * math.sin(tick * 0.06))
        glow = self._ac(rr, gg, bb, 25 + pulse)
        for rr_line in (r_outer, r_mid, r_inner):
            self.bg.create_oval(FCX - rr_line, FCY - rr_line, FCX + rr_line, FCY + rr_line, outline=glow, width=1)

        if self.center_panel_id == "system_monitor":
            cpu = float(self.system_stats.get("cpu", 0) or 0)
            ram = float(self.system_stats.get("ram", 0) or 0)
            bat = self.system_stats.get("bat", 0) or 0
            plugged = bool(self.system_stats.get("plugged", False))
            cpu_ghz = self.system_stats.get("cpu_ghz", None)
            bat_left_min = self.system_stats.get("bat_left_min", None)

            physical = psutil.cpu_count(logical=False) or 0
            logical = psutil.cpu_count() or 0
            vm = psutil.virtual_memory()
            used_gb = vm.used / (1024**3)
            total_gb = vm.total / (1024**3)

            self._draw_ring_gauge(FCX, FCY, r=band_outer_r, thickness=band_outer_th, pct=cpu, col_hex=C_PRI)
            self._draw_ring_gauge(FCX, FCY, r=band_mid_r, thickness=band_mid_th, pct=ram, col_hex=C_SEC)
            self._draw_ring_gauge(FCX, FCY, r=band_inner_r, thickness=band_inner_th, pct=bat if bat else None, col_hex=C_ACC)

            cpu_sub = f"{physical}p/{logical}l"
            if isinstance(cpu_ghz, (int, float)) and cpu_ghz:
                cpu_sub = f"{cpu_sub} {cpu_ghz:.1f}GHz"
            self._draw_ring_label(FCX, FCY, r=band_outer_r, thickness=band_outer_th, angle_deg=140, title=f"CPU {cpu:.0f}%", subtitle=cpu_sub, col_hex=C_PRI)
            self._draw_ring_label(FCX, FCY, r=band_mid_r, thickness=band_mid_th, angle_deg=220, title=f"RAM {ram:.0f}%", subtitle=f"{used_gb:.1f}/{total_gb:.1f}GB", col_hex=C_SEC)
            bat_title = f"BAT {bat:.0f}%" if bat else "BAT N/A"
            bat_sub = "CHG" if plugged else "DIS"
            if isinstance(bat_left_min, (int, float)) and bat_left_min and bat_left_min > 0:
                h = int(bat_left_min) // 60
                m = int(bat_left_min) % 60
                bat_sub = f"{bat_sub} {h}h{m:02d}"
            self._draw_ring_label(FCX, FCY, r=band_inner_r, thickness=band_inner_th, angle_deg=320, title=bat_title, subtitle=bat_sub if bat else None, col_hex=C_ACC)

            host = (os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "").strip()
            disk_pct = self.system_stats.get("disk_pct", None)
            disk_free_gb = self.system_stats.get("disk_free_gb", None)
            net_down = self.system_stats.get("net_down_kbps", None)
            net_up = self.system_stats.get("net_up_kbps", None)
            uptime_h = self.system_stats.get("uptime_h", None)

            disk_line_parts: list[str] = []
            if isinstance(disk_pct, (int, float)):
                disk_line_parts.append(f"DISK {disk_pct:.0f}%")
            if isinstance(disk_free_gb, (int, float)):
                disk_line_parts.append(f"FREE {disk_free_gb:.0f}GB")
            if isinstance(net_down, (int, float)) and isinstance(net_up, (int, float)):
                disk_line_parts.append(f"NET {net_down:.0f}/{net_up:.0f}KB/s")
            disk_line = "  ".join(disk_line_parts) if disk_line_parts else None

            host_line = None
            if host or isinstance(uptime_h, (int, float)):
                host_line = f"{host or 'HOST'}  UP {float(uptime_h or 0.0):.1f}h"

            self._draw_center_title(
                FCX,
                FCY,
                title="CORE TELEMETRY",
                line1=f"CPU {cpu:.0f}%  RAM {ram:.0f}%  BAT {bat:.0f}%",
                line2=disk_line,
                line3=host_line,
                col_hex=theme_col,
            )

        elif self.center_panel_id == "agent":
            try:
                queue = get_queue()
                all_tasks = queue.get_all_statuses()
            except Exception:
                all_tasks = []

            pending = len([t for t in all_tasks if t.get("status") == "pending"])
            running = len([t for t in all_tasks if t.get("status") == "running"])
            done = len([t for t in all_tasks if t.get("status") == "completed"])
            failed = len([t for t in all_tasks if t.get("status") == "failed"])
            cancelled = len([t for t in all_tasks if t.get("status") == "cancelled"])

            self._draw_ring_segment(FCX, FCY, r=band_outer_r, thickness=band_outer_th, center_deg=140, span_deg=80, progress=min(1.0, running / 10.0), col_hex=C_WARN)
            self._draw_ring_segment(FCX, FCY, r=band_outer_r, thickness=band_outer_th, center_deg=40, span_deg=80, progress=min(1.0, pending / 10.0), col_hex=C_PRI)
            self._draw_ring_segment(FCX, FCY, r=band_mid_r, thickness=band_mid_th, center_deg=220, span_deg=80, progress=min(1.0, done / 20.0), col_hex=C_SUCCESS)
            self._draw_ring_segment(FCX, FCY, r=band_mid_r, thickness=band_mid_th, center_deg=320, span_deg=80, progress=min(1.0, failed / 10.0), col_hex=C_ERR)

            total = max(1, pending + running + done + failed)
            done_pct = (done / total) * 100.0
            self._draw_ring_gauge(FCX, FCY, r=band_inner_r, thickness=band_inner_th, pct=done_pct, col_hex=C_ACC)
            total_all = pending + running + done + failed + cancelled
            self._draw_ring_label(
                FCX,
                FCY,
                r=band_inner_r,
                thickness=band_inner_th,
                angle_deg=270,
                title=f"COMP {done_pct:.0f}%",
                subtitle=f"TOT {total_all}",
                col_hex=C_ACC,
            )

            self._draw_ring_label(FCX, FCY, r=band_outer_r, thickness=band_outer_th, angle_deg=140, title=f"RUN {running}", subtitle="active", col_hex=C_WARN)
            self._draw_ring_label(FCX, FCY, r=band_outer_r, thickness=band_outer_th, angle_deg=40, title=f"PEND {pending}", subtitle="queued", col_hex=C_PRI)
            self._draw_ring_label(FCX, FCY, r=band_mid_r, thickness=band_mid_th, angle_deg=220, title=f"DONE {done}", subtitle="completed", col_hex=C_SUCCESS)
            self._draw_ring_label(FCX, FCY, r=band_mid_r, thickness=band_mid_th, angle_deg=320, title=f"FAIL {failed}", subtitle="errors", col_hex=C_ERR)

            top_goal = None
            try:
                running_tasks = [t for t in all_tasks if t.get("status") == "running" and t.get("goal")]
                if running_tasks:
                    top_goal = str(running_tasks[0].get("goal", ""))[:28]
            except Exception:
                pass

            slots_line = None
            try:
                active = int(getattr(queue, "_active_count", 0) or 0)
                maxc = int(getattr(queue, "_max_concurrent", 0) or 0)
                if maxc:
                    slots_line = f"SLOTS {active}/{maxc}  CANC {cancelled}"
            except Exception:
                pass

            self._draw_center_title(
                FCX,
                FCY,
                title="AGENT DASHBOARD",
                line1=f"RUN {running}  PEND {pending}  DONE {done}  FAIL {failed}",
                line2=slots_line,
                line3=(f"NOW: {top_goal}" if top_goal else None),
                col_hex=theme_col,
            )

        elif self.center_panel_id == "memory":
            facts = int(self.memory_stats.get("facts", 0) or 0)
            nodes = int(self.memory_stats.get("triplets", 0) or 0)

            mins = self.memory_stats.get("activity_mins", None)
            activity_txt = f"LAST {int(mins)}m" if isinstance(mins, int) else "LAST N/A"

            facts_pct = min(100.0, (facts / 50.0) * 100.0) if facts > 0 else 0.0
            nodes_pct = min(100.0, (nodes / 500.0) * 100.0) if nodes > 0 else 0.0
            act_pct = 0.0
            if isinstance(mins, int):
                act_pct = max(0.0, 100.0 - min(100.0, (mins / 60.0) * 100.0))

            self._draw_ring_gauge(FCX, FCY, r=band_outer_r, thickness=band_outer_th, pct=facts_pct, col_hex=C_PRI)
            self._draw_ring_gauge(FCX, FCY, r=band_mid_r, thickness=band_mid_th, pct=nodes_pct, col_hex=C_ACC)
            self._draw_ring_gauge(FCX, FCY, r=band_inner_r, thickness=band_inner_th, pct=act_pct if isinstance(mins, int) else None, col_hex=C_SEC)

            self._draw_ring_label(FCX, FCY, r=band_outer_r, thickness=band_outer_th, angle_deg=140, title=f"FACTS {facts}", subtitle="long-term", col_hex=C_PRI)
            self._draw_ring_label(FCX, FCY, r=band_mid_r, thickness=band_mid_th, angle_deg=40, title=f"NODES {nodes}", subtitle="graph", col_hex=C_ACC)
            self._draw_ring_label(FCX, FCY, r=band_inner_r, thickness=band_inner_th, angle_deg=270, title=activity_txt, subtitle="activity", col_hex=C_SEC)

            size_line = None
            lt_kb = self.memory_stats.get("lt_kb", None)
            kg_mb = self.memory_stats.get("kg_mb", None)
            if isinstance(lt_kb, (int, float)) or isinstance(kg_mb, (int, float)):
                lt = float(lt_kb or 0.0)
                kg = float(kg_mb or 0.0)
                if lt or kg:
                    size_line = f"LT {lt:.0f}KB  KG {kg:.1f}MB"

            id_n = int(self.memory_stats.get("facts_identity", 0) or 0)
            pref_n = int(self.memory_stats.get("facts_preferences", 0) or 0)
            rel_n = int(self.memory_stats.get("facts_relationships", 0) or 0)
            notes_n = int(self.memory_stats.get("facts_notes", 0) or 0)
            breakdown = None
            if facts:
                breakdown = f"ID {id_n}  PR {pref_n}  RL {rel_n}  NT {notes_n}"

            self._draw_center_title(
                FCX,
                FCY,
                title="NEURAL LINK",
                line1=f"FACTS {facts}  NODES {nodes}",
                line2=(size_line or activity_txt),
                line3=(breakdown or None),
                col_hex=theme_col,
            )

    def _draw(self):
        print("[TRACE] _draw called")
        c, t = self.bg, self.tick
        W, H = (320, 240) if self.compact_mode else (self.W, self.H)
        FCX, FCY, FW = (W // 2, 70, 120) if self.compact_mode else (self.FCX, self.FCY, self.FACE_SZ)
        c.delete("all")
        # Reset panel items so they are recreated each frame (avoid stale IDs)
        for panel in self.expandable_panels.values():
            panel.canvas_items = []

        # --- BACKGROUND GRADIENT & FIELD ---
        if not self.compact_mode:
            # Subtle vertical gradient simulation
            steps = 12
            sh = H // steps
            for i in range(steps):
                alpha = i / (steps - 1)
                r1, g1, b1 = int(C_BG_TOP[1:3], 16), int(C_BG_TOP[3:5], 16), int(C_BG_TOP[5:7], 16)
                r2, g2, b2 = int(C_BG_BOT[1:3], 16), int(C_BG_BOT[3:5], 16), int(C_BG_BOT[5:7], 16)
                curr_col = f"#{int(r1+(r2-r1)*alpha):02x}{int(g1+(g2-g1)*alpha):02x}{int(b1+(b2-b1)*alpha):02x}"
                c.create_rectangle(0, i*sh, W, (i+1)*sh, fill=curr_col, outline="")
            
            # Faint Grid lines
            gcol = self._ac(79, 209, 255, 15) # Soft cyan
            for x in range(0, W, 60): c.create_line(x, 0, x, H, fill=gcol)
            for y in range(0, H, 60): c.create_line(0, y, W, y, fill=gcol)
        else:
            # Simple border for compact mode
            c.create_rectangle(0, 0, W-1, H-1, outline=C_GLASS_BORDER, width=1)

        # --- STATE & THEME ENGINE ---
        if self.speaking: 
            state, pri, sec, tr, tg, tb = "SPEAKING", C_PRI, C_SEC, 79, 209, 255
        elif self.active_tasks:
            state, pri, sec, tr, tg, tb = "EXECUTING", C_SEC, C_PRI, 166, 108, 255
        elif self.speech_mode:
            state, pri, sec, tr, tg, tb = "LISTENING", C_PRI, C_SEC, 79, 209, 255
        else:
            state, pri, sec, tr, tg, tb = "IDLE", C_PRI, C_SEC, 79, 209, 255
        
        # --- BACKGROUND EFFECTS ---
        if not self.compact_mode:
            if state in ["SPEAKING", "EXECUTING"]:
                for x, y, s, char in self.data_stream:
                    c.create_text(x, y, text=char, fill=self._ac(tr, tg, tb, 80), font=("Courier", 8))
            else:
                rad = math.radians(self.radar_angle)
                c.create_line(FCX, FCY, FCX + W * math.cos(rad), FCY + W * math.sin(rad), fill=self._ac(tr, tg, tb, 30), width=1)

        # --- LEFT PANELS (Expandable) ---
        if not self.compact_mode:
            # Static logs panel (can be toggled via preferences)
            if self.show_logs_panel:
                hx, hy, hw = W - 240, 100, 210
                self._draw_glass_panel(hx - 10, hy - 30, hw + 20, 120, "SYSTEM LOGS")
                for i, (tag, txt) in enumerate(list(self.history_stack)):
                    alpha = int(70 + (i / len(self.history_stack)) * 185)
                    lcol = self._ac(tr, tg, tb, alpha) if tag == "ai" else self._ac(203, 239, 255, alpha)
                    if tag == "sys": lcol = self._ac(166, 108, 255, alpha)
                    c.create_text(hx, hy + 10 + i * 18, text=f"◈ {txt[:32]}", fill=lcol, font=("Courier", 8), anchor="w")

        # --- QUICK COMMANDS ---
        if not self.compact_mode:
            bx, by, bw, bh = 24, H - 155, 140, 26
            c.create_text(bx, by - 15, text="OPERATIONS", fill=C_SEC, font=("Courier", 8, "bold"), anchor="w")
            for i, cmd in enumerate(["SCREENSHOT", "WEB SEARCH", "EXPLAIN", "NEW TASK"]):
                yy = by + i * 32
                # Hover effect: brighter border and fill
                is_hovered = (self._hovered_button == f"quick_{i}")
                border_col = C_PRI if is_hovered else C_GLASS_BORDER
                fill_col = C_DIM if is_hovered else C_GLASS_BG
                c.create_rectangle(bx, yy, bx + bw, yy + bh, outline=border_col, fill=fill_col, width=2 if is_hovered else 1)
                c.create_text(bx + bw//2, yy + bh//2, text=cmd, fill=C_TEXT_PRI, font=("Courier", 7, "bold"))
                c.create_line(bx, yy, bx+4, yy, fill=C_ACC, width=2)
                c.create_line(bx, yy, bx, yy+4, fill=C_ACC, width=2)
            # PREFERENCES Button
            pby = by + 32 * 4 + 6
            pref_col = C_WARN if self.dream_mode_active else C_PRI
            is_hovered_pref = (self._hovered_button == "preferences")
            pref_border = C_PRI if is_hovered_pref else C_GLASS_BORDER
            pref_fill = C_DIM if is_hovered_pref else C_GLASS_BG
            c.create_rectangle(bx, pby, bx + bw, pby + bh, outline=pref_border, fill=pref_fill, width=2 if is_hovered_pref else 1)
            c.create_text(bx + bw//2, pby + bh//2, text="PREFERENCES", fill=pref_col, font=("Courier", 7, "bold"))
            c.create_line(bx, pby, bx+4, pby, fill=pref_col, width=2)
            c.create_line(bx, pby, bx, pby+4, fill=pref_col, width=2)
        # --- CORE ---
        if self.compact_mode:
            orb_r = int(FW * 0.3 * self.scale)
            c.create_oval(FCX-orb_r, FCY-orb_r, FCX+orb_r, FCY+orb_r, outline=C_PRI, width=2)
        else:
            for idx in range(3):
                rf, wr, al, gp = [(0.48, 2, 120, 60), (0.40, 1, 80, 40), (0.32, 1, 60, 30)][idx]
                rr, ba = int(FW * rf), self.rings_spin[idx]
                rcol_base = C_PRI if idx % 2 == 0 else C_SEC
                r, g, b = int(rcol_base[1:3], 16), int(rcol_base[3:5], 16), int(rcol_base[5:7], 16)
                rcol = self._ac(r, g, b, max(0, min(255, int(self.halo_a * (1.0 - idx * 0.2)))))
                for s in range(360 // (al + gp)):
                    c.create_arc(FCX-rr, FCY-rr, FCX+rr, FCY+rr, start=(ba + s * (al + gp)) % 360, extent=al, outline=rcol, width=wr, style="arc")
            for pr in self.pulse_r:
                pa = max(0, int(130 * (1.0 - pr / (FW * 0.75))))
                c.create_oval(FCX-int(pr), FCY-int(pr), FCX+int(pr), FCY+int(pr), outline=self._ac(tr, tg, tb, pa), width=1)
            if self._has_face:
                if self._face_scale_cache is None or abs(self._face_scale_cache[0] - self.scale) > 0.004:
                    self._face_scale_cache = (self.scale, ImageTk.PhotoImage(self._face_pil.resize((int(FW * self.scale), int(FW * self.scale)), Image.BILINEAR)))
                c.create_image(FCX, FCY, image=self._face_scale_cache[1])
            glow_r = int(FW * 0.15 * self.scale)
            c.create_oval(FCX-glow_r, FCY-glow_r, FCX+glow_r, FCY+glow_r, outline=self._ac(tr, tg, tb, 50), width=3)

        # --- STATUS & MIC ---
        if not self.compact_mode:
            sy = FCY + FW // 2 + 50
            c.create_text(W // 2, sy, text=f"• {state} •", fill=pri, font=("Courier", 12, "bold"))
            if self.speech_mode:
                mx, my, mw, mh = W // 2 - 70, sy + 30, 140, 12
                c.create_rectangle(mx, my, mx + mw, my + mh, outline=C_GLASS_BORDER, fill=C_GLASS_BG)
                for i in range(14):
                    h = int((random.random() * 0.6 + 0.4) * self.mic_level * mh) if self.speaking else int(math.sin(t*0.25 + i)*2 + 4)
                    c.create_rectangle(mx + i*10 + 2, my + mh - h, mx + i*10 + 8, my + mh, fill=C_ACC if h > 3 else C_DIM, outline="")
        else:
            # Compact Mode Status & Context
            sy = FCY + 65
            c.create_text(W // 2, sy, text=f"• {state} •", fill=pri, font=("Courier", 10, "bold"))
            
            # Simplified Env Context for Compact Mode
            cy = sy + 25
            ctx_text = f"APP: {self.env_context.get('active_app', 'N/A')[:12]} | PRJ: {self.env_context.get('project', 'None')[:12]}"
            c.create_text(W // 2, cy, text=ctx_text, fill=C_TEXT_PRI, font=("Courier", 8))
            c.create_text(W // 2, cy + 18, text=f"FOCUS: {self.env_context.get('focus_time_minutes', 0)} MIN | {self.env_context.get('time_of_day', 'Morning').upper()}", fill=C_ACC, font=("Courier", 8))

            # Compact Mic Toggle Visual
            # Coordinates sync with click handler: bx=110, by=195, bw=100, bh=22
            btn_w, btn_h = 100, 22
            bx, by = (W - btn_w) // 2, H - 45
            c.create_rectangle(bx, by, bx + btn_w, by + btn_h, outline=C_PRI if self.speech_mode else C_DIM, fill=C_GLASS_BG)
            c.create_text(W // 2, by + btn_h // 2, text="MIC: ON" if self.speech_mode else "MIC: OFF", fill=C_TEXT_PRI, font=("Courier", 8, "bold"))

        footer_y = H - 28
        if not self.compact_mode:
            c.create_rectangle(0, footer_y, W, H, fill=C_BG_BOT, outline="")
            c.create_line(0, footer_y, W, footer_y, fill=C_GLASS_BORDER, width=1)
            c.create_text(W // 2, H - 14, fill=C_TEXT_SEC, font=("Courier", 8), text="CRISTINE HOLOGRAPHIC INTERFACE  ·  v2.5  ·  QUANTUM ENCRYPTION ACTIVE")
        else:
            c.create_text(W // 2, H - 10, fill=C_TEXT_SEC, font=("Courier", 6), text="CRISTINE MINI-HUD [HOLOGRAPHIC]")

        # --- EXPANDABLE PANELS (drawn last to appear on top of all other elements) ---
        if not self.compact_mode:
            self._draw_radial_info(FCX, FCY, FW, t)
            for pid in ["system_monitor", "agent", "memory", "tasks"]:
                panel = self.expandable_panels.get(pid)
                if not panel:
                    continue
                radial_supported = {"system_monitor", "agent", "memory"}
                if panel.panel_id in radial_supported:
                    # Keep radial panels compact; detail renders in the center HUD rings.
                    panel.is_expanded = False
                    panel.current_h = panel.collapsed_h
                    panel.current_w = panel.collapsed_w
                    panel.is_selected = (panel.panel_id == self.center_panel_id)
                else:
                    panel.is_selected = False
                panel.draw(c)

    def start_speaking(self):
        self.speaking, self.status_text = True, "SPEAKING"
        self.log_frame.configure(highlightbackground=C_PRI)
        self.input_entry.configure(highlightbackground=C_PRI, highlightcolor=C_SEC)
        self.mode_btn.configure(bg=C_SEC, fg=C_BG_TOP)

    def stop_speaking(self):
        self.speaking, self.status_text = False, "ONLINE"
        self.log_frame.configure(highlightbackground=C_GLASS_BORDER)
        self.input_entry.configure(highlightbackground=C_GLASS_BORDER, highlightcolor=C_PRI)
        self.mode_btn.configure(bg=C_DIM, fg=C_TEXT_PRI)

    def _api_keys_exist(self):
        """Check if API key file exists AND has a non-empty key"""
        if not API_FILE.exists():
            return False
        try:
            with open(API_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                key = data.get("gemini_api_key", "").strip()
                return bool(key)  # Only return True if key is not empty
        except (json.JSONDecodeError, IOError):
            return False
    def wait_for_api_key(self):
        """Blocks until API key is ready (either loaded from file or entered by user)"""
        self._api_key_ready.wait()
    def _show_setup_ui(self):
        self.setup_frame = tk.Frame(self.root, bg=C_BG_TOP, highlightbackground=C_PRI, highlightthickness=1)
        self.setup_frame.place(relx=0.5, rely=0.5, anchor="center")
        self.setup_frame.tkraise()  # Bring frame above canvas
        tk.Label(self.setup_frame, text="◈  INITIALISATION REQUIRED", fg=C_PRI, bg=C_BG_TOP, font=("Courier", 13, "bold")).pack(pady=(18, 4))
        tk.Label(self.setup_frame, text="Enter your Gemini API key to boot CRISTINE.", fg=C_TEXT_SEC, bg=C_BG_TOP, font=("Courier", 9)).pack(pady=(0, 10))
        tk.Label(self.setup_frame, text="GEMINI API KEY", fg=C_DIM, bg=C_BG_TOP, font=("Courier", 9)).pack(pady=(8, 2))
        self.gemini_entry = tk.Entry(self.setup_frame, width=52, fg=C_TEXT_PRI, bg=C_DIMMER, insertbackground=C_TEXT_PRI, borderwidth=0, font=("Courier", 10), show="*")
        self.gemini_entry.pack(pady=(0, 4))
        tk.Button(self.setup_frame, text="▸  INITIALISE SYSTEMS", command=self._save_api_keys_and_complete_setup, bg=C_BG_TOP, fg=C_PRI, activebackground=C_DIM, activeforeground=C_PRI, font=("Courier", 10), borderwidth=0, pady=8).pack(pady=14)
        self.gemini_entry.focus()  # Focus on entry field
    def _save_api_keys_and_complete_setup(self):
        gemini = self.gemini_entry.get().strip()
        if not gemini: return
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(API_FILE, "w", encoding="utf-8") as f: json.dump({"gemini_api_key": gemini}, f, indent=4)
        self.setup_frame.destroy()
        self._complete_setup()
    def _complete_setup(self):
        self.status_text = "ONLINE"
        self.write_log("Systems initialised. CRISTINE online.", tag="sys")
        self._api_key_ready.set()  # Signal that API key is ready
