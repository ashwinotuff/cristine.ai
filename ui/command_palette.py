import ast
import json
import os
import threading
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import messagebox

_C_BG_TOP = "#03060A"
_C_PRI = "#4FD1FF"
_C_SEC = "#A66CFF"
_C_ACC = "#52FFA8"
_C_PANEL_BG = "#0D1B2E"
_C_BORDER = "#3A5A7E"
_C_TEXT = "#CBEFFF"
_C_TEXT_MUTED = "#7FAAC9"
_C_DIM = "#1B2D44"
_C_DIMMER = "#0D1520"

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

_C_SHEEN = _shade(_C_PANEL_BG, 0.08)
_C_SHADOW = _shade(_C_BG_TOP, -0.55)


@dataclass(frozen=True)
class PaletteItem:
    kind: str  # tool | routine | task | rerun | prefs
    key: str   # stable identifier (tool name, routine id/name, etc.)
    title: str
    subtitle: str = ""
    payload: dict[str, Any] | None = None


def _base_dir() -> Path:
    # ui/__init__.py defines BASE_DIR similarly; keep this local to avoid import loops.
    here = Path(__file__).resolve()
    return here.parent.parent


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _load_tool_declarations() -> list[dict[str, Any]]:
    """
    Read TOOL_DECLARATIONS from main.py without importing it (avoids heavy imports/cycles).
    This automatically stays current as tools are added.
    """
    main_path = _base_dir() / "main.py"
    try:
        src = main_path.read_text(encoding="utf-8")
        mod = ast.parse(src)
        for node in mod.body:
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == "TOOL_DECLARATIONS":
                        return ast.literal_eval(node.value)
    except Exception:
        pass
    return []


def _fuzzy_score(q: str, s: str) -> float:
    q = (q or "").strip().lower()
    s = (s or "").strip().lower()
    if not q:
        return 1.0
    if q in s:
        return 1.2
    return SequenceMatcher(a=q, b=s).ratio()


