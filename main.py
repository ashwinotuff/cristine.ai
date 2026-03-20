import asyncio
import threading
import json
import re
import sys
import traceback
from pathlib import Path

import pyaudio
from google import genai
from google.genai import types
import time 
from ui import CristineUI
from memory.memory_manager import load_memory, update_memory, format_memory_for_prompt
from memory.graph_memory import graph_memory
from memory.task_manager import get_task_manager
from memory.config_manager import get_gemini_key

from agent.task_queue import get_queue
from system.dream_mode_scheduler import DreamModeScheduler
from system.dream_mode_tasks import DreamModeTasks

from actions.flight_finder import flight_finder
from actions.open_app         import open_app
from actions.weather_report   import weather_action
from actions.send_message     import send_message
from actions.reminder         import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor import screen_process
from actions.youtube_video    import youtube_video
from actions.cmd_control      import cmd_control
from actions.desktop          import desktop_control
from actions.browser_control  import browser_control
from actions.file_controller  import file_controller
from actions.code_helper      import code_helper
from actions.dev_agent        import dev_agent
from actions.web_search       import web_search as web_search_action
from actions.computer_control import computer_control
from actions.app_switcher      import app_switcher
from actions.app_cheatsheet     import app_cheatsheet
from actions.system_monitor    import system_monitor_action
from actions.system_health_agent import system_health_check, system_health_action
from actions.real_time_translation import real_time_translation, process_audio_stream
from actions.project_planner import project_planner
from actions.emotional_companion import emotional_companion

def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
FORMAT              = pyaudio.paInt16
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

pya = pyaudio.PyAudio()

def _get_api_key() -> str:
    """Get API key from config file. Waits if file doesn't exist yet."""
    # Prefer env var so users can run without storing keys on disk.
    env_key = (get_gemini_key() or "").strip()
    if env_key:
        return env_key

    max_retries = 100
    for attempt in range(max_retries):
        if API_CONFIG_PATH.exists():
            try:
                with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                    key = json.load(f).get("gemini_api_key", "").strip()
                    if key:  # Make sure key is not empty
                        return key
            except (json.JSONDecodeError, IOError):
                pass
        time.sleep(0.1)
    # If we get here, file doesn't exist or is invalid
    raise ValueError(f"Unable to load API key from {API_CONFIG_PATH}. Please run the setup first.")

def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are Cristine, a sharp and efficient AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_memory_turn_counter  = 0
_memory_turn_lock     = threading.Lock()
_MEMORY_EVERY_N_TURNS = 5
_last_memory_input    = ""


def _update_memory_async(user_text: str, cristine_text: str) -> None:
    global _memory_turn_counter, _last_memory_input
    with _memory_turn_lock:
        _memory_turn_counter += 1
        current_count = _memory_turn_counter
    if current_count % _MEMORY_EVERY_N_TURNS != 0: return
    text = f"User: {user_text}\nCristine: {cristine_text}"
    if len(user_text.strip()) < 5 or user_text == _last_memory_input: return
    _last_memory_input = user_text
    try:
        import google.generativeai as genai
        genai.configure(api_key=_get_api_key())
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        
        prompt = f"""
        Analyze the conversation and extract:
        1. Personal facts about the user (name, preferences, etc.)
        2. Knowledge graph triplets (Subject -> Predicate -> Object) related to projects, tech stacks, or work history.
           Example: ("Project Spotify", "uses", "Spotify API"), ("User", "worked on", "Weather App")
        
        Return ONLY valid JSON with keys "facts" and "triplets".
        Triplets should be a list of lists: [["Subject", "Predicate", "Object"], ...]
        
        Conversation:
        {text[:1000]}
        
        JSON:
        """
        raw = model.generate_content(prompt).text.strip()
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        data = json.loads(raw)
        
        facts = data.get("facts")
        if facts: update_memory(facts)
        
        triplets = data.get("triplets")
        if triplets:
            for s, p, o in triplets:
                graph_memory.add_relationship(s, p, o, context=user_text[:200])
                print(f"[Memory] 🕸️ Graph: {s} -> {p} -> {o}")
    except Exception as e:
        print(f"[Memory] ⚠️ Extraction error: {e}")



TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": "Opens any application on the computer. Use this whenever the user asks to open, launch, or start any app, website, or program.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {"type": "STRING", "description": "Name of the application (e.g. 'Chrome', 'Spotify')"}
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Search query"},
                "mode": {"type": "STRING", "description": "search | compare (default: search)"},
                "items": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare (mode=compare)"},
                "aspect": {"type": "STRING", "description": "Aspect to compare (mode=compare)"}
            }
        }
    },
    {
        "name": "weather_report",
        "description": "Gets real-time weather information for a city.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a message. Background-safe for Telegram if Bot API is configured; other platforms may require on-screen automation.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver": {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform": {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date": {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time": {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["time"]
        }
    },
    {
        "name": "youtube_video",
        "description": "Controls YouTube for playing videos or summaries.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending"},
                "query": {"type": "STRING", "description": "Search query (used for play/summarize/get_info if url not provided)"},
                "url": {"type": "STRING", "description": "Direct YouTube URL (optional)"},
                "region": {"type": "STRING", "description": "Trending region ISO code (default: TR)"},
                "save": {"type": "BOOLEAN", "description": "If true, save summaries to Desktop (summarize)"}
            }
        }
    },
    {
        "name": "screen_process",
        "description": "Captures and analyzes the screen or camera image. MUST be called when user asks what is on screen, analyze my screen, etc.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' | 'camera'"},
                "text": {"type": "STRING", "description": "Instruction about the image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": "Controls computer: volume, brightness, dark mode, etc.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "Optional explicit action (e.g. volume_set, screenshot). Prefer description if unsure."},
                "description": {"type": "STRING", "description": "Natural language command (recommended)."},
                "value": {"type": "STRING", "description": "Optional value for the action (volume %, text to type, count, etc.)"},
                "text": {"type": "STRING", "description": "Optional text (for type_text)."},
                "key": {"type": "STRING", "description": "Optional key name (for press_key)."},
                "press_enter": {"type": "BOOLEAN", "description": "Press Enter after typing (type_text)."}
            }
        }
    },
    {
        "name": "browser_control",
        "description": "Automates a browser. Supports headless background mode (recommended).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | press | close"},
                "url": {"type": "STRING", "description": "URL for go_to"},
                "query": {"type": "STRING", "description": "Search query for search"},
                "engine": {"type": "STRING", "description": "google | bing | duckduckgo (default: google)"},
                "selector": {"type": "STRING", "description": "CSS selector for click/type"},
                "text": {"type": "STRING", "description": "Text to type, or link/button text to click"},
                "description": {"type": "STRING", "description": "Human description for smart_click/smart_type"},
                "direction": {"type": "STRING", "description": "up | down (scroll)"},
                "amount": {"type": "NUMBER", "description": "Scroll amount in pixels (default: 500)"},
                "key": {"type": "STRING", "description": "Key to press (e.g. Enter, Escape, Tab)"},
                "fields": {"type": "OBJECT", "description": "Form fields map for fill_form (selector -> value)"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear input before typing (default: True)"},
                "headless": {"type": "BOOLEAN", "description": "If true, run headless (no visible browser window). Defaults from Preferences."},
                "timeout_ms": {"type": "NUMBER", "description": "Playwright action timeout in milliseconds (optional)."},
                "result_timeout_s": {"type": "NUMBER", "description": "How long to wait for completion (seconds, optional)."},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders (background-safe, no on-screen automation).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "list | create_file | create_folder | read | write | delete | move | copy | rename | find | largest | disk_usage | organize_desktop | info"},
                "path": {"type": "STRING", "description": "Base path or shortcut: desktop, downloads, documents, pictures, music, videos, home, or an absolute path."},
                "name": {"type": "STRING", "description": "Optional filename/folder name (combined with path)"},
                "content": {"type": "STRING", "description": "Content for create_file/write"},
                "append": {"type": "BOOLEAN", "description": "Append when writing (write action)"},
                "destination": {"type": "STRING", "description": "Destination path (move/copy)"},
                "new_name": {"type": "STRING", "description": "New name (rename)"},
                "extension": {"type": "STRING", "description": "Filter extension (find)"},
                "max_results": {"type": "NUMBER", "description": "Max results (find)"},
                "count": {"type": "NUMBER", "description": "Count (largest)"},
                "show_hidden": {"type": "BOOLEAN", "description": "Include hidden files (list)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "cmd_control",
        "description": "Runs terminal commands (defaults to silent/background execution unless visible=true).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task": {"type": "STRING", "description": "Natural language request to convert to a safe command (recommended)."},
                "command": {"type": "STRING", "description": "Explicit command to run (optional)."},
                "visible": {"type": "BOOLEAN", "description": "If true, open a visible terminal window (defaults from Preferences)."},
                "timeout": {"type": "NUMBER", "description": "Timeout seconds for execution (silent mode)."} 
            }
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop (wallpaper, organize, list). action=task may require on-screen automation.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | current_wallpaper | organize | clean | list | stats | task"},
                "path": {"type": "STRING", "description": "Image path for wallpaper"},
                "url": {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode": {"type": "STRING", "description": "Organize mode (organize): by_type | by_date"},
                "task": {"type": "STRING", "description": "Natural language desktop task (requires on-screen automation)"},
                "description": {"type": "STRING", "description": "Alias for task"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, runs code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "write | edit | explain | run | build | screen_debug | optimize | auto"},
                "description": {"type": "STRING", "description": "What to do / what change to make / what to analyze"},
                "language": {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save output (filename or full path)"},
                "file_path": {"type": "STRING", "description": "Existing file path (edit/explain/run/build/optimize)"},
                "code": {"type": "STRING", "description": "Raw code string (optional)"},
                "args": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "CLI args for run/build"},
                "timeout": {"type": "NUMBER", "description": "Execution timeout in seconds (default: 30)"}
            }
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description": {"type": "STRING"}
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": "Executes complex multi-step tasks.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal": {"type": "STRING"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct on-screen computer control (mouse/keyboard/screen). Not background-safe unless on-screen automation is enabled.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | drag | copy | paste | screenshot | wait | wait_image | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text": {"type": "STRING", "description": "Text to type/paste"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (smart_type)"},
                "press_enter": {"type": "BOOLEAN", "description": "Press Enter after typing (type)"},
                "x": {"type": "NUMBER", "description": "X coordinate"},
                "y": {"type": "NUMBER", "description": "Y coordinate"},
                "x1": {"type": "NUMBER", "description": "Drag start X"},
                "y1": {"type": "NUMBER", "description": "Drag start Y"},
                "x2": {"type": "NUMBER", "description": "Drag end X"},
                "y2": {"type": "NUMBER", "description": "Drag end Y"},
                "duration": {"type": "NUMBER", "description": "Mouse move duration seconds"},
                "image": {"type": "STRING", "description": "Image path to locate on screen"},
                "keys": {"type": "STRING", "description": "Hotkey combo string (e.g. ctrl+shift+s)"},
                "key": {"type": "STRING", "description": "Single key (press)"},
                "direction": {"type": "STRING", "description": "Scroll direction (up/down/left/right)"},
                "amount": {"type": "NUMBER", "description": "Scroll amount"},
                "path": {"type": "STRING", "description": "Screenshot save path (optional)"},
                "seconds": {"type": "NUMBER", "description": "Wait seconds"},
                "timeout": {"type": "NUMBER", "description": "Timeout seconds (wait_image)"},
                "title": {"type": "STRING", "description": "Window title (focus_window)"},
                "description": {"type": "STRING", "description": "Description for AI screen_find/screen_click"},
                "type": {"type": "STRING", "description": "Random data type (random_data)"},
                "field": {"type": "STRING", "description": "User profile field (user_data)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches for flights.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin": {"type": "STRING"},
                "destination": {"type": "STRING"},
                "date": {"type": "STRING"}
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "system_monitor",
        "description": "Monitors system health and settings.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING"},
                "value": {"type": "STRING"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "query_knowledge_graph",
        "description": "Searches Cristine's long-term memory graph for relationships between projects, tech stacks, dates, and other entities.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "search_term": {"type": "STRING", "description": "The entity or project name to search for (e.g., 'Spotify API', 'project X')"}
            },
            "required": ["search_term"]
        }
    },
    {
        "name": "real_time_translation",
        "description": "Translate speech or text in real time using Gemini's linguistic engine.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "mode": {
                    "type": "STRING",
                    "description": "'text' for static strings, 'start_live' for speech mode, 'stop_live' to end."
                },
                "text": {
                    "type": "STRING",
                    "description": "The content to translate (Required for 'text' mode)."
                },
                "source_lang": {
                    "type": "STRING",
                    "description": "Source language (default: English)."
                },
                "target_lang": {
                    "type": "STRING",
                    "description": "Target language (default: Spanish)."
                }
            },
            "required": ["mode"]
        }
    },
    {
        "name": "project_planner",
        "description": "Generate high-level structured project plans, roadmaps, and milestones using AI reasoning.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "project_description": {
                    "type": "STRING", 
                    "description": "Full description of the project, goal, or startup idea."
                },
                "output_format": {
                    "type": "STRING",
                    "description": "'markdown' (default) or 'json'. Saved to projects/ folder."
                }
            },
            "required": ["project_description"]
        }
    },
    {
        "name": "emotional_companion",
        "description": "Provides empathetic, supportive AI responses for emotional and mental health concerns. Use when user wants to talk about feelings, stress, relationships, or needs emotional support.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "text": {
                    "type": "STRING",
                    "description": "The user's emotional concern or input (required)."
                },
                "tone": {
                    "type": "STRING",
                    "description": "Optional tone: 'supportive', 'reflective', 'actionable', or 'auto' (default)."
                },
                "reset": {
                    "type": "BOOLEAN",
                    "description": "If true, start a fresh emotional session."
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "app_switcher",
        "description": "Switches focus to a specific open application window based on intent or keyword (e.g. 'code', 'music', 'browser', 'terminal').",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_keyword": {"type": "STRING", "description": "The application keyword or name (e.g. 'code', 'spotify', 'chrome')"}
            },
            "required": ["app_keyword"]
        }
    },
    {
        "name": "app_cheatsheet",
        "description": "Detects the currently active application and provides useful keyboard shortcuts for it.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action_query": {"type": "STRING", "description": "Optional: Specific action to find shortcut for (e.g. 'freeze panes')"}
            }
        }
    },
    {
        "name": "add_task",
        "description": "Adds a new task to the task list.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task": {"type": "STRING", "description": "Task description (e.g. 'Finish robotics code', 'Study physics chapter')"}
            },
            "required": ["task"]
        }
    },
    {
        "name": "complete_task",
        "description": "Marks a task as complete.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task_id": {"type": "STRING", "description": "Task ID or task name to mark complete"}
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "delete_task",
        "description": "Deletes a task from the task list.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task_id": {"type": "STRING", "description": "Task ID or task name to delete"}
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "show_tasks",
        "description": "Shows all pending and completed tasks.",
        "parameters": {
            "type": "OBJECT",
            "properties": {}
        }
    }
]

