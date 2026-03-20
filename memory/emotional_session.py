"""
Emotional Session Memory
Manages conversation context for the Emotional Companion Chat feature.
Stores user concerns, AI responses, and mood trends within a session.
"""

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
import sys
from typing import Optional, List, Dict, Any


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
EMOTIONAL_SESSIONS_DIR = BASE_DIR / "memory" / "emotional_sessions"
SESSION_DB = BASE_DIR / "memory" / "emotional_sessions.db"
_session_lock = threading.Lock()


class EmotionalSession:
    """Manages a single emotional companion session."""
    
    def __init__(self, session_id: Optional[str] = None):
        EMOTIONAL_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or self._generate_session_id()
        self.conversation_turns: List[Dict[str, str]] = []
        self.mood_tags: List[str] = []
        self.created_at = datetime.now().isoformat()
        self.last_updated = self.created_at
        self._context_window = 10  # Remember last 10 turns for context
        self._load_from_db()
    
    @staticmethod
    def _generate_session_id() -> str:
        """Generate a unique session ID."""
        return datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def _load_from_db(self) -> None:
        """Load existing session from database if it exists."""
        try:
            with sqlite3.connect(SESSION_DB) as conn:
                cursor = conn.execute(
                    "SELECT conversation, mood_tags, created_at, last_updated FROM emotional_sessions WHERE session_id = ?",
                    (self.session_id,)
                )
                row = cursor.fetchone()
                if row:
                    conv_json, mood_json, created, updated = row
                    self.conversation_turns = json.loads(conv_json)
                    self.mood_tags = json.loads(mood_json)
                    self.created_at = created
                    self.last_updated = updated
        except Exception as e:
            print(f"[EmotionalSession] ⚠️ Load error: {e}")
    
    def _init_db(self) -> None:
        """Ensure database table exists."""
        try:
            with sqlite3.connect(SESSION_DB) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS emotional_sessions (
                        session_id TEXT PRIMARY KEY,
                        conversation TEXT NOT NULL,
                        mood_tags TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        last_updated TEXT NOT NULL
                    )
                """)
                conn.commit()
        except Exception as e:
            print(f"[EmotionalSession] ⚠️ DB init error: {e}")
    
    def add_turn(self, user_text: str, ai_response: str, mood_tag: Optional[str] = None) -> None:
        """Add a conversation turn to the session."""
        turn = {
            "timestamp": datetime.now().isoformat(),
            "user": user_text,
            "ai": ai_response,
            "mood_tag": mood_tag or "neutral"
        }
        with _session_lock:
            self.conversation_turns.append(turn)
            if mood_tag:
                self.mood_tags.append(mood_tag)
            self.last_updated = datetime.now().isoformat()
            self._persist()
    
    def get_context(self) -> str:
        """Return formatted conversation history for prompt injection."""
        if not self.conversation_turns:
            return ""
        
        # Get last N turns (context window)
        recent_turns = self.conversation_turns[-self._context_window:]
        lines = ["[EMOTIONAL SESSION CONTEXT]"]
        for turn in recent_turns:
            lines.append(f"• User: {turn['user']}")
            lines.append(f"  Cristine: {turn['ai']}")
        
        return "\n".join(lines) + "\n"
    
    def get_mood_trend(self) -> str:
        """Analyze and return mood trend summary."""
        if not self.mood_tags:
            return "Mood trend: Not yet established."
        
        # Count occurrences of each mood
        mood_counts = {}
        for tag in self.mood_tags:
            mood_counts[tag] = mood_counts.get(tag, 0) + 1
        
        most_common = max(mood_counts, key=mood_counts.get)
        return f"Mood trend: Predominantly {most_common}. Recent variations: {', '.join(set(self.mood_tags[-3:]))}"
    
    def _persist(self) -> None:
        """Save session to database."""
        try:
            self._init_db()
            with sqlite3.connect(SESSION_DB) as conn:
                conv_json = json.dumps(self.conversation_turns)
                mood_json = json.dumps(self.mood_tags)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO emotional_sessions 
                    (session_id, conversation, mood_tags, created_at, last_updated)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (self.session_id, conv_json, mood_json, self.created_at, self.last_updated)
                )
                conn.commit()
        except Exception as e:
            print(f"[EmotionalSession] ⚠️ Persist error: {e}")
    
    def clear(self) -> None:
        """Clear this session's data."""
        with _session_lock:
            self.conversation_turns = []
            self.mood_tags = []
            try:
                with sqlite3.connect(SESSION_DB) as conn:
                    conn.execute("DELETE FROM emotional_sessions WHERE session_id = ?", (self.session_id,))
                    conn.commit()
            except Exception as e:
                print(f"[EmotionalSession] ⚠️ Clear error: {e}")


# Global session instance (persists across tool calls within a session)
_current_session: Optional[EmotionalSession] = None


def get_session() -> EmotionalSession:
    """Get or create the current emotional session."""
    global _current_session
    if _current_session is None:
        _current_session = EmotionalSession()
    return _current_session


def reset_session() -> None:
    """Reset the global session (e.g., when user starts fresh emotional chat)."""
    global _current_session
    if _current_session:
        _current_session.clear()
    _current_session = None