class ToolForm(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        tool_name: str,
        schema: dict[str, Any] | None,
        initial_params: dict[str, Any] | None,
        on_submit: Callable[[dict[str, Any]], None],
    ):
        super().__init__(parent)
        self.title(f"Run Tool: {tool_name}")
        self.configure(bg="#03060A")
        self.resizable(True, True)
        self.geometry("520x420")

        self.tool_name = tool_name
        self.schema = schema or {}
        self.on_submit = on_submit

        self.vars: dict[str, Any] = {}
        self.json_boxes: dict[str, tk.Text] = {}

        header = tk.Label(self, text=f"RUN TOOL: {tool_name}", bg="#03060A", fg="#4FD1FF", font=("Courier", 12, "bold"))
        header.pack(anchor="w", padx=12, pady=(10, 6))

        self.msg = tk.StringVar(value="")
        msg_lbl = tk.Label(self, textvariable=self.msg, bg="#03060A", fg="#A66CFF", font=("Courier", 9))
        msg_lbl.pack(anchor="w", padx=12, pady=(0, 8))

        body = tk.Frame(self, bg="#0D1B2E", highlightbackground="#3A5A7E", highlightthickness=1)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        canvas = tk.Canvas(body, bg="#0D1B2E", highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(body, command=canvas.yview)
        sb.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=sb.set)

        inner = tk.Frame(canvas, bg="#0D1B2E")
        canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_config(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner.bind("<Configure>", _on_config)

        params_schema = (self.schema or {}).get("parameters") or {}
        props = (params_schema.get("properties") or {}) if isinstance(params_schema, dict) else {}
        required = set(params_schema.get("required") or [])

        initial_params = dict(initial_params or {})
        self._raw_params_box: tk.Text | None = None

        if not props:
            # Unknown/complex schema fallback: raw JSON editor.
            info = tk.Label(inner, text="Parameters (raw JSON):", bg="#0D1B2E", fg="#CBEFFF", font=("Courier", 10, "bold"))
            info.pack(anchor="w", padx=10, pady=(10, 4))
            box = tk.Text(inner, height=10, bg="#0D1520", fg="#CBEFFF", insertbackground="#CBEFFF", font=("Courier", 9), borderwidth=0, wrap="word")
            box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            try:
                box.insert("1.0", json.dumps(initial_params or {}, indent=2))
            except Exception:
                box.insert("1.0", "{}")
            self._raw_params_box = box
        else:
            for key, spec in props.items():
                spec = spec or {}
                ptype = str(spec.get("type") or "STRING").upper()
                desc = str(spec.get("description") or "")
                is_req = key in required

                row = tk.Frame(inner, bg="#0D1B2E")
                row.pack(fill="x", padx=10, pady=6)

                lbl_txt = f"{key}{' *' if is_req else ''}"
                lbl = tk.Label(row, text=lbl_txt, bg="#0D1B2E", fg="#CBEFFF", font=("Courier", 10, "bold"))
                lbl.pack(anchor="w")
                if desc:
                    d = tk.Label(row, text=desc, bg="#0D1B2E", fg="#7FAAC9", font=("Courier", 8))
                    d.pack(anchor="w")

                init_val = initial_params.get(key)

                if ptype in ("STRING", "NUMBER", "BOOLEAN"):
                    if ptype == "BOOLEAN":
                        v = tk.BooleanVar(value=bool(init_val) if init_val is not None else False)
                        self.vars[key] = ("BOOLEAN", v, is_req)
                        cb = tk.Checkbutton(row, text="True / False", variable=v, bg="#0D1B2E", fg="#4FD1FF", selectcolor="#1B2D44", font=("Courier", 9))
                        cb.pack(anchor="w", pady=2)
                    else:
                        v = tk.StringVar(value="" if init_val is None else str(init_val))
                        self.vars[key] = (ptype, v, is_req)
                        ent = tk.Entry(row, textvariable=v, bg="#0D1520", fg="#CBEFFF", insertbackground="#CBEFFF", font=("Courier", 10), borderwidth=0)
                        ent.pack(fill="x", pady=2)
                else:
                    # Nested or array: JSON textbox.
                    box = tk.Text(row, height=4, bg="#0D1520", fg="#CBEFFF", insertbackground="#CBEFFF", font=("Courier", 9), borderwidth=0, wrap="word")
                    try:
                        if init_val is not None:
                            box.insert("1.0", json.dumps(init_val, indent=2))
                    except Exception:
                        pass
                    box.pack(fill="x", pady=2)
                    self.json_boxes[key] = box
                    self.vars[key] = ("JSON", None, is_req)

        btn_row = tk.Frame(self, bg="#03060A")
        btn_row.pack(fill="x", padx=12, pady=(0, 12))

        def _submit():
            try:
                params = self._collect_params()
            except Exception as e:
                self.msg.set(str(e)[:140])
                return
            self.destroy()
            self.on_submit(params)

        run_btn = tk.Button(btn_row, text="RUN", command=_submit, bg="#52FFA8", fg="#03060A", font=("Courier", 10, "bold"), borderwidth=0, padx=16, pady=8, cursor="hand2")
        run_btn.pack(side="left")
        cancel_btn = tk.Button(btn_row, text="CLOSE", command=self.destroy, bg="#1B2D44", fg="#CBEFFF", font=("Courier", 10, "bold"), borderwidth=0, padx=16, pady=8, cursor="hand2")
        cancel_btn.pack(side="left", padx=(8, 0))

        self.transient(parent)
        self.grab_set()
        self.focus_force()

    def _collect_params(self) -> dict[str, Any]:
        if self._raw_params_box is not None:
            raw = self._raw_params_box.get("1.0", "end").strip()
            if raw == "":
                return {}
            try:
                val = json.loads(raw)
            except Exception:
                raise ValueError("Invalid JSON parameters")
            if not isinstance(val, dict):
                raise ValueError("Parameters JSON must be an object")
            return val

        out: dict[str, Any] = {}
        missing = []
        for key, (ptype, var, is_req) in self.vars.items():
            if ptype == "BOOLEAN":
                val = bool(var.get())
                out[key] = val
                continue
            if ptype == "NUMBER":
                raw = (var.get() or "").strip()
                if not raw:
                    if is_req:
                        missing.append(key)
                    continue
                try:
                    out[key] = float(raw) if ("." in raw) else int(raw)
                except Exception:
                    raise ValueError(f"Invalid number for '{key}'")
                continue
            if ptype == "STRING":
                raw = (var.get() or "")
                if raw.strip() == "":
                    if is_req:
                        missing.append(key)
                    continue
                out[key] = raw
                continue
            # JSON box
            box = self.json_boxes.get(key)
            raw = (box.get("1.0", "end").strip() if box else "")
            if raw == "":
                if is_req:
                    missing.append(key)
                continue
            try:
                out[key] = json.loads(raw)
            except Exception:
                raise ValueError(f"Invalid JSON for '{key}'")

        if missing:
            raise ValueError("Missing required: " + ", ".join(missing))
        return out


class CommandPalette(tk.Toplevel):
    def __init__(self, ui):
        super().__init__(ui.root)
        self.ui = ui
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)

        self.configure(bg=_C_BG_TOP)

        # Depth layering: shadow -> border -> surface
        shadow = tk.Frame(self, bg=_C_SHADOW)
        shadow.pack(fill="both", expand=True)
        border = tk.Frame(shadow, bg=_C_BORDER)
        border.pack(fill="both", expand=True, padx=(0, 4), pady=(0, 4))
        self.panel = tk.Frame(border, bg=_C_PANEL_BG)
        self.panel.pack(fill="both", expand=True, padx=1, pady=1)

        # Top sheen highlight
        tk.Frame(self.panel, bg=_C_SHEEN, height=2).pack(fill="x")

        hdr = tk.Frame(self.panel, bg=_C_PANEL_BG)
        hdr.pack(fill="x", padx=12, pady=(10, 8))
        tk.Label(hdr, text="COMMAND PALETTE", bg=_C_PANEL_BG, fg=_C_SEC, font=("Courier", 10, "bold")).pack(side="left")
        tk.Label(hdr, text="Ctrl+K to toggle  |  Enter to run  |  Esc to close", bg=_C_PANEL_BG, fg=_C_TEXT_MUTED, font=("Courier", 8)).pack(side="right")

        self.q = tk.StringVar(value="")
        ent_wrap = tk.Frame(self.panel, bg=_C_BORDER)
        ent_wrap.pack(fill="x", padx=12, pady=(0, 8))
        ent = tk.Entry(ent_wrap, textvariable=self.q, bg=_C_DIMMER, fg=_C_TEXT, insertbackground=_C_TEXT, font=("Courier", 12), borderwidth=0)
        ent.pack(fill="x", padx=1, pady=1, ipady=6)
        self.entry = ent
        try:
            ent.bind("<FocusIn>", lambda _e: ent_wrap.config(bg=_C_PRI))
            ent.bind("<FocusOut>", lambda _e: ent_wrap.config(bg=_C_BORDER))
        except Exception:
            pass

        list_outer = tk.Frame(self.panel, bg=_C_BORDER)
        list_outer.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        list_wrap = tk.Frame(list_outer, bg=_C_PANEL_BG)
        list_wrap.pack(fill="both", expand=True, padx=1, pady=1)
        self.listbox = tk.Listbox(list_wrap, bg=_C_DIMMER, fg=_C_TEXT, selectbackground=_C_PRI, selectforeground=_C_BG_TOP, font=("Courier", 10), borderwidth=0, height=12)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(list_wrap, command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=sb.set)

        self.items: list[PaletteItem] = []
        self._row_items: list[PaletteItem | None] = []

        self.q.trace_add("write", lambda *_: self._refresh())
        self.listbox.bind("<Return>", lambda e: self._activate_selected())
        self.listbox.bind("<Escape>", lambda e: self.hide())
        self.entry.bind("<Escape>", lambda e: self.hide())
        self.entry.bind("<Return>", lambda e: self._activate_selected())
        self.entry.bind("<Down>", lambda e: self._select_delta(+1))
        self.entry.bind("<Up>", lambda e: self._select_delta(-1))
        self.listbox.bind("<Down>", lambda e: self._select_delta(+1))
        self.listbox.bind("<Up>", lambda e: self._select_delta(-1))
        self.listbox.bind("<Double-Button-1>", lambda e: self._activate_selected())

        # Window sizing is done at show() time.

    def toggle(self):
        if self.winfo_viewable():
            self.hide()
        else:
            self.show()

    def show(self):
        root = self.ui.root
        root.update_idletasks()
        w = max(560, int(root.winfo_width() * 0.68))
        h = max(380, min(520, int(root.winfo_height() * 0.62)))
        x = root.winfo_rootx() + (root.winfo_width() - w) // 2
        y = root.winfo_rooty() + int(root.winfo_height() * 0.18)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.deiconify()
        self.entry.focus_set()
        self.q.set("")
        self._refresh()

    def hide(self):
        self.withdraw()

    def _select_delta(self, d: int):
        if not self._row_items:
            return
        cur = self.listbox.curselection()
        idx = cur[0] if cur else 0
        step = 1 if d >= 0 else -1
        idx = idx + d
        idx = max(0, min(len(self._row_items) - 1, idx))
        # Skip non-selectable rows (headers/separators).
        while 0 <= idx < len(self._row_items) and self._row_items[idx] is None:
            idx += step
        idx = max(0, min(len(self._row_items) - 1, idx))
        if self._row_items[idx] is None:
            return
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(idx)
        self.listbox.activate(idx)
        self.listbox.see(idx)

    def _build_catalog(self) -> list[PaletteItem]:
        items: list[PaletteItem] = []

        # Actions
        items.append(PaletteItem(kind="command", key="diag_smoke", title="RUN: Feature Diagnostics (smoke)", subtitle="Fast background-safe checks", payload={"cmd": "diag", "mode": "smoke"}))
        items.append(PaletteItem(kind="command", key="diag_full", title="RUN: Feature Diagnostics (full)", subtitle="Runs intrusive/slow tests too", payload={"cmd": "diag", "mode": "full"}))

        # Tools
        for t in _load_tool_declarations():
            name = str(t.get("name") or "").strip()
            if not name:
                continue
            desc = str(t.get("description") or "")
            items.append(PaletteItem(kind="tool", key=name, title=name, subtitle=desc, payload={"decl": t}))

        # Routines
        routines_path = _base_dir() / "memory" / "routines.json"
        routines = _load_json(routines_path, [])
        if isinstance(routines, list):
            for r in routines:
                if not isinstance(r, dict):
                    continue
                rid = str(r.get("id") or r.get("name") or "").strip()
                if not rid:
                    continue
                items.append(PaletteItem(kind="routine", key=rid, title=str(r.get("name") or rid), subtitle=str(r.get("description") or ""), payload={"routine": r}))

        # Tasks (raw catalog; does not mutate task manager)
        tasks_path = _base_dir() / "memory" / "tasks.json"
        tasks = _load_json(tasks_path, [])
        if isinstance(tasks, list):
            for t in tasks[:1000]:
                if not isinstance(t, dict):
                    continue
                tid = str(t.get("id") or "").strip()
                title = str(t.get("task") or t.get("title") or tid).strip()
                if not title:
                    continue
                subtitle = str(t.get("status") or "").strip()
                items.append(PaletteItem(kind="task", key=tid or title, title=title, subtitle=subtitle, payload={"task": t}))

        # Recent rerun
        last = getattr(self.ui, "_last_tool_run", None)
        if isinstance(last, dict) and last.get("tool"):
            items.append(PaletteItem(kind="rerun", key=str(last.get("tool")), title=f"RERUN: {last.get('tool')}", subtitle="Edit params then run", payload={"tool": last.get("tool"), "params": last.get("params") or {}}))

        # Recent tool runs (in-memory buffer)
        hist = getattr(self.ui, "_tool_run_history", None)
        if hist:
            try:
                for i, h in enumerate(list(hist)[:6]):
                    if not isinstance(h, dict) or not h.get("tool"):
                        continue
                    tname = str(h.get("tool"))
                    items.append(
                        PaletteItem(
                            kind="rerun",
                            key=f"{tname}#{i}",
                            title=f"RECENT: {tname}",
                            subtitle="Rerun with params",
                            payload={"tool": tname, "params": h.get("params") or {}},
                        )
                    )
            except Exception:
                pass

        # Preferences jumps
        items.append(PaletteItem(kind="prefs", key="prefs_general", title="PREFERENCES: General", subtitle="Jump to General section", payload={"section": "general"}))

        return items

    def _refresh(self):
        q = (self.q.get() or "").strip()
        if not q:
            self._render_default()
        else:
            self._render_search(q)

    def _add_row(self, text: str, item: PaletteItem | None, *, fg: str | None = None):
        idx = self.listbox.size()
        self.listbox.insert("end", text)
        self._row_items.append(item)
        if fg:
            try:
                self.listbox.itemconfig(idx, fg=fg)
            except Exception:
                pass

    def _select_first(self):
        for i, it in enumerate(self._row_items):
            if it is not None:
                self.listbox.selection_clear(0, "end")
                self.listbox.selection_set(i)
                self.listbox.activate(i)
                self.listbox.see(i)
                return

    def _render_default(self):
        self.listbox.delete(0, "end")
        self._row_items = []

        # Recent tools (unique, most recent first)
        recent_rows: list[PaletteItem] = []
        seen = set()
        hist = getattr(self.ui, "_tool_run_history", None)
        if hist:
            try:
                for h in list(hist)[:20]:
                    if not isinstance(h, dict) or not h.get("tool"):
                        continue
                    tname = str(h.get("tool"))
                    if tname in seen:
                        continue
                    seen.add(tname)
                    recent_rows.append(
                        PaletteItem(
                            kind="rerun",
                            key=f"recent:{tname}",
                            title=f"{tname}",
                            subtitle="recent (edit params then run)",
                            payload={"tool": tname, "params": h.get("params") or {}},
                        )
                    )
                    if len(recent_rows) >= 8:
                        break
            except Exception:
                pass

        self._add_row("RECENT TOOLS", None, fg="#A66CFF")
        if recent_rows:
            for it in recent_rows:
                self._add_row(f"  {it.title}", it, fg="#CBEFFF")
        else:
            self._add_row("  (none yet)", None, fg="#7FAAC9")
        self._add_row("", None, fg="#7FAAC9")

        # All tools (scrollable)
        self._add_row("ALL TOOLS", None, fg="#A66CFF")
        for t in _load_tool_declarations():
            name = str(t.get("name") or "").strip()
            if not name:
                continue
            desc = str(t.get("description") or "")
            it = PaletteItem(kind="tool", key=name, title=name, subtitle=desc, payload={"decl": t})
            self._add_row(f"  {name}", it, fg="#CBEFFF")

        self._select_first()

    def _render_search(self, q: str):
        base = self._build_catalog()
        scored = []
        for it in base:
            hay = f"{it.title} {it.subtitle} {it.key}"
            scored.append((_fuzzy_score(q, hay), it))
        scored.sort(key=lambda x: x[0], reverse=True)
        self.items = [it for _s, it in scored[:8]]

        self.listbox.delete(0, "end")
        self._row_items = []
        for it in self.items:
            line = it.title
            if it.subtitle:
                line = f"{line}  -  {it.subtitle[:70]}"
            self._add_row(line, it, fg="#CBEFFF")
        self._select_first()

    def _activate_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        it = self._row_items[idx] if 0 <= idx < len(self._row_items) else None
        if it is None:
            return
        self.hide()
        if it.kind == "command":
            cmd = (it.payload or {}).get("cmd")
            if cmd == "diag":
                mode = str((it.payload or {}).get("mode") or "smoke")
                try:
                    self.ui.run_feature_diagnostics(mode=mode)
                except Exception:
                    self.ui.write_log("[diag] Could not start diagnostics.", tag="sys")
            return
        if it.kind in ("tool", "rerun"):
            decl = (it.payload or {}).get("decl")
            tool = it.key if it.kind == "tool" else (it.payload or {}).get("tool")
            params = (it.payload or {}).get("params") if it.kind == "rerun" else {}

            # For normal tools, decl is provided; for rerun, reload decl from main.py.
            if not decl:
                for d in _load_tool_declarations():
                    if d.get("name") == tool:
                        decl = d
                        break

            def on_submit(p: dict[str, Any]):
                self.ui.run_tool_from_palette(str(tool), p, decl)

            ToolForm(self.ui.root, tool_name=str(tool), schema=decl, initial_params=params, on_submit=on_submit)
            return

        if it.kind == "routine":
            self.ui.run_routine_from_palette(it.payload.get("routine") if it.payload else None)
            return

        if it.kind == "task":
            # Put task text into the input field so user can act on it quickly.
            try:
                t = (it.payload or {}).get("task") or {}
                txt = str(t.get("task") or t.get("title") or it.title)
                self.ui.input_entry.delete(0, "end")
                self.ui.input_entry.insert(0, txt)
                self.ui.input_entry.focus_set()
            except Exception:
                pass
            return

        if it.kind == "prefs":
            section = (it.payload or {}).get("section") or "general"
            try:
                self.ui.open_preferences(section=str(section))
            except Exception:
                self.ui.open_preferences()
            return


def ensure_routines_file():
    p = _base_dir() / "memory" / "routines.json"
    if not p.exists():
        try:
            p.write_text("[]\n", encoding="utf-8")
        except Exception:
            pass