class CristineLive:
    def __init__(self, ui: CristineUI):
        self.ui = ui
        self.session = None
        self._loop = None
        self.ui.text_submit_callback = self._handle_user_text
        
        # Register voice command callbacks
        from core.voice_commands import get_voice_command_manager
        vcm = get_voice_command_manager()
        vcm.register_function_callback("activate_cristine", lambda: self.ui.write_log("Cristine activated!", tag="sys"))
        vcm.register_function_callback("minimize", lambda: self.ui.root.iconify())
        vcm.register_function_callback("maximize", lambda: self.ui.root.state("zoomed"))
        vcm.register_function_callback("toggle_compact", lambda: self.ui.toggle_compact())
        vcm.register_function_callback("clear_logs", self._clear_logs)
        vcm.register_function_callback("open_preferences", lambda: self.ui.open_preferences())
    
    def _clear_logs(self):
        """Clear the log text widget"""
        self.ui.log_text.configure(state="normal")
        self.ui.log_text.delete("1.0", "end")
        self.ui.log_text.configure(state="disabled")
        self.ui.write_log("Logs cleared.", tag="sys")

    def _handle_user_text(self, text: str):
        # Check for custom voice commands first
        from core.voice_commands import get_voice_command_manager
        vcm = get_voice_command_manager()
        command = vcm.find_command(text)
        
        if command:
            # Match found - execute command
            result = vcm.execute_command(command)
            status_msg = result.get("message", "Command executed")
            self.ui.write_log(f"CMD: {status_msg}", tag="sys")
            print(f"[VoiceCmd] Executed: {command.phrase}")
            return
        
        # No command match - send to AI
        if not self._loop or not self.session: return
        asyncio.run_coroutine_threadsafe(self.session.send_client_content(turns=[{"parts": [{"text": text}]}], turn_complete=True), self._loop)

    def speak(self, text: str):
        if not self._loop or not self.session: return
        asyncio.run_coroutine_threadsafe(self.session.send_client_content(turns=[{"parts": [{"text": text}]}], turn_complete=True), self._loop)
    
    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime 
        memory, sys_prompt = load_memory(), _load_system_prompt()
        mem_str = format_memory_for_prompt(memory)
        graph_str = graph_memory.format_graph_for_prompt()
        now = datetime.now()
        time_ctx = f"[CURRENT DATE & TIME]\nRight now it is: {now.strftime('%A, %B %d, %Y — %I:%M %p')}\n\n"
        full_prompt = time_ctx + (mem_str + "\n\n" if mem_str else "") + (graph_str + "\n\n" if graph_str else "") + sys_prompt
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction=full_prompt,
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")))
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name, args = fc.name, dict(fc.args or {})
        print(f"[CRISTINE] 🔧 TOOL: {name}")
        try:
            if hasattr(self.ui, "record_tool_run"):
                self.ui.record_tool_run(name, args)
        except Exception:
            pass
        self.ui.set_task_status(name, True)
        loop, result = asyncio.get_event_loop(), "Done."
        try:
            if name == "open_app": r = await loop.run_in_executor(None, lambda: open_app(parameters=args, player=self.ui)); result = r or "Success."
            elif name == "web_search": r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui)); result = r or "Search done."
            elif name == "weather_report": r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui)); result = r or "Weather done."
            elif name == "browser_control": r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui)); result = r or "Browser done."
            elif name == "file_controller": r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui)); result = r or "File done."
            elif name == "send_message": r = await loop.run_in_executor(None, lambda: send_message(parameters=args, player=self.ui)); result = r or "Sent."
            elif name == "reminder": r = await loop.run_in_executor(None, lambda: reminder(parameters=args, player=self.ui)); result = r or "Reminder set."
            elif name == "youtube_video": r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, player=self.ui)); result = r or "YouTube done."
            elif name == "screen_process": threading.Thread(target=screen_process, kwargs={"parameters": args, "player": self.ui}, daemon=True).start(); result = "Vision active."
            elif name == "computer_settings": r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, player=self.ui)); result = r or "Settings done."
            elif name == "cmd_control": r = await loop.run_in_executor(None, lambda: cmd_control(parameters=args, player=self.ui)); result = r or "CMD done."
            elif name == "desktop_control": r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui)); result = r or "Desktop done."
            elif name == "code_helper": r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui)); result = r or "Code done."
            elif name == "dev_agent": r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui)); result = r or "Dev done."
            elif name == "agent_task":
                from agent.task_queue import get_queue; r = get_queue().submit(goal=args.get("goal", ""), speak=True); result = f"Task {r} started."
            elif name == "computer_control": r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui)); result = r or "Control done."
            elif name == "flight_finder": r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui)); result = r or "Flights found."
            elif name == "app_switcher": r = await loop.run_in_executor(None, lambda: app_switcher(parameters=args, player=self.ui)); result = r or "Switched."
            elif name == "app_cheatsheet": r = await loop.run_in_executor(None, lambda: app_cheatsheet(parameters=args, player=self.ui)); result = r or "Cheatsheet done."
            elif name == "system_monitor": r = await loop.run_in_executor(None, lambda: system_monitor_action(parameters=args)); result = r or "Stats done."
            elif name == "real_time_translation":
                r = await loop.run_in_executor(None, lambda: real_time_translation(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Translation complete."
            elif name == "project_planner":
                r = await loop.run_in_executor(None, lambda: project_planner(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Project plan generated."
            elif name == "emotional_companion": r = await loop.run_in_executor(None, lambda: emotional_companion(parameters=args, player=self.ui)); result = r or "I'm here to listen."
            elif name == "add_task":
                task_text = args.get("task", "").strip()
                task_mgr = get_task_manager()
                task = task_mgr.add_task(task_text)
                if task:
                    self.ui._update_task_stats()
                    result = f"✓ Task added: {task.task}"
                    self.ui.write_log(f"Task added: {task.task}", tag="sys")
                else:
                    result = "Failed to add task."
            elif name == "complete_task":
                task_id = args.get("task_id", "").strip()
                task_mgr = get_task_manager()
                # Try to find by ID first, then by name
                success = task_mgr.complete_task(task_id)
                if not success:
                    # Try to find by name
                    for task in task_mgr.tasks:
                        if task.task.lower() == task_id.lower():
                            success = task_mgr.complete_task(task.id)
                            break
                if success:
                    self.ui._update_task_stats()
                    result = f"✓ Task marked as complete: {task_id}"
                    self.ui.write_log(f"Task completed: {task_id}", tag="sys")
                else:
                    result = f"Could not find task: {task_id}"
            elif name == "delete_task":
                task_id = args.get("task_id", "").strip()
                task_mgr = get_task_manager()
                # Try to find by ID first, then by name
                success = task_mgr.delete_task(task_id)
                if not success:
                    # Try to find by name
                    for task in task_mgr.tasks:
                        if task.task.lower() == task_id.lower():
                            success = task_mgr.delete_task(task.id)
                            break
                if success:
                    self.ui._update_task_stats()
                    result = f"✓ Task deleted: {task_id}"
                    self.ui.write_log(f"Task deleted: {task_id}", tag="sys")
                else:
                    result = f"Could not find task: {task_id}"
            elif name == "show_tasks":
                task_mgr = get_task_manager()
                summary = task_mgr.get_task_summary()
                result = summary
                self.ui.write_log(summary, tag="sys")
            elif name == "query_knowledge_graph":
                term = args.get("search_term", "")
                rels = graph_memory.query(term)
                if rels:
                    result = "Knowledge Graph Matches:\n" + "\n".join([f"- {s} --[{p}]--> {o} ({t})" for s, p, o, t in rels])
                else:
                    result = f"No relationships found for '{term}'."
            else: result = f"Unknown tool: {name}"
        except Exception as e:
            result = f"Error: {e}"; traceback.print_exc()
        finally: self.ui.set_task_status(name, False)
        return types.FunctionResponse(id=fc.id, name=name, response={"result": result})

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        stream = await asyncio.to_thread(pya.open, format=FORMAT, channels=CHANNELS, rate=SEND_SAMPLE_RATE, input=True, frames_per_buffer=CHUNK_SIZE)
        try:
            while True:
                data = await asyncio.to_thread(stream.read, CHUNK_SIZE, exception_on_overflow=False)
                process_audio_stream(data, player=self.ui, speak=self.speak)
                if self.ui.speech_mode: await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})
                else: await asyncio.sleep(0.01)
        finally: stream.close()

    async def _receive_audio(self):
        out_buf, in_buf = [], []
        try:
            while True:
                async for response in self.session.receive():
                    if response.data: self.audio_in_queue.put_nowait(response.data)
                    if response.server_content:
                        sc = response.server_content
                        if sc.input_transcription: 
                            txt = sc.input_transcription.text
                            if txt: in_buf.append(txt)
                        if sc.output_transcription:
                            chunk = sc.output_transcription.text
                            if chunk:
                                self.ui.write_log(chunk, tag="ai", is_stream=True)
                                out_buf.append(chunk)
                        if sc.turn_complete:
                            fi, fo = "".join(filter(None, in_buf)).strip(), "".join(filter(None, out_buf)).strip()
                            self.ui.write_log("", tag="ai", is_stream=False) # Finalize line
                            if fi: 
                                self.ui.write_log(fi, tag="you", is_stream=False)
                                threading.Thread(target=_update_memory_async, args=(fi, fo), daemon=True).start()
                            in_buf, out_buf = [], []
                    if response.tool_call:
                        frs = [await self._execute_tool(fc) for fc in response.tool_call.function_calls]
                        await self.session.send_tool_response(function_responses=frs)
        except Exception: traceback.print_exc()

    async def _play_audio(self):
        stream = await asyncio.to_thread(pya.open, format=FORMAT, channels=CHANNELS, rate=RECEIVE_SAMPLE_RATE, output=True)
        try:
            while True:
                chunk = await self.audio_in_queue.get()
                await asyncio.to_thread(stream.write, chunk)
        finally: stream.close()

    async def run(self):
        client = genai.Client(api_key=_get_api_key(), http_options={"api_version": "v1beta"})
        while True:
            try:
                async with client.aio.live.connect(model=LIVE_MODEL, config=self._build_config()) as session:
                    self.session, self._loop = session, asyncio.get_event_loop()
                    self.audio_in_queue, self.out_queue = asyncio.Queue(), asyncio.Queue(maxsize=10)
                    self.ui.write_log("CRISTINE online.")
                    await asyncio.gather(self._send_realtime(), self._listen_audio(), self._receive_audio(), self._play_audio())
            except Exception: traceback.print_exc()
            await asyncio.sleep(3)

def main():
    ui = CristineUI("face.png")
    
    # Initialize Dream Mode System
    dream_tasks = DreamModeTasks(
        on_status_update=lambda msg: ui.write_log(msg, tag="sys"),
        on_task_complete=lambda task: print(f"[DreamMode] ✅ Task complete: {task}")
    )
    
    def on_dream_mode_trigger(enabled_tasks):
        """Callback when Dream Mode should run."""
        ui.dream_mode_active = True
        ui._update_title()
        ui.write_log("🌙 DREAM MODE ACTIVE - Cristine is optimizing...", tag="sys")
        
        # Run Dream Mode tasks in a background thread
        def run_tasks():
            dream_tasks.execute_all_tasks(enabled_tasks)
            ui.dream_mode_active = False
            ui._update_title()
            ui.write_log("✅ Cristine completed nightly optimization.", tag="sys")
        
        threading.Thread(target=run_tasks, daemon=True, name="DreamMode").start()
    
    # Initialize scheduler
    dream_scheduler = DreamModeScheduler(dream_mode_callback=on_dream_mode_trigger)
    dream_scheduler.start()
    
    # Start Cristine
    threading.Thread(target=lambda: (ui.wait_for_api_key(), asyncio.run(CristineLive(ui).run())), daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__": main()
