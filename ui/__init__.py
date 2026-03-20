import os, json, time, math, random, threading
import tkinter as tk
from collections import deque
from PIL import Image, ImageTk, ImageDraw
import sys
from pathlib import Path
import psutil
from actions.context_monitor import monitor as context_monitor
from threading import Event
from .preferences_window import PreferencesWindow
from memory.task_manager import get_task_manager
from agent.task_queue import get_queue
from .command_palette import CommandPalette, ensure_routines_file

def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE = CONFIG_DIR / "api_keys.json"

SYSTEM_NAME, MODEL_BADGE = "CRISTINE", "Cristine"
C_BG_TOP, C_BG_BOT = "#03060A", "#0A1220"
C_PRI, C_SEC, C_ACC = "#4FD1FF", "#A66CFF", "#52FFA8"
C_GLASS_BG = "#0D1B2E"
C_GLASS_BORDER = "#3A5A7E"
C_TEXT_PRI, C_TEXT_SEC = "#CBEFFF", "#7FAAC9"
C_WARN, C_ERR, C_SUCCESS = "#FFB020", "#FF4A6E", "#52FFA8"
C_DIM, C_DIMMER = "#1B2D44", "#0D1520"

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

# Subtle depth layers (used for cards/panels)
C_GLASS_BG_L1 = _shade(C_GLASS_BG, 0.06)
C_GLASS_BG_L2 = _shade(C_GLASS_BG, 0.12)
C_EDGE_HI = _shade(C_GLASS_BORDER, 0.30)
C_EDGE_LO = _shade(C_DIMMER, -0.35)
C_PANEL_SHADOW = _shade(C_BG_TOP, -0.55)

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

        # Fade effect
        self.alpha = 0.7 + 0.3 * t

    def draw(self, canvas):
        """Render panel on canvas."""
        items = self.canvas_items
        x, y, w, h = int(self.current_x), int(self.current_y), int(self.current_w), int(self.current_h)

        if w < 10 or h < 10:
            return

        bg_color = C_GLASS_BG
        is_selected = bool(getattr(self, "is_selected", False))
        border_color = self.theme_color if is_selected else C_GLASS_BORDER
        title_color = self.theme_color if is_selected else C_SEC

        if len(items) == 0:
            # Create new items
            # Shadow (depth) layer
            items.append(canvas.create_rectangle(x + 3, y + 3, x + w + 3, y + h + 3, fill=C_PANEL_SHADOW, outline="", width=0))

            # Base surface
            items.append(canvas.create_rectangle(x, y, x + w, y + h, fill=bg_color, outline=border_color, width=1))

            # Subtle top "sheen" band (simulates light hitting the surface)
            sheen_h = min(26, max(18, int(h * 0.22)))
            items.append(canvas.create_rectangle(x + 1, y + 1, x + w - 1, y + sheen_h, fill=C_GLASS_BG_L1, outline="", width=0))

            # Edge lighting: highlight top/left, shadow bottom/right
            items.append(canvas.create_line(x + 1, y + 1, x + w - 1, y + 1, fill=C_EDGE_HI, width=1))
            items.append(canvas.create_line(x + 1, y + 1, x + 1, y + h - 1, fill=C_EDGE_HI, width=1))
            items.append(canvas.create_line(x + 1, y + h - 1, x + w - 1, y + h - 1, fill=C_EDGE_LO, width=1))
            items.append(canvas.create_line(x + w - 1, y + 1, x + w - 1, y + h - 1, fill=C_EDGE_LO, width=1))

            # HUD accent lines
            items.append(canvas.create_line(x, y, x + w, y, fill=(self.theme_color if is_selected else C_PRI), width=1))
            items.append(canvas.create_line(x, y, x, y + 20, fill=(self.theme_color if is_selected else C_PRI), width=2))

            # Title + divider (kept stable to avoid index drift)
            items.append(canvas.create_text(x + 10, y + 12, text=self.title or "", fill=title_color,
                                           font=("Courier", 9, "bold"), anchor="w"))
            items.append(canvas.create_line(x + 5, y + 22, x + w - 5, y + 22, fill=border_color, width=1))

            # Content area (must be before close button)
            content_item = canvas.create_text(x + 10, y + 35, text="", fill=C_TEXT_PRI,
                                              font=("Courier", 8), anchor="nw", width=w - 20)
            items.append(content_item)
            self.text_item = content_item  # Store reference for later updates

            # Close button
            self._create_close_button(canvas, x, y, w, h, items)
            # Set initial close button visibility
            self._update_close_button(canvas, x, y, w, h)
        else:
            # Update existing items
            if len(items) >= 12:
                # Shadow
                canvas.coords(items[0], x + 3, y + 3, x + w + 3, y + h + 3)

                # Surface
                canvas.coords(items[1], x, y, x + w, y + h)
                canvas.itemconfig(items[1], fill=bg_color, outline=border_color)

                # Sheen band
                sheen_h = min(26, max(18, int(h * 0.22)))
                canvas.coords(items[2], x + 1, y + 1, x + w - 1, y + sheen_h)
                canvas.itemconfig(items[2], fill=C_GLASS_BG_L1)

                # Edge lighting
                canvas.coords(items[3], x + 1, y + 1, x + w - 1, y + 1)
                canvas.coords(items[4], x + 1, y + 1, x + 1, y + h - 1)
                canvas.coords(items[5], x + 1, y + h - 1, x + w - 1, y + h - 1)
                canvas.coords(items[6], x + w - 1, y + 1, x + w - 1, y + h - 1)
                canvas.itemconfig(items[3], fill=C_EDGE_HI)
                canvas.itemconfig(items[4], fill=C_EDGE_HI)
                canvas.itemconfig(items[5], fill=C_EDGE_LO)
                canvas.itemconfig(items[6], fill=C_EDGE_LO)

                # Accent lines
                accent_col = self.theme_color if is_selected else C_PRI
                canvas.coords(items[7], x, y, x + w, y)
                canvas.itemconfig(items[7], fill=accent_col)
                canvas.coords(items[8], x, y, x, y + 20)
                canvas.itemconfig(items[8], fill=accent_col)

                # Title/divider
                canvas.coords(items[9], x + 10, y + 12)
                canvas.itemconfig(items[9], text=self.title or "", fill=title_color)
                canvas.coords(items[10], x + 5, y + 22, x + w - 5, y + 22)
                canvas.itemconfig(items[10], fill=border_color)

            # Update close button
            self._update_close_button(canvas, x, y, w, h)
            # Update content item position and size
            if self.text_item is not None:
                canvas.coords(self.text_item, x + 10, y + 35)
                canvas.itemconfig(self.text_item, width=w - 20)

        # Render content based on state
        if self.text_item is not None:
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
        # (Without this, background/grid lines can draw over panel surfaces.)
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
        """Update close button position and visibility."""
        if not self.close_items:
            return
        bg_id, line1_id, line2_id = self.close_items
        btn_size = 16
        btn_x = x + w - btn_size - 8
        btn_y = y + 8
        canvas.coords(bg_id, btn_x, btn_y, btn_x + btn_size, btn_y + btn_size)
        canvas.coords(line1_id, btn_x + 4, btn_y + 4, btn_x + btn_size - 4, btn_y + btn_size - 4)
        canvas.coords(line2_id, btn_x + btn_size - 4, btn_y + 4, btn_x + 4, btn_y + btn_size - 4)
        self.close_button_rect = (btn_x, btn_y, btn_x + btn_size, btn_y + btn_size)
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
        if not self.close_button_rect:
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

