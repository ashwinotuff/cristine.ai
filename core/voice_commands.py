"""
Voice Commands Manager
Handles creation, storage, matching, and execution of custom voice commands
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Callable
import sys
import subprocess
import difflib

def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
COMMANDS_PATH = BASE_DIR / "config" / "custom_commands.json"

# Whitelist of safe applications (expand as needed)
SAFE_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "edge": "msedge.exe",
    "chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "spotify": "spotify.exe",
    "discord": "discord.exe",
    "slack": "slack.exe",
    "visual studio code": "code.exe",
    "vscode": "code.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
}

# Whitelist of safe built-in functions
SAFE_FUNCTIONS = {
    "activate_cristine": "cristine.activate",
    "minimize": "cristine.minimize",
    "maximize": "cristine.maximize",
    "toggle_compact": "cristine.toggle_compact",
    "clear_logs": "cristine.clear_logs",
    "open_preferences": "cristine.open_preferences",
}


class VoiceCommand:
    """Represents a single voice command"""
    
    def __init__(self, phrase: str, action: str, target: str):
        self.phrase = phrase.lower().strip()
        self.action = action
        self.target = target
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON storage"""
        return {
            "phrase": self.phrase,
            "action": self.action,
            "target": self.target
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'VoiceCommand':
        """Create from dictionary"""
        return VoiceCommand(data["phrase"], data["action"], data["target"])


class VoiceCommandManager:
    """Manages custom voice commands"""
    
    def __init__(self):
        self.commands: List[VoiceCommand] = []
        self._load_commands()
        self.function_callbacks: Dict[str, Callable] = {}
    
    def _load_commands(self) -> None:
        """Load commands from JSON file"""
        try:
            if COMMANDS_PATH.exists():
                with open(COMMANDS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.commands = [VoiceCommand.from_dict(cmd) for cmd in data]
                    print(f"[VoiceCmd] Loaded {len(self.commands)} custom commands")
        except Exception as e:
            print(f"[VoiceCmd] Error loading commands: {e}")
            self.commands = []
    
    def save_commands(self) -> bool:
        """Save commands to JSON file"""
        try:
            COMMANDS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(COMMANDS_PATH, "w", encoding="utf-8") as f:
                data = [cmd.to_dict() for cmd in self.commands]
                json.dump(data, f, indent=2)
            print(f"[VoiceCmd] Saved {len(self.commands)} commands")
            return True
        except Exception as e:
            print(f"[VoiceCmd] Error saving commands: {e}")
            return False
    
    def add_command(self, phrase: str, action: str, target: str) -> bool:
        """Add a new command"""
        try:
            # Validate
            if not phrase or not action or not target:
                print("[VoiceCmd] Missing required fields")
                return False
            
            if action not in ["open_app", "run_function", "run_safe_script"]:
                print(f"[VoiceCmd] Invalid action: {action}")
                return False
            
            # Safety checks
            if not self._is_safe_action(action, target):
                print(f"[VoiceCmd] Unsafe action blocked: {action} {target}")
                return False
            
            # Check for duplicates
            if any(cmd.phrase == phrase.lower().strip() for cmd in self.commands):
                print(f"[VoiceCmd] Command already exists: {phrase}")
                return False
            
            cmd = VoiceCommand(phrase, action, target)
            self.commands.append(cmd)
            return self.save_commands()
        except Exception as e:
            print(f"[VoiceCmd] Error adding command: {e}")
            return False
    
    def delete_command(self, phrase: str) -> bool:
        """Delete a command by phrase"""
        try:
            original_count = len(self.commands)
            self.commands = [cmd for cmd in self.commands if cmd.phrase != phrase.lower().strip()]
            if len(self.commands) < original_count:
                return self.save_commands()
            return False
        except Exception as e:
            print(f"[VoiceCmd] Error deleting command: {e}")
            return False
    
    def find_command(self, speech_text: str, fuzzy: bool = True) -> Optional[VoiceCommand]:
        """
        Find matching command from speech
        
        Args:
            speech_text: The user's voice input
            fuzzy: Allow fuzzy matching (typos)
            
        Returns:
            Matching VoiceCommand or None
        """
        text = speech_text.lower().strip()
        
        # Exact match first
        for cmd in self.commands:
            if cmd.phrase == text:
                return cmd
            # Substring match (e.g., "open spotify" matches speech "hey open spotify")
            if cmd.phrase in text or text in cmd.phrase:
                return cmd
        
        # Fuzzy match (if enabled)
        if fuzzy and self.commands:
            matches = difflib.get_close_matches(text, 
                                               [cmd.phrase for cmd in self.commands],
                                               n=1, cutoff=0.6)
            if matches:
                matching_phrase = matches[0]
                return next(cmd for cmd in self.commands if cmd.phrase == matching_phrase)
        
        return None
    
    def execute_command(self, command: VoiceCommand) -> Dict:
        """
        Execute a command safely
        
        Args:
            command: The VoiceCommand to execute
            
        Returns:
            Result dict with status and message
        """
        try:
            if command.action == "open_app":
                return self._execute_open_app(command.target)
            
            elif command.action == "run_function":
                return self._execute_function(command.target)
            
            elif command.action == "run_safe_script":
                return self._execute_safe_script(command.target)
            
            else:
                return {"success": False, "message": f"Unknown action: {command.action}"}
        
        except Exception as e:
            print(f"[VoiceCmd] Error executing command: {e}")
            return {"success": False, "message": f"Execution error: {str(e)}"}
    
    def _execute_open_app(self, app_name: str) -> Dict:
        """Safely open an application from whitelist"""
        try:
            app_lower = app_name.lower().strip()
            
            if app_lower not in SAFE_APPS:
                return {"success": False, "message": f"Application not in safe list: {app_name}"}
            
            exe_path = SAFE_APPS[app_lower]
            subprocess.Popen(exe_path)
            return {"success": True, "message": f"Opening {app_name}"}
        
        except Exception as e:
            return {"success": False, "message": f"Failed to open app: {str(e)}"}
    
    def _execute_function(self, function_name: str) -> Dict:
        """Execute a registered callback function"""
        try:
            func_lower = function_name.lower().strip()
            
            if func_lower not in self.function_callbacks:
                return {"success": False, "message": f"Function not registered: {function_name}"}
            
            callback = self.function_callbacks[func_lower]
            callback()
            return {"success": True, "message": f"Executed: {function_name}"}
        
        except Exception as e:
            return {"success": False, "message": f"Function execution failed: {str(e)}"}
    
    def _execute_safe_script(self, script_path: str) -> Dict:
        """Execute a safe Python script from the scripts directory"""
        try:
            # Only allow scripts from a whitelisted directory
            script_dir = BASE_DIR / "scripts"
            full_path = script_dir / script_path
            
            # Security: prevent path traversal
            if not str(full_path).startswith(str(script_dir)):
                return {"success": False, "message": "Script path traversal not allowed"}
            
            if not full_path.exists():
                return {"success": False, "message": f"Script not found: {script_path}"}
            
            # Run the script
            result = subprocess.run([sys.executable, str(full_path)], 
                                  capture_output=True, text=True, timeout=10)
            
            return {
                "success": result.returncode == 0,
                "message": result.stdout if result.returncode == 0 else result.stderr
            }
        
        except Exception as e:
            return {"success": False, "message": f"Script execution failed: {str(e)}"}
    
    def _is_safe_action(self, action: str, target: str) -> bool:
        """Validate if an action is safe to perform"""
        if action == "open_app":
            return target.lower() in SAFE_APPS
        elif action == "run_function":
            return target.lower() in SAFE_FUNCTIONS
        elif action == "run_safe_script":
            # Scripts must be in the scripts directory
            script_dir = BASE_DIR / "scripts"
            full_path = script_dir / target
            return str(full_path).startswith(str(script_dir))
        return False
    
    def register_function_callback(self, function_name: str, callback: Callable) -> None:
        """Register a callback function that can be called via voice command"""
        self.function_callbacks[function_name.lower()] = callback
    
    def get_all_commands(self) -> List[Dict]:
        """Get all commands as dictionaries"""
        return [cmd.to_dict() for cmd in self.commands]
    
    def get_safe_app_list(self) -> List[str]:
        """Get list of safe applications"""
        return list(SAFE_APPS.keys())
    
    def get_safe_function_list(self) -> List[str]:
        """Get list of safe functions"""
        return list(SAFE_FUNCTIONS.keys())


# Global instance
_voice_command_manager = None

def get_voice_command_manager() -> VoiceCommandManager:
    """Get or create global voice command manager instance"""
    global _voice_command_manager
    if _voice_command_manager is None:
        _voice_command_manager = VoiceCommandManager()
    return _voice_command_manager
