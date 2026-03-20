# actions/app_switcher.py
# Cristine — Smart App Switcher
#
# Allows switching between open application windows based on intent/keywords.

import json
import sys
import traceback
from pathlib import Path

try:
    import pygetwindow as gw
    _GW = True
except ImportError:
    _GW = False

# Keyword mapping for common application intents
KEYWORD_MAP = {
    "code": ["visual studio", "vscode", "sublime", "pycharm", "intellij", "atom"],
    "music": ["spotify", "itunes", "music", "deezer", "tidal"],
    "browser": ["chrome", "edge", "firefox", "opera", "brave", "safari"],
    "terminal": ["cmd", "powershell", "terminal", "bash", "zsh", "iterm", "conemu"],
    "editor": ["notepad", "textedit", "gedit", "wordpad"],
    "communication": ["discord", "slack", "telegram", "whatsapp", "teams", "zoom"]
}

def app_switcher(
    parameters: dict,
    player=None,
    session_memory=None
) -> str:
    """
    Switch to a specific application window based on intent or keyword.
    
    Parameters:
        app_keyword (str): The keyword or intent (e.g., 'code', 'spotify', 'chrome')
    """
    if not _GW:
        return json.dumps({"status": "error", "message": "pygetwindow not installed."})

    app_keyword = parameters.get("app_keyword", "")
    if not app_keyword:
        # Friendly alias
        app_keyword = parameters.get("app_name", "") or parameters.get("keyword", "")
    app_keyword = str(app_keyword).lower().strip()
    if not app_keyword:
        return json.dumps({"status": "error", "message": "No application keyword provided."})

    if player:
        player.write_log(f"[Switcher] Seeking: {app_keyword}")

    try:
        # 1. Identify potential titles to search for
        search_terms = [app_keyword]
        if app_keyword in KEYWORD_MAP:
            search_terms.extend(KEYWORD_MAP[app_keyword])
        
        # 2. Get all open windows
        all_windows = gw.getAllWindows()
        if not all_windows:
            return json.dumps({"status": "not_found", "message": "No open windows detected."})

        best_match = None
        
        # 3. Find the best match
        # We look for windows that contain any of our search terms in their title
        for window in all_windows:
            title = window.title.lower()
            if not title: # Skip empty titles
                continue
                
            for term in search_terms:
                if term in title:
                    best_match = window
                    break
            if best_match:
                break

        # 4. Activate the window if found
        if best_match:
            try:
                if best_match.isMinimized:
                    best_match.restore()
                best_match.activate()
                
                if player:
                    player.write_log(f"[Switcher] Focused: {best_match.title}")
                    
                return json.dumps({
                    "status": "success", 
                    "window": best_match.title
                })
            except Exception as e:
                return json.dumps({
                    "status": "error", 
                    "message": f"Failed to activate window: {str(e)}"
                })
        else:
            return json.dumps({
                "status": "not_found", 
                "message": "No matching window found."
            })

    except Exception as e:
        print(f"[AppSwitcher] ❌ Error: {e}")
        traceback.print_exc()
        return json.dumps({
            "status": "error", 
            "message": str(e)
        })