# ----------------------------------------------------------------------------
# PANEL CONTENT RENDERERS
# ----------------------------------------------------------------------------

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
    # Courier 8 is roughly ~6-7px/char; be conservative.
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
    """Expanded system monitor."""
    ui = getattr(render_system_monitor, 'ui', None)
    if not ui:
        return
    stats = ui.system_stats
    cpu = stats.get('cpu', 0)
    ram = stats.get('ram', 0)
    bat = stats.get('bat', 0)
    plugged = stats.get('plugged', False)

    lines: list[str] = []
    physical = psutil.cpu_count(logical=False) or 0
    logical = psutil.cpu_count() or 0

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
    """Collapsed widget."""
    ui = getattr(render_system_monitor_collapsed, 'ui', None)
    if not ui:
        canvas.itemconfig(text_item, text="NO DATA")
        return
    stats = ui.system_stats
    cpu = stats.get('cpu', 0)
    ram = stats.get('ram', 0)
    bat = stats.get('bat', 0)
    text = f"CPU:{cpu:3.0f}%  RAM:{ram:3.0f}%  BAT:{bat:3.0f}%"
    canvas.itemconfig(text_item, text=text, anchor="center", font=("Courier", 8))
    canvas.coords(text_item, x + w//2, y + h//2)

def render_task_manager(canvas, x, y, w, h, text_item):
    """Expanded task manager."""
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
    """Collapsed task widget."""
    task_mgr = get_task_manager()
    tasks = task_mgr.get_all_tasks()
    pending = [t for t in tasks if t['status'] == 'pending']
    text = f"TASKS: {len(pending)} PENDING"
    canvas.itemconfig(text_item, text=text, anchor="center", font=("Courier", 8))
    canvas.coords(text_item, x + w//2, y + h//2)

def render_memory_viewer(canvas, x, y, w, h, text_item):
    """Expanded memory viewer."""
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
        snippets = ["(stored in long_term.json)", "(open memory viewer for details)"]
        lines.extend(snippets)
    else:
        lines.append("No facts stored yet")
    lines.append("")
    lines.append("Search: Ctrl+F")
    canvas.itemconfig(text_item, text=_fit_panel_lines(lines, w))

def render_memory_viewer_collapsed(canvas, x, y, w, h, text_item):
    """Collapsed memory widget."""
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

def render_command_core(canvas, x, y, w, h, text_item):
    """Expanded command hub (tool history, rerun, and palette hint)."""
    ui = getattr(render_command_core, "ui", None)
    lines: list[str] = ["COMMAND CORE", ""]

    last = getattr(ui, "_last_tool_run", None) if ui else None
    if isinstance(last, dict) and last.get("tool"):
        lines.append(f"Last: {str(last.get('tool'))[:28]}")
    else:
        lines.append("Last: (none)")

    hist = list(getattr(ui, "_tool_run_history", []) or []) if ui else []
    if hist:
        # Show a short recent list (most recent first, de-duped).
        seen = set()
        recent: list[str] = []
        for rec in hist:
            t = str((rec or {}).get("tool") or "").strip()
            if not t or t in seen:
                continue
            seen.add(t)
            recent.append(t)
            if len(recent) >= 6:
                break
        if recent:
            lines.append("")
            lines.append("Recent:")
            for t in recent:
                lines.append(f"- {t}")

    lines.append("")
    lines.append("Palette: Ctrl+K")
    canvas.itemconfig(text_item, text=_fit_panel_lines(lines, w))


def render_command_core_collapsed(canvas, x, y, w, h, text_item):
    """Collapsed command hub."""
    ui = getattr(render_command_core_collapsed, "ui", None)
    hist = list(getattr(ui, "_tool_run_history", []) or []) if ui else []

    def _short_tool(name: str) -> str:
        parts = [p for p in (name or "").strip().split("_") if p]
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0][:8].upper()
        if len(parts) == 2:
            return (parts[0][:4] + " " + parts[1][:4]).upper()
        return "".join([p[0] for p in parts[:4]]).upper()

    a = ""
    b = ""
    if hist:
        seen = set()
        recents: list[str] = []
        for rec in hist:
            t = str((rec or {}).get("tool") or "").strip()
            if not t or t in seen:
                continue
            seen.add(t)
            recents.append(t)
            if len(recents) >= 2:
                break
        if recents:
            a = _short_tool(recents[0])
            if len(recents) > 1:
                b = _short_tool(recents[1])

    if a and b:
        text = f"RECENT: {a} • {b}\nCTRL+K"
    elif a:
        text = f"RECENT: {a}\nCTRL+K"
    else:
        text = "CTRL+K\nTOOL PALETTE"

    canvas.itemconfig(text_item, text=text, anchor="center", font=("Courier", 8, "bold"))
    canvas.coords(text_item, x + w // 2, y + h // 2)

class CristineUI:
    def __init__(self, face_path, size=None):
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
        self.panels = {"telemetry": True, "logs": True, "memory": True, "context": True, "tasks": True}
        self.expandable_panels = {}  # New expandable panel system
        self.last_stats_t, self.compact_mode, self.active_tasks = 0, False, {}
        self.DEBUG_PANELS = False  # Debug flag for panel positions
        self.task_stats = {"pending": 0, "completed": 0}
        self.task_panel_hovered = False
        self.task_add_input = ""
        self.task_panel_scroll_offset = 0
        self.history_stack, self._drag_data = deque(maxlen=5), {"x": 0, "y": 0}
        self._hovered_button = None
        self._hovered_panel = None
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
        self._command_palette = None
        self._last_tool_run = None  # used by command palette rerun
        self._tool_run_history = deque(maxlen=40)
        self.dream_mode_active = False
        self.center_panel_id = None  # Selected menu panel to show details in the center HUD
        
        # Initialize task manager
        from memory.task_manager import get_task_manager
        self.task_manager = get_task_manager()
        self._update_task_stats()

        # Initialize expandable panels
        self._initialize_panels()

        self.bg = tk.Canvas(self.root, width=W, height=H, bg=C_BG_TOP, highlightthickness=0)
        self.bg.place(x=0, y=0)
        self.bg.focus_set()  # Enable focus for keyboard input
        self.bg.bind("<Button-1>", self._on_canvas_click)
        self.bg.bind("<B1-Motion>", self._do_drag)
        self.bg.bind("<ButtonRelease-1>", self._on_mouse_release)
        self.bg.bind("<Motion>", self._on_canvas_motion)
        self.bg.bind("<Key>", self._on_canvas_key)
        self.root.bind("<Control-h>", lambda e: self.toggle_compact())
        self.root.bind("<Control-m>", lambda e: self.toggle_input_mode())
        self.root.bind("<Control-k>", lambda e: self.toggle_command_palette())
        
        self.log_frame = tk.Frame(self.root, bg=C_GLASS_BG, highlightbackground=C_GLASS_BORDER, highlightthickness=1)
        self.log_text = tk.Text(self.log_frame, fg=C_TEXT_PRI, bg=C_GLASS_BG, insertbackground=C_TEXT_PRI, 
                               borderwidth=0, wrap="word", font=("Courier", 10), padx=10, pady=6)
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")
        
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
        self._update_title()
        self._animate()
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Apply startup/tray prefs at launch (best-effort; safe no-ops on unsupported platforms).
        self._sync_startup_registration()
        self._sync_tray_state()
        if self.tray_enabled and self._start_minimized and self._api_keys_exist():
            self.root.after(200, self.root.withdraw)

        ensure_routines_file()

    def _layout_bottom_widgets(self):
        """Place chat log + input so they don't cover the left OPERATIONS column."""
        W, H = self.W, self.H

        # Left column is the OPERATIONS stack (bx=24, bw=140); reserve extra padding.
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
        self.mic_level = max(0.0, min(1.0, level))

    def _on_canvas_click(self, e):
        # Check for panel interactions first (top-most panels in reverse order)
        if not self.compact_mode:
            for panel in reversed(list(self.expandable_panels.values())):
                if panel.contains(e.x, e.y):
                    # Menu behavior: keep panels compact, show details in center HUD.
                    if panel.panel_id in {"system_monitor", "command_core", "memory"}:
                        self.center_panel_id = None if self.center_panel_id == panel.panel_id else panel.panel_id
                    return

        self._start_drag(e)

        if self.compact_mode:
            bx, by, bw, bh = 110, 195, 100, 22
            if bx <= e.x <= bx + bw and by <= e.y <= by + bh:
                self.toggle_input_mode()
                return
            return

        if not self.compact_mode:
            bx, by, bw, bh = 24, self.H - 265, 140, 26
            for i, cmd in enumerate(["SCREENSHOT", "WEB SEARCH", "EXPLAIN", "NEW TASK"]):
                yy = by + i * 32
                if bx <= e.x <= bx + bw and yy <= e.y <= yy + bh:
                    print(f"[UI] 🖱️ Quick Cmd Click: {cmd}")
                    mapping = {
                        "SCREENSHOT": "Please capture a screenshot of my screen.",
                        "WEB SEARCH": "Use your web search tool to find information about this.",
                        "EXPLAIN": "Analyze my screen and explain exactly what you see.",
                        "NEW TASK": "I have a new task for you to plan and execute."
                    }
                    if self.text_submit_callback: self.text_submit_callback(mapping[cmd])
                    return
            pbx, pby, pbw, pbh = 24, self.H - 265 + 32 * 4 + 6, 140, 26
            if pbx <= e.x <= pbx + pbw and pby <= e.y <= pby + pbh:
                print("[UI] 🖱️ Preferences Click")
                self.open_preferences()
                return

            # Note: Old panel toggles (telemetry, memory, context, logs) are deprecated
            # They are now controlled by clicking directly on the panels

            # Handle task panel interactions (when hovered/expanded)
            if self.task_panel_hovered and self.panels["tasks"]:
                self.bg.focus_set()  # Ensure canvas has focus for keyboard
                hx_orig, hy = self.W - 240, 100
                ty = hy + 150
                panel_w = 300
                
                # Reposition if needed
                panel_x = hx_orig
                if hx_orig + panel_w + 20 > self.W:
                    panel_x = self.W - panel_w - 30
                
                pending_tasks = self.task_manager.get_pending_tasks()
                completed_tasks = self.task_manager.get_completed_tasks()
                
                current_y = ty + 8
                task_spacing = 22
                
                # Check for checkbox clicks on pending tasks (TOGGLE COMPLETION)
                if pending_tasks:
                    current_y += 24  # Skip "PENDING ITEMS" header
                    for task in pending_tasks[:8]:
                        # Touch-friendly padding for hit areas
                        HIT_PADDING = 4
                        # Checkbox at panel_x + 10, current_y
                        if panel_x + 5 - HIT_PADDING <= e.x <= panel_x + 20 + HIT_PADDING and current_y - 10 - HIT_PADDING <= e.y <= current_y + 10 + HIT_PADDING:
                            print(f"[TASK] ✓ Marking complete: {task.task}")
                            self.task_manager.complete_task(task.id)
                            self._update_task_stats()
                            return
                        # Delete button at panel_x + panel_w - 18
                        if panel_x + panel_w - 25 - HIT_PADDING <= e.x <= panel_x + panel_w - 12 + HIT_PADDING and current_y - 8 - HIT_PADDING <= e.y <= current_y + 12 + HIT_PADDING:
                            print(f"[TASK] 🗑️ Deleting task: {task.task}")
                            self.task_manager.delete_task(task.id)
                            self._update_task_stats()
                            return
                        current_y += task_spacing
                
                # Check for checkbox clicks on completed tasks (TOGGLE BACK TO PENDING)
                if completed_tasks:
                    current_y += 28  # Skip "COMPLETED ITEMS" header
                    for task in completed_tasks[:5]:
                        # Touch-friendly padding for hit areas
                        HIT_PADDING = 4
                        # Checkbox at panel_x + 10, current_y
                        if panel_x + 5 - HIT_PADDING <= e.x <= panel_x + 20 + HIT_PADDING and current_y - 10 - HIT_PADDING <= e.y <= current_y + 10 + HIT_PADDING:
                            print(f"[TASK] ↩️ Marking pending: {task.task}")
                            self.task_manager.uncomplete_task(task.id)
                            self._update_task_stats()
                            return
                        # Delete button at panel_x + panel_w - 18
                        if panel_x + panel_w - 25 - HIT_PADDING <= e.x <= panel_x + panel_w - 12 + HIT_PADDING and current_y - 8 - HIT_PADDING <= e.y <= current_y + 12 + HIT_PADDING:
                            print(f"[TASK] 🗑️ Deleting task: {task.task}")
                            self.task_manager.delete_task(task.id)
                            self._update_task_stats()
                            return
                        current_y += task_spacing
                
                # Check for "Add task" button click
                input_y = current_y + 12
                input_h = 24
                if panel_x + panel_w - 32 <= e.x <= panel_x + panel_w - 8 and input_y <= e.y <= input_y + input_h:
                    if self.task_add_input.strip():
                        print(f"[TASK] ➕ Adding task: {self.task_add_input}")
                        self.task_manager.add_task(self.task_add_input)
                        self._update_task_stats()
                        self.task_add_input = ""
                    return

    def _on_canvas_motion(self, e):
        """Track mouse motion for panel hover and task panel detection."""
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

        # Check expandable panel hover first
        panel_hovered = False
        for panel in reversed(list(self.expandable_panels.values())):
            if panel.contains(e.x, e.y):
                self.root.config(cursor="hand2")
                self._hovered_panel = panel.panel_id
                panel_hovered = True
                break

        if panel_hovered:
            return

        # Task panel hover detection (existing)
        hx_orig, hy = self.W - 240, 100
        ty = hy + 150
        panel_w = 300
        panel_x = hx_orig
        if hx_orig + panel_w + 20 > self.W:
            panel_x = self.W - panel_w - 30
        task_x1, task_x2 = panel_x - 10, panel_x + panel_w + 10
        task_y1 = ty - 30
        pending = len(self.task_manager.get_pending_tasks())
        completed = len(self.task_manager.get_completed_tasks())
        items_shown = min(8, pending) + min(5, completed)
        base_h = 100
        task_spacing = 22
        expanded_h = min(420, base_h + items_shown * task_spacing + 60)
        task_y2 = task_y1 + expanded_h

        was_hovered = getattr(self, 'task_panel_hovered', False)
        self.task_panel_hovered = (task_x1 <= e.x <= task_x2 and task_y1 <= e.y <= task_y2)

        if self.task_panel_hovered:
            self.root.config(cursor="hand2")
            if not was_hovered:
                self.bg.focus_set()
        else:
            # Check quick command buttons hover
            bx, by, bw, bh = 24, self.H - 265, 140, 26
            hovered = False
            for i in range(4):
                yy = by + i * 32
                if bx - 8 <= e.x <= bx + bw + 8 and yy - 8 <= e.y <= yy + bh + 8:
                    self.root.config(cursor="hand2")
                    self._hovered_button = f"quick_{i}"
                    hovered = True
                    break
            if not hovered:
                pbx, pby, pbw, pbh = 24, self.H - 265 + 32 * 4 + 6, 140, 26
                if pbx - 8 <= e.x <= pbx + pbw + 8 and pby - 8 <= e.y <= pby + pbh + 8:
                    self.root.config(cursor="hand2")
                    self._hovered_button = "preferences"
                    hovered = True
            if not hovered:
                self.root.config(cursor="")
                self._hovered_button = None

    def _on_mouse_release(self, e):
        """Stop any panel dragging."""
        for panel in self.expandable_panels.values():
            if panel.is_dragging:
                panel.stop_drag()

    def _on_canvas_key(self, e):
        """Handle keyboard input for task panel when hovered"""
        if self.task_panel_hovered and self.panels["tasks"] and not self.compact_mode:
            if e.keysym == "Return":
                # Submit task on Enter
                if self.task_add_input.strip():
                    print(f"[TASK] ➕ Adding task via Enter: {self.task_add_input}")
                    self.task_manager.add_task(self.task_add_input)
                    self._update_task_stats()
                    self.task_add_input = ""
                    return "break"  # Consume event
            elif e.keysym == "BackSpace":
                # Delete last character
                if self.task_add_input:
                    self.task_add_input = self.task_add_input[:-1]
                    return "break"
            elif e.keysym == "Escape":
                # Clear input and unfocus
                self.task_add_input = ""
                return "break"
            elif len(e.char) == 1 and ord(e.char) >= 32:  # Printable characters
                # Add character to input (limit to ~40 chars for display)
                if len(self.task_add_input) < 40:
                    self.task_add_input += e.char
                    return "break"

    def _load_face(self, path):
        try:
            img = Image.open(path).convert("RGBA").resize((self.FACE_SZ, self.FACE_SZ), Image.LANCZOS)
            mask = Image.new("L", (self.FACE_SZ, self.FACE_SZ), 0)
            ImageDraw.Draw(mask).ellipse((2, 2, self.FACE_SZ-2, self.FACE_SZ-2), fill=255)
            img.putalpha(mask)
            self._face_pil, self._has_face = img, True
        except Exception: self._has_face = False

    def _load_preferences(self):
        prefs_path = BASE_DIR / "config" / "preferences.json"
        if prefs_path.exists():
            try:
                with open(prefs_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _on_preferences_changed(self, prefs):
        self.preferences = prefs
        if "interface_compact_mode" in prefs and prefs["interface_compact_mode"] != self.compact_mode:
            self.toggle_compact()
        # Update expandable panels
        for panel_id, panel in self.expandable_panels.items():
            pref_key = f"interface_panel_{panel_id}"
            if pref_key in prefs:
                panel.is_expanded = prefs[pref_key]
                panel.current_w = panel.expanded_w if panel.is_expanded else panel.collapsed_w
                panel.current_h = panel.expanded_h if panel.is_expanded else panel.collapsed_h
        # Backward compatibility: map old keys
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
        if self.DEBUG_PANELS:
            for pid, panel in self.expandable_panels.items():
                print(f"[DEBUG] Panel {pid}: pos=({panel.current_x},{panel.current_y}) size={int(panel.current_w)}x{int(panel.current_h)} expanded={panel.is_expanded}")

    def open_preferences(self, section: str | None = None):
        if self.preferences_window is None:
            self.preferences_window = PreferencesWindow(
                self.root,
                prefs_callback=self._on_preferences_changed,
                log_callback=self.write_log,
            )
        self.preferences_window.open(section=section)

    def toggle_command_palette(self):
        if self._command_palette is None:
            self._command_palette = CommandPalette(self)
        self._command_palette.toggle()

    def run_tool_from_palette(self, tool_name: str, params: dict, decl: dict | None = None):
        # Execute in a worker thread so the HUD stays responsive.
        self._last_tool_run = {"tool": tool_name, "params": dict(params or {})}
        try:
            self._tool_run_history.appendleft(dict(self._last_tool_run))
        except Exception:
            pass
        self.write_log(f"[palette] TOOL {tool_name}  {json.dumps(params, ensure_ascii=True)}", tag="sys")

        def worker():
            result = ""
            try:
                result = _palette_call_tool(tool_name, params, ui=self)
            except Exception as e:
                result = f"Error: {str(e)[:200]}"
            try:
                self.write_log(result if result else "Done.", tag="sys")
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def run_feature_diagnostics(self, mode: str = "smoke") -> None:
        mode = (mode or "smoke").strip().lower()
        self.write_log(f"[diag] Starting diagnostics ({mode})...", tag="sys")

        def worker():
            try:
                from system.feature_diagnostics import run_feature_diagnostics

                report = run_feature_diagnostics(
                    tool_runner=lambda name, p: _palette_call_tool(str(name), dict(p or {}), ui=self),
                    log=lambda m: self.write_log(str(m), tag="sys"),
                    prefs=dict(getattr(self, "preferences", {}) or {}),
                    mode=mode,
                )

                # Persist report to disk for sharing/debugging.
                try:
                    p = BASE_DIR / "memory" / "diagnostics_report.json"
                    p.parent.mkdir(parents=True, exist_ok=True)
                    with open(p, "w", encoding="utf-8") as f:
                        json.dump(report, f, indent=2)
                    self.write_log(f"[diag] Saved report: {str(p)}", tag="sys")
                except Exception:
                    pass

                # Print a compact summary list of failures.
                fails = [r for r in (report.get("results") or []) if isinstance(r, dict) and r.get("status") == "FAIL"]
                if fails:
                    self.write_log("[diag] FAILURES:", tag="sys")
                    for r in fails[:20]:
                        self.write_log(f"  - {r.get('tool')}: {str(r.get('message') or '')[:140]}", tag="sys")
                else:
                    self.write_log("[diag] No failures detected in this mode.", tag="sys")
            except Exception as e:
                self.write_log(f"[diag] Diagnostics crashed: {str(e)[:200]}", tag="sys")

        threading.Thread(target=worker, daemon=True).start()

    def run_routine_from_palette(self, routine: dict | None):
        if not routine:
            self.write_log("[palette] Routine not found.", tag="sys")
            return
        name = str(routine.get("name") or routine.get("id") or "ROUTINE")
        steps = routine.get("steps") or routine.get("tool_calls") or []
        if not isinstance(steps, list):
            self.write_log(f"[palette] Routine '{name}' is invalid.", tag="sys")
            return

        self.write_log(f"[palette] RUN ROUTINE: {name}", tag="sys")

        def worker():
            from tkinter import messagebox

            from system.automation_runner import run_steps_with_self_heal

            def log(msg: str) -> None:
                self.write_log(str(msg or ""), tag="sys")

            def tool_runner(tool: str, params: dict):
                # Keep history/Command Core in sync with routine tool runs (including retries).
                try:
                    self.record_tool_run(str(tool), dict(params or {}))
                except Exception:
                    pass
                return _palette_call_tool(str(tool), dict(params or {}), ui=self)

            def request_approval(plan: dict) -> bool:
                # Must run on the UI thread (Tk is not thread-safe).
                ev = threading.Event()
                out = {"ok": False}

                def _ui():
                    try:
                        reason = str(plan.get("reason") or "This automation requires approval.")
                        req_settings = []
                        for op in (plan.get("patch_ops") or []):
                            if isinstance(op, dict) and op.get("op") == "request_setting":
                                req_settings.append((str(op.get("key") or "").strip(), op.get("value")))

                        if any(k == "automation_allow_ui" for k, _v in req_settings):
                            msg = reason + "\n\nEnable 'Allow on-screen automation' now?"
                        else:
                            msg = reason + "\n\nApprove applying this repair and retry?"
                        ok = bool(messagebox.askyesno("Automation Approval", msg, parent=self.root))
                        if ok:
                            if req_settings:
                                prefs = dict(getattr(self, "preferences", {}) or {})
                                for k, v in req_settings:
                                    if k:
                                        prefs[k] = v
                                # Persist and re-apply.
                                try:
                                    prefs_path = BASE_DIR / "config" / "preferences.json"
                                    prefs_path.parent.mkdir(parents=True, exist_ok=True)
                                    with open(prefs_path, "w", encoding="utf-8") as f:
                                        json.dump(prefs, f, indent=2)
                                except Exception:
                                    pass
                                try:
                                    self._on_preferences_changed(prefs)
                                except Exception:
                                    pass
                        out["ok"] = ok
                    except Exception:
                        out["ok"] = False
                    finally:
                        ev.set()

                try:
                    self.root.after(0, _ui)
                except Exception:
                    return False

                ev.wait(timeout=180)
                return bool(out.get("ok", False))

            ok, patched_steps, report = run_steps_with_self_heal(
                steps,
                tool_runner=tool_runner,
                log=log,
                request_approval=request_approval,
                context={"routine": {"name": name}},
            )

            try:
                healed = int((report or {}).get("healed") or 0)
                persistable_success = bool((report or {}).get("persistable_success", False))
            except Exception:
                healed = 0
                persistable_success = False

            if healed:
                self.write_log(f"[palette] Self-heal applied {healed} fix(es).", tag="sys")

            if ok and persistable_success:
                # Ask to persist patched steps back into routines.json.
                ev = threading.Event()
                out = {"ok": False}

                def _ui_persist():
                    try:
                        out["ok"] = bool(messagebox.askyesno("Persist Fixes", f"Persist self-healing fixes to '{name}'?", parent=self.root))
                    except Exception:
                        out["ok"] = False
                    finally:
                        ev.set()

                try:
                    self.root.after(0, _ui_persist)
                    ev.wait(timeout=180)
                except Exception:
                    out["ok"] = False

                if out.get("ok"):
                    try:
                        routines_path = BASE_DIR / "memory" / "routines.json"
                        if not routines_path.exists():
                            routines_path.parent.mkdir(parents=True, exist_ok=True)
                            routines_path.write_text("[]\n", encoding="utf-8")
                        with open(routines_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        rid = str(routine.get("id") or "").strip()
                        rname = str(routine.get("name") or "").strip()
                        updated = False
                        if isinstance(data, list):
                            for r in data:
                                if not isinstance(r, dict):
                                    continue
                                if rid and str(r.get("id") or "").strip() == rid:
                                    key = "steps" if isinstance(r.get("steps"), list) else ("tool_calls" if isinstance(r.get("tool_calls"), list) else "steps")
                                    r[key] = patched_steps
                                    updated = True
                                    break
                                if not rid and rname and str(r.get("name") or "").strip() == rname:
                                    key = "steps" if isinstance(r.get("steps"), list) else ("tool_calls" if isinstance(r.get("tool_calls"), list) else "steps")
                                    r[key] = patched_steps
                                    updated = True
                                    break
                        if updated:
                            with open(routines_path, "w", encoding="utf-8") as f:
                                json.dump(data, f, indent=2)
                            self.write_log(f"[palette] Persisted fixes to routine '{name}'.", tag="sys")
                        else:
                            self.write_log("[palette] Could not locate routine to persist fixes.", tag="sys")
                    except Exception as e:
                        self.write_log(f"[palette] Persist failed: {str(e)[:160]}", tag="sys")

            if ok:
                self.write_log(f"[palette] Routine '{name}' completed.", tag="sys")
            else:
                self.write_log(f"[palette] Routine '{name}' stopped.", tag="sys")

        threading.Thread(target=worker, daemon=True).start()

    def record_tool_run(self, tool_name: str, params: dict | None = None):
        rec = {"tool": str(tool_name), "params": dict(params or {})}
        self._last_tool_run = dict(rec)
        try:
            self._tool_run_history.appendleft(dict(rec))
        except Exception:
            pass

    def _sync_startup_registration(self):
        try:
            from system.startup_manager import set_run_on_startup

            ok, msg = set_run_on_startup(
                bool(getattr(self, "_startup_enabled", False)),
                start_minimized=bool(getattr(self, "_start_minimized", False) and getattr(self, "tray_enabled", False)),
            )
            if ok:
                self.write_log(f"[startup] {msg}", tag="sys")
            else:
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
        # If tray icon is running, close hides to tray instead of exiting.
        if bool(getattr(self, "tray_enabled", False)) and getattr(self, "_tray_icon", None) is not None:
            try:
                self.root.withdraw()
                self.write_log("Cristine is still running in the tray.", tag="sys")
            except Exception:
                pass
            return
        self._quit_app()

    def _quit_app(self):
        # Hard-exit is intentional in this app (threads/audio/etc.).
        try:
            self._stop_tray_icon()
        except Exception:
            pass
        os._exit(0)

    def _initialize_panels(self):
        """Create expandable panels."""
        left_x = 24
        telemetry_y = 80
        # Menu stack on the left (no in-place expansion; details render in center HUD).
        stack_gap = 14

        collapsed_w = 180
        collapsed_h_small = 60
        expanded_h_large = 320

        system_y = telemetry_y - 10
        command_y = system_y + (collapsed_h_small + 20) + stack_gap
        memory_y = command_y + (collapsed_h_small + 20) + stack_gap
        memory_y = max(50, min(memory_y, self.H - (collapsed_h_small + 20) - 10))

        # Attach UI reference to renderers that need it
        render_system_monitor.ui = self
        render_system_monitor_collapsed.ui = self
        render_command_core.ui = self
        render_command_core_collapsed.ui = self

        # System Monitor Panel (replaces CORE TELEMETRY)
        system_panel = ExpandablePanel(
            panel_id="system_monitor",
            x=left_x - 10,
            y=system_y,
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

        # Command Core Panel (between telemetry and neural link)
        command_panel = ExpandablePanel(
            panel_id="command_core",
            x=left_x - 10,
            y=command_y,
            collapsed_w=collapsed_w + 20,
            collapsed_h=collapsed_h_small + 20,
            expanded_w=400,
            expanded_h=300,
            title="COMMAND CORE",
            theme_color=C_WARN,
            expanded_renderer=render_command_core,
            collapsed_renderer=render_command_core_collapsed
        )
        self.expandable_panels["command_core"] = command_panel

        # Memory Viewer Panel (replaces NEURAL LINK)
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

        # Force compact menu mode (details render in center HUD instead of expanding panels).
        for panel in self.expandable_panels.values():
            panel.is_expanded = False
            panel.current_h = panel.collapsed_h
            panel.current_w = panel.collapsed_w

        # Logs panel (legacy) - separate boolean
        prefs = self.preferences
        self.show_logs_panel = prefs.get("interface_panel_logs", True)

        # Debug: print panel positions if enabled
        if self.DEBUG_PANELS:
            for pid, panel in self.expandable_panels.items():
                print(f"[DEBUG] Panel {pid}: pos=({panel.current_x},{panel.current_y}) size={int(panel.current_w)}x{int(panel.current_h)} expanded={panel.is_expanded}")

    def _save_panel_preferences(self):
        """Save panel states to preferences."""
        try:
            prefs_path = BASE_DIR / "config" / "preferences.json"
            if prefs_path.exists():
                with open(prefs_path, "r", encoding="utf-8") as f:
                    prefs = json.load(f)
            else:
                prefs = {}
            for panel_id, panel in self.expandable_panels.items():
                prefs[f"interface_panel_{panel_id}"] = panel.is_expanded
            prefs["interface_panel_logs"] = getattr(self, 'show_logs_panel', True)
            with open(prefs_path, "w", encoding="utf-8") as f:
                json.dump(prefs, f, indent=2)
        except Exception as e:
            print(f"[UI] Failed to save panel preferences: {e}")

    @staticmethod
    def _ac(r, g, b, a):
        f = a / 255.0
        return f"#{int(r*f):02x}{int(g*f):02x}{int(b*f):02x}"

    def toggle_input_mode(self):
        self.speech_mode = not self.speech_mode
        self.mode_btn.configure(text="MIC: ON" if self.speech_mode else "MIC: OFF", bg=C_DIM if not self.speech_mode else C_SEC)
        self.write_log(f"SYS: Mode set to {'SPEECH' if self.speech_mode else 'TEXT'}", tag="sys")
        self._update_title()
        if not self.speech_mode: self.input_entry.focus_set()

    def _on_text_submit(self, event):
        txt = self.input_entry.get().strip()
        if txt:
            self.input_entry.delete(0, tk.END); self.write_log(txt, tag="you")
            if self.text_submit_callback: self.text_submit_callback(txt)

    def write_log(self, text: str, tag: str = "ai", is_stream: bool = False):
        # Tkinter is not thread-safe. Some actions run in background threads and
        # may call write_log; marshal onto the UI thread to avoid silent failures.
        try:
            if threading.current_thread() is not threading.main_thread():
                self.root.after(0, lambda t=text, tg=tag, s=is_stream: self.write_log(t, tag=tg, is_stream=s))
                return
        except Exception:
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
        if self.speaking:
            if t % 3 == 0: self.data_stream.append([random.randint(0, self.W), 0, random.randint(5, 12), random.choice("01ABCDEF")])
            self.data_stream = [[x, y + s, s, c] for x, y, s, c in self.data_stream if y < self.H]
        else:
            self.radar_angle = (self.radar_angle + 1.5) % 360
            if self.data_stream: self.data_stream.pop(0)
        if t % 40 == 0: self.status_blink = not self.status_blink
        if t % 8 == 0: self._update_title()
        if now - self.last_stats_t > 3.0: self._update_system_stats(); self._update_task_stats(); self.last_stats_t = now
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

            # Context monitor snapshot (active app, project, etc.)
            self.env_context = context_monitor.get_current_context()

            # --- Memory stats ---
            mem_path = Path(BASE_DIR) / "memory" / "long_term.json"
            db_path = Path(BASE_DIR) / "memory" / "knowledge_graph.db"

            mem_mtime = None
            kg_mtime = None

            # Long-term facts + breakdown
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
                # Keep keys stable for the radial renderer.
                self.memory_stats.setdefault("facts_identity", 0)
                self.memory_stats.setdefault("facts_preferences", 0)
                self.memory_stats.setdefault("facts_relationships", 0)
                self.memory_stats.setdefault("facts_notes", 0)

            # Knowledge graph triplets + db size
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

            # Recent memory activity (minutes since last write to either file)
            mt = 0.0
            for ts in (mem_mtime, kg_mtime):
                if ts:
                    mt = max(mt, float(ts))
            self.memory_stats["activity_mins"] = int((time.time() - mt) / 60) if mt else None

        except Exception:
            pass
    
    def _update_task_stats(self):
        """Update task counts from task manager and run cleanup"""
        try:
            self.task_stats["pending"] = len(self.task_manager.get_pending_tasks())
            self.task_stats["completed"] = len(self.task_manager.get_completed_tasks())
            
            # Auto-cleanup old tasks every 60 seconds
            import time
            if not hasattr(self, 'last_cleanup_t'):
                self.last_cleanup_t = time.time()
            
            now = time.time()
            if now - self.last_cleanup_t > 60:
                self.task_manager.cleanup_old_tasks()
                self.last_cleanup_t = now
        except Exception as e:
            print(f"[UI] Error updating task stats: {e}")

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
        self._update_title()

    def _start_drag(self, e):
        """Start dragging - either a panel or the window."""
        # Check if dragging an expanded panel
        if not self.compact_mode:
            for panel in reversed(list(self.expandable_panels.values())):
                if panel.contains(e.x, e.y) and panel.is_expanded:
                    panel.start_drag(e.x, e.y)
                    return
        # Otherwise, start window drag (or nothing)
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
        c.create_rectangle(x, y, x + w, y + h, fill=C_GLASS_BG, outline=C_GLASS_BORDER, width=1)
        c.create_line(x, y, x + w, y, fill=C_PRI, width=1)
        c.create_line(x, y, x, y + 20, fill=C_PRI, width=2)
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
        return 79, 209, 255  # fallback cyan

    @staticmethod
    def _polar_tk(cx: int, cy: int, r: float, deg: float) -> tuple[float, float]:
        """Tk-style polar: 0°=right, 90°=up, 180°=left, 270°=down."""
        rad = math.radians(deg)
        return cx + r * math.cos(rad), cy - r * math.sin(rad)

    def _draw_text(self, x: float, y: float, *, text: str, fill: str, font, anchor: str = "center"):
        # Simple shadow for readability on the radar background.
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
        # Soft glow + main stroke so the progress reads clearly over the ring art.
        self.bg.create_arc(bbox, start=90, extent=extent, style="arc", outline=glow, width=thickness + 2)
        self.bg.create_arc(bbox, start=90, extent=extent, style="arc", outline=fill, width=thickness)
        # End-cap marker helps the eye pick out the actual value quickly.
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

        # Marker dot on the ring band.
        mx, my = self._polar_tk(cx, cy, r + (thickness / 2.0) - 2.0, angle_deg)
        self.bg.create_oval(mx - 2, my - 2, mx + 2, my + 2, fill=col, outline="")

        # Text inside the band, anchored away from the center.
        lx, ly = self._polar_tk(cx, cy, r - (thickness / 2.0) + 8.0, angle_deg)
        anchor = "e" if math.cos(math.radians(angle_deg)) < 0 else "w"
        # Connector line helps associate label -> ring at a glance.
        self.bg.create_line(mx, my, lx, ly, fill=sub, width=1)
        self._draw_text(lx, ly - 6, text=title, fill=col, font=("Courier", 9, "bold"), anchor=anchor)
        if subtitle:
            self._draw_text(lx, ly + 8, text=subtitle, fill=sub, font=("Courier", 7, "bold"), anchor=anchor)

    def _draw_center_title(self, cx: int, cy: int, *, title: str, line1: str, line2: str | None, line3: str | None = None, col_hex: str):
        rr, gg, bb = self._hex_rgb(col_hex)
        tcol = self._ac(rr, gg, bb, 235)
        # 3-line center layout to anchor the widget visually without crowding the inner ring.
        self._draw_text(cx, cy - 18, text=title, fill=tcol, font=("Courier", 11, "bold"), anchor="center")
        self._draw_text(cx, cy + 2, text=line1, fill=C_TEXT_PRI, font=("Courier", 8, "bold"), anchor="center")
        if line2:
            self._draw_text(cx, cy + 18, text=line2, fill=C_TEXT_SEC, font=("Courier", 8), anchor="center")
        if line3:
            self._draw_text(cx, cy + 32, text=line3, fill=C_TEXT_SEC, font=("Courier", 7, "bold"), anchor="center")

    def _draw_radial_info(self, FCX: int, FCY: int, FW: int, tick: int):
        """Radial Information Expansion System: draw selected panel details along rings."""
        if self.compact_mode or not self.center_panel_id:
            return

        supported = {"system_monitor", "command_core", "memory"}
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

            # Visual gauges (distinct colors per ring/metric).
            self._draw_ring_gauge(FCX, FCY, r=band_outer_r, thickness=band_outer_th, pct=cpu, col_hex=C_PRI)
            self._draw_ring_gauge(FCX, FCY, r=band_mid_r, thickness=band_mid_th, pct=ram, col_hex=C_SEC)
            self._draw_ring_gauge(FCX, FCY, r=band_inner_r, thickness=band_inner_th, pct=bat if bat else None, col_hex=C_ACC)

            # Labels distributed around the circle for balance.
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

            # Center anchor label.
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

        elif self.center_panel_id == "command_core":
            hist = list(getattr(self, "_tool_run_history", []) or [])
            last = getattr(self, "_last_tool_run", None)

            def _short_tool(name: str) -> str:
                parts = [p for p in (name or "").strip().split("_") if p]
                if not parts:
                    return ""
                if len(parts) == 1:
                    return parts[0][:8].upper()
                if len(parts) == 2:
                    return (parts[0][:4] + " " + parts[1][:4]).upper()
                return "".join([p[0] for p in parts[:4]]).upper()

            def _hash32(s: str) -> int:
                h = 0
                for ch in (s or ""):
                    h = (h * 31 + ord(ch)) & 0xFFFFFFFF
                return h

            palette = [C_PRI, C_SEC, C_ACC, C_WARN]

            # Build: 8 most-recent unique tools + usage counts ("today" == since launch).
            recent: list[str] = []
            seen = set()
            counts: dict[str, int] = {}
            for rec in hist:
                t = str((rec or {}).get("tool") or "").strip()
                if not t:
                    continue
                counts[t] = counts.get(t, 0) + 1
                if t in seen:
                    continue
                seen.add(t)
                recent.append(t)
                if len(recent) >= 8:
                    break

            max_count = 1
            if recent:
                try:
                    max_count = max(1, max([counts.get(t, 0) for t in recent]))
                except Exception:
                    max_count = 1

            # OUTER RING: 8 recent tools (segment fill = usage frequency).
            slot = 45.0
            span = 32.0
            base = 90.0
            for i, tool in enumerate(recent):
                center = base - i * slot
                c = counts.get(tool, 0)
                prog = min(1.0, float(c) / float(max_count or 1))
                col = palette[_hash32(tool) % len(palette)]
                self._draw_ring_segment(
                    FCX,
                    FCY,
                    r=band_outer_r,
                    thickness=band_outer_th,
                    center_deg=center,
                    span_deg=span,
                    progress=prog,
                    col_hex=col,
                )
                rr2, gg2, bb2 = self._hex_rgb(col)
                tcol = self._ac(rr2, gg2, bb2, 235)
                tx, ty = self._polar_tk(FCX, FCY, band_outer_r, center)
                self._draw_text(
                    tx,
                    ty,
                    text=f"{_short_tool(tool)}\nx{c}",
                    fill=tcol,
                    font=("Courier", 7, "bold"),
                    anchor="center",
                )

            # MIDDLE RING: favorites (highlight if used recently).
            recent_set = set([str((r or {}).get("tool") or "").strip() for r in hist[:12]])
            favorites = [
                ("SCREEN", "computer_settings", C_ACC),
                ("SEARCH", "web_search", C_PRI),
                ("EXPLAIN", "screen_process", C_SEC),
                ("TASK", "add_task", C_WARN),
                ("OPEN", "open_app", C_TEXT_PRI),
            ]
            fav_slot = 72.0
            fav_span = 50.0
            for i, (label, tool_name, col) in enumerate(favorites):
                center = 90.0 - i * fav_slot
                prog = 1.0 if tool_name in recent_set else 0.25
                self._draw_ring_segment(
                    FCX,
                    FCY,
                    r=band_mid_r,
                    thickness=band_mid_th,
                    center_deg=center,
                    span_deg=fav_span,
                    progress=prog,
                    col_hex=col,
                )
                rr2, gg2, bb2 = self._hex_rgb(col)
                tcol = self._ac(rr2, gg2, bb2, 220)
                tx, ty = self._polar_tk(FCX, FCY, band_mid_r, center)
                self._draw_text(tx, ty, text=label, fill=tcol, font=("Courier", 7, "bold"), anchor="center")

            # INNER RING: toggles/status.
            toggles = [
                ("MIC", bool(getattr(self, "speech_mode", True)), C_PRI),
                ("TRAY", bool(getattr(self, "tray_enabled", False)), C_ACC),
                ("START", bool(getattr(self, "_startup_enabled", False)), C_WARN),
                ("DREAM", bool(getattr(self, "dream_mode_active", False)), C_SEC),
            ]
            tog_slot = 90.0
            tog_span = 66.0
            for i, (label, on, col) in enumerate(toggles):
                center = 45.0 - i * tog_slot
                self._draw_ring_segment(
                    FCX,
                    FCY,
                    r=band_inner_r,
                    thickness=band_inner_th,
                    center_deg=center,
                    span_deg=tog_span,
                    progress=1.0 if on else 0.0,
                    col_hex=col,
                )
                rr2, gg2, bb2 = self._hex_rgb(col if on else C_TEXT_SEC)
                tcol = self._ac(rr2, gg2, bb2, 210)
                tx, ty = self._polar_tk(FCX, FCY, band_inner_r, center)
                self._draw_text(
                    tx,
                    ty,
                    text=f"{label}\n{'ON' if on else 'OFF'}",
                    fill=tcol,
                    font=("Courier", 7, "bold"),
                    anchor="center",
                )

            # Center anchor label.
            last_tool = str(last.get("tool")) if isinstance(last, dict) and last.get("tool") else "(none)"
            last_tool_s = (last_tool or "").strip()
            if len(last_tool_s) > 24:
                last_tool_s = last_tool_s[:21] + "..."
            runs = len(hist)
            uniq = len(counts)
            top_tool = None
            top_n = 0
            try:
                for k, v in counts.items():
                    if v > top_n:
                        top_tool, top_n = k, v
            except Exception:
                pass

            self._draw_center_title(
                FCX,
                FCY,
                title="COMMAND CORE",
                line1=f"LAST {last_tool_s}",
                line2=f"RUNS {runs}  TOOLS {uniq}  CTRL+K",
                line3=(f"TOP {_short_tool(str(top_tool))} x{top_n}" if top_tool else None),
                col_hex=theme_col,
            )

        elif self.center_panel_id == "memory":
            facts = int(self.memory_stats.get("facts", 0) or 0)
            nodes = int(self.memory_stats.get("triplets", 0) or 0)

            # Recent activity: minutes since last write (computed in _update_system_stats).
            mins = self.memory_stats.get("activity_mins", None)
            activity_txt = f"LAST {int(mins)}m" if isinstance(mins, int) else "LAST N/A"

            facts_pct = min(100.0, (facts / 50.0) * 100.0) if facts > 0 else 0.0
            nodes_pct = min(100.0, (nodes / 500.0) * 100.0) if nodes > 0 else 0.0
            act_pct = 0.0
            if isinstance(mins, int):
                act_pct = max(0.0, 100.0 - min(100.0, (mins / 60.0) * 100.0))

            self._draw_ring_gauge(FCX, FCY, r=band_outer_r, thickness=band_outer_th, pct=facts_pct, col_hex=C_PRI)
            self._draw_ring_gauge(FCX, FCY, r=band_mid_r, thickness=band_mid_th, pct=nodes_pct, col_hex=C_ACC)
            self._draw_ring_gauge(FCX, FCY, r=band_inner_r, thickness=band_inner_th, pct=act_pct if mins is not None else None, col_hex=C_SEC)

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
        c, t = self.bg, self.tick
        W, H = (320, 240) if self.compact_mode else (self.W, self.H)
        FCX, FCY, FW = (W // 2, 70, 120) if self.compact_mode else (self.FCX, self.FCY, self.FACE_SZ)
        c.delete("all")
        # Reset panel items to force recreation each frame (avoid stale IDs)
        for panel in self.expandable_panels.values():
            panel.canvas_items = []
        if not self.compact_mode:
            steps = 12
            sh = H // steps
            for i in range(steps):
                alpha = i / (steps - 1)
                r1, g1, b1 = int(C_BG_TOP[1:3], 16), int(C_BG_TOP[3:5], 16), int(C_BG_TOP[5:7], 16)
                r2, g2, b2 = int(C_BG_BOT[1:3], 16), int(C_BG_BOT[3:5], 16), int(C_BG_BOT[5:7], 16)
                curr_col = f"#{int(r1+(r2-r1)*alpha):02x}{int(g1+(g2-g1)*alpha):02x}{int(b1+(b2-b1)*alpha):02x}"
                c.create_rectangle(0, i*sh, W, (i+1)*sh, fill=curr_col, outline="")
            gcol = self._ac(79, 209, 255, 15)
            for x in range(0, W, 60): c.create_line(x, 0, x, H, fill=gcol)
            for y in range(0, H, 60): c.create_line(0, y, W, y, fill=gcol)
        else:
            c.create_rectangle(0, 0, W-1, H-1, outline=C_GLASS_BORDER, width=1)
        if self.speaking: 
            state, pri, sec, tr, tg, tb = "SPEAKING", C_PRI, C_SEC, 79, 209, 255
        elif self.active_tasks:
            state, pri, sec, tr, tg, tb = "EXECUTING", C_SEC, C_PRI, 166, 108, 255
        elif self.speech_mode:
            state, pri, sec, tr, tg, tb = "LISTENING", C_PRI, C_SEC, 79, 209, 255
        else:
            state, pri, sec, tr, tg, tb = "IDLE", C_PRI, C_SEC, 79, 209, 255
        if not self.compact_mode:
            if state in ["SPEAKING", "EXECUTING"]:
                for x, y, s, char in self.data_stream:
                    c.create_text(x, y, text=char, fill=self._ac(tr, tg, tb, 80), font=("Courier", 8))
            else:
                rad = math.radians(self.radar_angle)
                c.create_line(FCX, FCY, FCX + W * math.cos(rad), FCY + W * math.sin(rad), fill=self._ac(tr, tg, tb, 30), width=1)
        if not self.compact_mode:
            hx, hy, hw = W - 240, 100, 210
            if self.panels["logs"]:
                self._draw_glass_panel(hx - 10, hy - 30, hw + 20, 120, "SYSTEM LOGS")
                for i, (tag, txt) in enumerate(list(self.history_stack)):
                    alpha = int(70 + (i / len(self.history_stack)) * 185)
                    lcol = self._ac(tr, tg, tb, alpha) if tag == "ai" else self._ac(203, 239, 255, alpha)
                    if tag == "sys": lcol = self._ac(166, 108, 255, alpha)
                    c.create_text(hx, hy + 10 + i * 18, text=f"◈ {txt[:32]}", fill=lcol, font=("Courier", 8), anchor="w")
            else:
                c.create_text(hx, hy - 20, text="▶ SYSTEM LOGS", fill=C_SEC, font=("Courier", 9, "bold"), anchor="w")
            # Tasks Panel
            ty = hy + 150
            if self.panels["tasks"]:
                if self.task_panel_hovered:
                    # Significantly expanded panel
                    pending_tasks = self.task_manager.get_pending_tasks()
                    completed_tasks = self.task_manager.get_completed_tasks()
                    total_tasks = len(pending_tasks) + len(completed_tasks)
                    
                    # MUCH larger expansion - up to 400px height, 300px width
                    panel_w = 300
                    base_h = 100
                    task_spacing = 22  # More spacing between tasks
                    items_shown = min(8, len(pending_tasks)) + min(5, len(completed_tasks))
                    panel_h = min(420, base_h + items_shown * task_spacing + 60)  # Much bigger!
                    
                    # REPOSITION panel to fit on screen (move left if would go off right edge)
                    panel_x = hx
                    if hx + panel_w + 20 > W:  # Would go off right edge
                        panel_x = W - panel_w - 30  # Shift left with padding
                    
                    # Draw glowing border effect
                    glow_col = self._ac(79, 209, 255, 30)
                    for glow_r in [6, 4, 2]:
                        c.create_rectangle(panel_x - 10 - glow_r, ty - 30 - glow_r, panel_x + panel_w + 10 + glow_r, ty - 30 + panel_h + glow_r, 
                                         outline=glow_col, width=1)
                    
                    # Draw main panel
                    self._draw_glass_panel(panel_x - 10, ty - 30, panel_w + 20, panel_h, "TODAY'S TASKS")
                    
                    current_y = ty + 8
                    
                    # Draw pending tasks
                    if pending_tasks:
                        c.create_text(panel_x + 5, current_y, text="PENDING ITEMS", fill=C_PRI, font=("Courier", 9, "bold"), anchor="w")
                        current_y += 24
                        for task in pending_tasks[:8]:  # Show up to 8 pending
                            task_text = task.task[:32]  # Shorter for space
                            # Highlight on hover
                            task_box_x1 = panel_x + 2
                            task_box_x2 = panel_x + panel_w - 8
                            task_box_y = current_y - 8
                            c.create_rectangle(task_box_x1, task_box_y, task_box_x2, task_box_y + 20, fill=C_DIM, outline=C_GLASS_BORDER)
                            # Clickable checkbox
                            c.create_text(panel_x + 10, current_y, text="☐", fill=C_PRI, font=("Courier", 11, "bold"), anchor="w", tags=f"task_checkbox_{task.id}")
                            c.create_text(panel_x + 28, current_y, text=task_text, fill=C_TEXT_PRI, font=("Courier", 9), anchor="w")
                            # Delete button - larger
                            c.create_text(panel_x + panel_w - 18, current_y, text="[×]", fill=C_WARN, font=("Courier", 8, "bold"), anchor="w")
                            current_y += task_spacing
                    
                    # Draw completed tasks
                    if completed_tasks:
                        c.create_text(panel_x + 5, current_y + 6, text="COMPLETED ITEMS", fill=C_SUCCESS, font=("Courier", 9, "bold"), anchor="w")
                        current_y += 28
                        for task in completed_tasks[:5]:  # Show up to 5 completed
                            task_text = task.task[:32]  # Shorter for space
                            # Highlight on hover
                            task_box_x1 = panel_x + 2
                            task_box_x2 = panel_x + panel_w - 8
                            task_box_y = current_y - 8
                            c.create_rectangle(task_box_x1, task_box_y, task_box_x2, task_box_y + 20, fill=C_DIM, outline=C_GLASS_BORDER)
                            # Clickable checkbox
                            c.create_text(panel_x + 10, current_y, text="☑", fill=C_SUCCESS, font=("Courier", 11, "bold"), anchor="w", tags=f"task_checkbox_{task.id}")
                            c.create_text(panel_x + 28, current_y, text=task_text, fill=C_TEXT_PRI, font=("Courier", 9), anchor="w")
                            # Delete button - larger
                            c.create_text(panel_x + panel_w - 18, current_y, text="[×]", fill=C_WARN, font=("Courier", 8, "bold"), anchor="w")
                            current_y += task_spacing
                    
                    
                    # Add task input - much larger and more prominent
                    input_y = current_y + 12
                    input_h = 24
                    c.create_rectangle(panel_x + 5, input_y, panel_x + panel_w - 35, input_y + input_h, fill=C_DIM, outline=C_PRI, width=2)
                    placeholder = self.task_add_input if self.task_add_input else "➕ Type new task..."
                    placeholder_col = C_TEXT_PRI if self.task_add_input else C_TEXT_SEC
                    c.create_text(panel_x + 10, input_y + input_h//2, text=placeholder[:28], fill=placeholder_col, font=("Courier", 9), anchor="w")
                    
                    # Add button - larger and more visible
                    c.create_rectangle(panel_x + panel_w - 32, input_y, panel_x + panel_w - 8, input_y + input_h, fill=C_ACC, outline=C_PRI, width=2)
                    c.create_text(panel_x + panel_w - 20, input_y + input_h//2, text="+", fill=C_BG_TOP, font=("Courier", 12, "bold"), anchor="c")
                    
                    # Show task count at bottom
                    total = len(pending_tasks) + len(completed_tasks)
                    c.create_text(panel_x + 8, ty - 30 + panel_h - 8, text=f"Total: {total} tasks", fill=C_TEXT_SEC, font=("Courier", 7), anchor="w")
                    
                else:
                    # Compact panel (original layout)
                    self._draw_glass_panel(hx - 10, ty - 30, hw + 20, 100, "TODAY'S TASKS")
                    c.create_text(hx, ty + 10, text=f"PENDING: {self.task_stats['pending']}", fill=C_PRI, font=("Courier", 8), anchor="w")
                    c.create_text(hx, ty + 30, text=f"COMPLETED: {self.task_stats['completed']}", fill=C_SUCCESS, font=("Courier", 8), anchor="w")
                    # Visual progress bar
                    total = self.task_stats['pending'] + self.task_stats['completed']
                    if total > 0:
                        progress = self.task_stats['completed'] / total
                        bar_w = hw - 10
                        c.create_rectangle(hx, ty + 50, hx + bar_w, ty + 55, fill=C_DIM, outline="")
                        c.create_rectangle(hx, ty + 50, hx + int(bar_w * progress), ty + 55, fill=C_SUCCESS, outline="")
                        c.create_text(hx, ty + 70, text=f"{int(progress*100)}% COMPLETE", fill=C_ACC, font=("Courier", 7), anchor="w")
            else:
                c.create_text(hx, ty - 20, text="▶ TODAY'S TASKS", fill=C_SEC, font=("Courier", 9, "bold"), anchor="w")
        if not self.compact_mode:
            bx, by, bw, bh = 24, H - 265, 140, 26
            c.create_text(bx, by - 15, text="OPERATIONS", fill=C_SEC, font=("Courier", 8, "bold"), anchor="w")
            for i, cmd in enumerate(["SCREENSHOT", "WEB SEARCH", "EXPLAIN", "NEW TASK"]):
                yy = by + i * 32
                c.create_rectangle(bx, yy, bx + bw, yy + bh, outline=C_GLASS_BORDER, fill=C_GLASS_BG)
                c.create_text(bx + bw//2, yy + bh//2, text=cmd, fill=C_TEXT_PRI, font=("Courier", 7, "bold"))
                c.create_line(bx, yy, bx+4, yy, fill=C_ACC, width=2)
                c.create_line(bx, yy, bx, yy+4, fill=C_ACC, width=2)            
            pby = by + 32 * 4 + 6
            pref_col = C_WARN if self.dream_mode_active else C_PRI
            c.create_rectangle(bx, pby, bx + bw, pby + bh, outline=C_GLASS_BORDER, fill=C_GLASS_BG)
            c.create_text(bx + bw//2, pby + bh//2, text="PREFERENCES", fill=pref_col, font=("Courier", 7, "bold"))
            c.create_line(bx, pby, bx+4, pby, fill=pref_col, width=2)
            c.create_line(bx, pby, bx, pby+4, fill=pref_col, width=2)
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

            # Radial Information Expansion System (only for left menu panels).
            self._draw_radial_info(FCX, FCY, FW, t)
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
            sy = FCY + 65
            c.create_text(W // 2, sy, text=f"• {state} •", fill=pri, font=("Courier", 10, "bold"))
            cy = sy + 25
            ctx_text = f"APP: {self.env_context.get('active_app', 'N/A')[:12]} | PRJ: {self.env_context.get('project', 'None')[:12]}"
            c.create_text(W // 2, cy, text=ctx_text, fill=C_TEXT_PRI, font=("Courier", 8))
            c.create_text(W // 2, cy + 18, text=f"FOCUS: {self.env_context.get('focus_time_minutes', 0)} MIN | {self.env_context.get('time_of_day', 'Morning').upper()}", fill=C_ACC, font=("Courier", 8))
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
            for panel in self.expandable_panels.values():
                panel.is_selected = (panel.panel_id == self.center_panel_id)
                panel.draw(c)

    def _update_title(self):
        """Update window title with status indicator"""
        if self.dream_mode_active:
            title = "🌙 CRISTINE"
        elif self.speaking or self.active_tasks:
            title = "◆ CRISTINE"
        elif self.speech_mode:
            title = "● CRISTINE"
        else:
            title = "◇ CRISTINE"
        self.root.title(title)

    def start_speaking(self):
        self.speaking, self.status_text = True, "SPEAKING"
        self.log_frame.configure(highlightbackground=C_PRI)
        self.input_entry.configure(highlightbackground=C_PRI, highlightcolor=C_SEC)
        self.mode_btn.configure(bg=C_SEC, fg=C_BG_TOP)
        self._update_title()

    def stop_speaking(self):
        self.speaking, self.status_text = False, "ONLINE"
        self.log_frame.configure(highlightbackground=C_GLASS_BORDER)
        self.input_entry.configure(highlightbackground=C_GLASS_BORDER, highlightcolor=C_PRI)
        self.mode_btn.configure(bg=C_DIM, fg=C_TEXT_PRI)
        self._update_title()

    def _api_keys_exist(self):
        if not API_FILE.exists():
            return False
        try:
            with open(API_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                key = data.get("gemini_api_key", "").strip()
                return bool(key)
        except (json.JSONDecodeError, IOError):
            return False
    def wait_for_api_key(self):
        self._api_key_ready.wait()
    def _show_setup_ui(self):
        self.setup_frame = tk.Frame(self.root, bg=C_BG_TOP, highlightbackground=C_PRI, highlightthickness=1)
        self.setup_frame.place(relx=0.5, rely=0.5, anchor="center")
        self.setup_frame.tkraise()
        tk.Label(self.setup_frame, text="◈  INITIALISATION REQUIRED", fg=C_PRI, bg=C_BG_TOP, font=("Courier", 13, "bold")).pack(pady=(18, 4))
        tk.Label(self.setup_frame, text="Enter your Gemini API key to boot CRISTINE.", fg=C_TEXT_SEC, bg=C_BG_TOP, font=("Courier", 9)).pack(pady=(0, 10))
        tk.Label(self.setup_frame, text="GEMINI API KEY", fg=C_DIM, bg=C_BG_TOP, font=("Courier", 9)).pack(pady=(8, 2))
        self.gemini_entry = tk.Entry(self.setup_frame, width=52, fg=C_TEXT_PRI, bg=C_DIMMER, insertbackground=C_TEXT_PRI, borderwidth=0, font=("Courier", 10), show="*")
        self.gemini_entry.pack(pady=(0, 4))
        tk.Button(self.setup_frame, text="▸  INITIALISE SYSTEMS", command=self._save_api_keys_and_complete_setup, bg=C_BG_TOP, fg=C_PRI, activebackground=C_DIM, activeforeground=C_PRI, font=("Courier", 10), borderwidth=0, pady=8).pack(pady=14)
        self.gemini_entry.focus()
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
        self._api_key_ready.set()

__all__ = ["CristineUI"]


def _palette_call_tool(tool: str, parameters: dict, *, ui: "CristineUI") -> str:
    """
    Best-effort tool runner for the Command Palette.

    Tries to mirror main.py behavior but avoids importing main.py or requiring the live session.
    New tools that follow the convention actions/<tool>.py:def <tool>(parameters, player=...) work automatically.
    """
    tool = (tool or "").strip()
    parameters = dict(parameters or {})

    # Special cases / legacy naming differences.
    if tool == "weather_report":
        from actions.weather_report import weather_action
        return weather_action(parameters=parameters, player=ui) or "Done."

    if tool == "screen_process":
        from actions.screen_processor import screen_process
        threading.Thread(target=screen_process, kwargs={"parameters": parameters, "player": ui}, daemon=True).start()
        return "Vision active."

    if tool == "desktop_control":
        from actions.desktop import desktop_control
        return desktop_control(parameters=parameters, player=ui) or "Done."

    if tool == "system_monitor":
        from actions.system_monitor import system_monitor_action
        return system_monitor_action(parameters=parameters) or "Done."

    if tool == "agent_task":
        goal = str(parameters.get("goal", "") or "")
        if not goal:
            return "agent_task requires 'goal'."
        try:
            from agent.task_queue import get_queue
            tid = get_queue().submit(goal=goal, speak=True)
            return f"Task {tid} started."
        except Exception as e:
            return f"Failed to start agent task: {str(e)[:160]}"

    if tool in ("add_task", "complete_task", "delete_task", "show_tasks"):
        from memory.task_manager import get_task_manager

        task_mgr = get_task_manager()
        if tool == "add_task":
            txt = str(parameters.get("task", "") or "").strip()
            if not txt:
                return "add_task requires 'task'."
            t = task_mgr.add_task(txt)
            try:
                ui._update_task_stats()
            except Exception:
                pass
            return f"Task added: {t.task} ({t.id})" if t else "Failed to add task."

        if tool == "show_tasks":
            return task_mgr.get_task_summary()

        task_id = str(parameters.get("task_id", "") or "").strip()
        if not task_id:
            return f"{tool} requires 'task_id'."

        # Try by ID first, then by task text.
        if tool == "complete_task":
            success = task_mgr.complete_task(task_id)
            if not success:
                for t in task_mgr.tasks:
                    if str(getattr(t, "task", "")).lower() == task_id.lower():
                        success = task_mgr.complete_task(t.id)
                        break
            try:
                ui._update_task_stats()
            except Exception:
                pass
            return f"✓ Task marked as complete: {task_id}" if success else f"Could not find task: {task_id}"

        if tool == "delete_task":
            success = task_mgr.delete_task(task_id)
            if not success:
                for t in task_mgr.tasks:
                    if str(getattr(t, "task", "")).lower() == task_id.lower():
                        success = task_mgr.delete_task(t.id)
                        break
            try:
                ui._update_task_stats()
            except Exception:
                pass
            return f"✓ Task deleted: {task_id}" if success else f"Could not find task: {task_id}"

    if tool == "query_knowledge_graph":
        from memory.graph_memory import graph_memory

        term = str(parameters.get("search_term", "") or "").strip()
        if not term:
            return "query_knowledge_graph requires 'search_term'."
        rels = graph_memory.query(term)
        if rels:
            lines = [f"- {s} --[{p}]--> {o} ({t})" for s, p, o, t in rels]
            return "Knowledge Graph Matches:\n" + "\n".join(lines[:50])
        return f"No relationships found for '{term}'."

    # Default convention: actions.<tool>.<tool>
    try:
        import importlib

        mod = importlib.import_module(f"actions.{tool}")
        fn = getattr(mod, tool, None)
        if callable(fn):
            return fn(parameters=parameters, player=ui) or "Done."

        # Common alternate naming pattern.
        fn2 = getattr(mod, f"{tool}_action", None)
        if callable(fn2):
            return fn2(parameters=parameters, player=ui) or "Done."

        return f"Tool '{tool}' is installed but not callable (missing function)."
    except Exception as e:
        return f"Tool '{tool}' failed: {str(e)[:200]}"

