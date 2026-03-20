# actions/app_cheatsheet.py
# Cristine — Interactive Cheat Sheet
#
# Detects the active application and provides context-aware keyboard shortcuts.

import json
import sys
import traceback
from pathlib import Path

try:
    import pygetwindow as gw
    _GW = True
except ImportError:
    _GW = False

# Shortcut Database
SHORTCUT_DB = {
    "excel": {
        "name": "Microsoft Excel",
        "shortcuts": {
            "freeze panes": "Alt + W + F + F",
            "new sheet": "Shift + F11",
            "save": "Ctrl + S",
            "insert current date": "Ctrl + ;",
            "insert current time": "Ctrl + Shift + :",
            "format as currency": "Ctrl + Shift + $",
            "autosum": "Alt + =",
            "hide ribbon": "Ctrl + F1"
        }
    },
    "vscode": {
        "name": "Visual Studio Code",
        "shortcuts": {
            "command palette": "Ctrl + Shift + P",
            "format document": "Shift + Alt + F",
            "search": "Ctrl + F",
            "quick open": "Ctrl + P",
            "toggle sidebar": "Ctrl + B",
            "integrated terminal": "Ctrl + `",
            "multi-cursor": "Alt + Click",
            "go to line": "Ctrl + G"
        }
    },
    "photoshop": {
        "name": "Adobe Photoshop",
        "shortcuts": {
            "undo": "Ctrl + Z",
            "brush tool": "B",
            "zoom": "Z",
            "hand tool": "H",
            "move tool": "V",
            "lasso tool": "L",
            "transform": "Ctrl + T",
            "new layer": "Ctrl + Shift + N"
        }
    },
    "blender": {
        "name": "Blender",
        "shortcuts": {
            "search": "F3",
            "render": "F12",
            "move": "G",
            "rotate": "R",
            "scale": "S",
            "extrude": "E",
            "object/edit mode": "Tab",
            "add object": "Shift + A"
        }
    },
    "chrome": {
        "name": "Google Chrome",
        "shortcuts": {
            "new tab": "Ctrl + T",
            "close tab": "Ctrl + W",
            "reopen closed tab": "Ctrl + Shift + T",
            "incognito": "Ctrl + Shift + N",
            "downloads": "Ctrl + J",
            "history": "Ctrl + H",
            "search": "Ctrl + L",
            "inspect": "Ctrl + Shift + I"
        }
    },
    "word": {
        "name": "Microsoft Word",
        "shortcuts": {
            "save": "Ctrl + S",
            "bold": "Ctrl + B",
            "italic": "Ctrl + I",
            "center align": "Ctrl + E",
            "insert link": "Ctrl + K",
            "spelling check": "F7",
            "find": "Ctrl + F",
            "replace": "Ctrl + H"
        }
    },
    "powerpoint": {
        "name": "Microsoft PowerPoint",
        "shortcuts": {
            "new slide": "Ctrl + M",
            "duplicate slide": "Ctrl + D",
            "present": "F5",
            "present from current": "Shift + F5",
            "group objects": "Ctrl + G",
            "ungroup": "Ctrl + Shift + G",
            "open selection pane": "Alt + F10"
        }
    }
}

def app_cheatsheet(
    parameters: dict,
    player=None,
    session_memory=None
) -> str:
    """
    Detect the active application and return or display useful shortcuts.
    
    Parameters:
        action_query (str): Optional. A specific action to look for (e.g., 'freeze panes')
    """
    if not _GW:
        return "Sir, pygetwindow is not installed. I cannot detect active applications."

    action_query = parameters.get("action_query", "").lower().strip()
    
    try:
        # 1. Detect Active Window
        active_window = gw.getActiveWindow()
        if not active_window:
            return "Sir, I couldn't detect an active window."
        
        title = active_window.title.lower()
        
        # 2. Identify Application
        detected_app = None
        app_data = None
        
        for app_id, data in SHORTCUT_DB.items():
            if app_id in title:
                detected_app = app_id
                app_data = data
                break
        
        if not detected_app:
            return f"Sir, I detected '{active_window.title}', but I don't have a shortcut database for it yet."

        # 3. Look for specific shortcut or provide top ones
        shortcuts = app_data["shortcuts"]
        
        if action_query:
            # Search for best match in shortcuts
            best_match = None
            for key, val in shortcuts.items():
                if action_query in key:
                    best_match = (key, val)
                    break
            
            if best_match:
                msg = f"Application: {app_data['name']}\nAction: {best_match[0].title()}\nShortcut: {best_match[1]}"
                if player:
                    player.write_log(f"--- {app_data['name'].upper()} SHORTCUT ---", tag="sys")
                    player.write_log(f"{best_match[0].title()} -> {best_match[1]}", tag="sys")
                return msg
            else:
                return f"Sir, I couldn't find a shortcut for '{action_query}' in {app_data['name']}."
        
        # If no query, return top 5
        top_shortcuts = list(shortcuts.items())[:5]
        lines = [f"--- {app_data['name'].upper()} CHEATSHEET ---"]
        for action, keys in top_shortcuts:
            lines.append(f"{action.title():.<20} {keys}")
        
        result = "\n".join(lines)
        if player:
            for line in lines:
                player.write_log(line, tag="sys")
                
        return result

    except Exception as e:
        print(f"[CheatSheet] ❌ Error: {e}")
        traceback.print_exc()
        return f"Cheat sheet error: {e}"
