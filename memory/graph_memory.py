import sqlite3
import json
from datetime import datetime
from pathlib import Path
import sys

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
DB_PATH = BASE_DIR / "memory" / "knowledge_graph.db"

class ContextualMemoryGraph:
    def __init__(self):
        self._init_db()

    def _init_db(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS triplets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object TEXT NOT NULL,
                    context TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_subject ON triplets(subject)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_object ON triplets(object)")

    def add_relationship(self, subject: str, predicate: str, obj: str, context: str = None):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO triplets (subject, predicate, object, context) VALUES (?, ?, ?, ?)",
                (subject, predicate, obj, context)
            )

    def query(self, search_term: str):
        """Finds triplets where subject or object matches the search term."""
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute(
                "SELECT subject, predicate, object, timestamp FROM triplets WHERE subject LIKE ? OR object LIKE ?",
                (f"%{search_term}%", f"%{search_term}%")
            )
            return cursor.fetchall()

    def get_all_relationships(self, limit=50):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute(
                "SELECT subject, predicate, object, timestamp FROM triplets ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )
            return cursor.fetchall()

    def format_graph_for_prompt(self) -> str:
        rels = self.get_all_relationships(20)
        if not rels:
            return ""
        
        lines = ["[KNOWLEDGE GRAPH]"]
        for s, p, o, t in rels:
            # Simple formatting: (Date) Subject -> Predicate -> Object
            date_str = t.split(" ")[0] if " " in t else t
            lines.append(f"- ({date_str}) {s} --[{p}]--> {o}")
        
        return "\n".join(lines) + "\n"

# Singleton instance
graph_memory = ContextualMemoryGraph()
