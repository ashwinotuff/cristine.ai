"""
Dream Mode Tasks for Cristine
Executes maintenance and optimization tasks during idle/night hours
"""

import os
import threading
import time
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime
import sys
import json
import requests
from typing import Callable


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()


class DreamModeTasks:
    """Executes Dream Mode maintenance tasks."""

    def __init__(self, on_status_update: Callable = None, on_task_complete: Callable = None):
        """
        Initialize Dream Mode Tasks.
        
        Args:
            on_status_update: Callback for status updates (receives message string)
            on_task_complete: Callback when a task completes (receives task name)
        """
        self.on_status_update = on_status_update
        self.on_task_complete = on_task_complete
        self._running = False
        self._cancel_flag = threading.Event()

    def _log(self, msg: str) -> None:
        """Log a message."""
        print(f"[DreamMode] {msg}")
        if self.on_status_update:
            self.on_status_update(msg)

    def cancel(self) -> None:
        """Signal tasks to cancel."""
        self._cancel_flag.set()
        print("[DreamMode] ⏸️ Cancellation requested")

    def reset_cancel(self) -> None:
        """Reset the cancel flag."""
        self._cancel_flag.clear()

    def is_cancelled(self) -> bool:
        """Check if cancellation was requested."""
        return self._cancel_flag.is_set()

    def execute_all_tasks(self, enabled_tasks: dict) -> None:
        """
        Execute all enabled Dream Mode tasks.
        
        Args:
            enabled_tasks: Dict with keys like:
                - file_organization: bool
                - knowledge_graph: bool
                - self_learning: bool
        """
        self._running = True
        self.reset_cancel()
        
        self._log("🌙 Dream Mode ACTIVATED")
        start_time = time.time()
        
        try:
            if enabled_tasks.get("file_organization"):
                self._organize_files()
                if self.on_task_complete:
                    self.on_task_complete("file_organization")
                if self.is_cancelled():
                    self._log("⏸️ User activity detected - Dream Mode paused")
                    return
            
            if enabled_tasks.get("knowledge_graph"):
                self._improve_knowledge_graph()
                if self.on_task_complete:
                    self.on_task_complete("knowledge_graph")
                if self.is_cancelled():
                    self._log("⏸️ User activity detected - Dream Mode paused")
                    return
            
            if enabled_tasks.get("self_learning"):
                self._run_self_learning()
                if self.on_task_complete:
                    self.on_task_complete("self_learning")
                if self.is_cancelled():
                    self._log("⏸️ User activity detected - Dream Mode paused")
                    return
            
            elapsed = time.time() - start_time
            self._log(f"✅ Dream Mode completed in {elapsed:.0f}s")
        
        except Exception as e:
            self._log(f"❌ Error during Dream Mode: {e}")
        finally:
            self._running = False

    # ========== TASK 1: FILE ORGANIZATION ==========

    def _organize_files(self) -> None:
        """Organize files in user directories."""
        self._log("📁 Starting File Organization...")
        
        # Define directories to organize
        user_home = Path.home()
        dirs_to_organize = [
            user_home / "Desktop",
            user_home / "Downloads",
        ]
        
        # Define file category mappings
        categories = {
            "Documents": [".pdf", ".docx", ".doc", ".txt", ".xlsx", ".xls", ".pptx", ".ppt"],
            "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico"],
            "Videos": [".mp4", ".avi", ".mkv", ".mov", ".flv", ".wmv", ".webm"],
            "Code": [".py", ".js", ".ts", ".java", ".cpp", ".c", ".cs", ".go", ".rs", ".html", ".css", ".jsx", ".tsx"],
            "Archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"],
        }
        
        for directory in dirs_to_organize:
            if not directory.exists():
                continue
            
            if self.is_cancelled():
                return
            
            self._log(f"  📂 Organizing {directory.name}...")
            organized_count = 0
            
            try:
                # Iterate through files in directory
                for item in directory.iterdir():
                    if self.is_cancelled():
                        return
                    
                    # Skip directories
                    if item.is_dir():
                        continue
                    
                    # Skip system files
                    if item.name.startswith("."):
                        continue
                    
                    file_ext = item.suffix.lower()
                    
                    # Find matching category
                    target_category = None
                    for category, extensions in categories.items():
                        if file_ext in extensions:
                            target_category = category
                            break
                    
                    if target_category:
                        # Create category folder if it doesn't exist
                        target_dir = directory / target_category
                        try:
                            target_dir.mkdir(exist_ok=True)
                            # Move file to category folder
                            new_path = target_dir / item.name
                            
                            # Handle duplicate names
                            counter = 1
                            while new_path.exists():
                                name_parts = item.stem, f"_{counter}", item.suffix
                                new_name = "".join(name_parts)
                                new_path = target_dir / new_name
                                counter += 1
                            
                            # Move the file
                            shutil.move(str(item), str(new_path))
                            organized_count += 1
                        except Exception as e:
                            # Continue if a single file fails
                            pass
                
                self._log(f"  ✅ Organized {organized_count} files in {directory.name}")
            
            except Exception as e:
                self._log(f"  ⚠️ Error organizing {directory.name}: {e}")

    # ========== TASK 2: KNOWLEDGE GRAPH IMPROVEMENT ==========

    def _improve_knowledge_graph(self) -> None:
        """Optimize and improve the knowledge graph."""
        self._log("🧠 Starting Knowledge Graph Optimization...")
        
        db_path = BASE_DIR / "memory" / "knowledge_graph.db"
        
        if not db_path.exists():
            self._log("  ⚠️ Knowledge graph database not found")
            return
        
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                
                if self.is_cancelled():
                    return
                
                # Step 1: Remove duplicate triplets
                self._log("  🔍 Removing duplicate triplets...")
                cursor = conn.execute("""
                    SELECT id, subject, predicate, object FROM triplets
                    ORDER BY id DESC
                """)
                rows = cursor.fetchall()
                duplicates_removed = 0
                
                seen = set()
                to_delete = []
                for row_id, subject, predicate, obj in rows:
                    key = (subject, predicate, obj)
                    if key in seen:
                        to_delete.append(row_id)
                        duplicates_removed += 1
                    else:
                        seen.add(key)
                
                if to_delete:
                    for rid in to_delete:
                        conn.execute("DELETE FROM triplets WHERE id = ?", (rid,))
                    conn.commit()
                
                self._log(f"  ✅ Removed {duplicates_removed} duplicates")
                
                if self.is_cancelled():
                    return
                
                # Step 2: Rebuild indexes
                self._log("  🔨 Rebuilding indexes...")
                conn.execute("REINDEX")
                conn.commit()
                self._log("  ✅ Indexes rebuilt")
                
                if self.is_cancelled():
                    return
                
                # Step 3: Analyze table for query optimization
                self._log("  📊 Analyzing table statistics...")
                conn.execute("ANALYZE")
                conn.commit()
                self._log("  ✅ Statistics updated")
                
                # Step 4: Vacuum to reclaim space
                self._log("  🧹 Vacuuming database...")
                conn.execute("VACUUM")
                self._log("  ✅ Database optimized")
                
                # Report stats
                res = conn.execute("SELECT COUNT(*) FROM triplets").fetchone()
                triplet_count = res[0] if res else 0
                self._log(f"  📈 Knowledge graph now contains {triplet_count} triplets")
        
        except Exception as e:
            self._log(f"  ❌ Error improving knowledge graph: {e}")

    # ========== TASK 3: SELF-LEARNING (ONLINE RESEARCH) ==========

    def _run_self_learning(self) -> None:
        """Perform background self-learning tasks."""
        self._log("🔍 Starting Self-Learning Mode...")
        self._log("  📚 Gathering knowledge from online sources...")
        
        # Topics to research (could be expanded)
        research_topics = [
            "Python programming best practices",
            "AI assistant design patterns",
            "System automation techniques",
            "Natural language processing advances",
            "User interface design principles",
        ]
        
        try:
            for topic in research_topics:
                if self.is_cancelled():
                    return
                
                self._log(f"  🔎 Researching: {topic[:40]}...")
                
                try:
                    # Attempt to fetch knowledge (using DuckDuckGo API or similar)
                    knowledge = self._fetch_topic_knowledge(topic)
                    
                    if knowledge:
                        # Store the knowledge
                        self._store_knowledge(topic, knowledge)
                        self._log(f"  💾 Stored knowledge about {topic[:30]}...")
                    
                except Exception as e:
                    self._log(f"  ⚠️ Could not fetch {topic[:30]}: {str(e)[:40]}")
                
                # Small delay between requests
                time.sleep(2)
            
            self._log("  ✅ Self-learning session completed")
        
        except Exception as e:
            self._log(f"  ❌ Error during self-learning: {e}")

    def _fetch_topic_knowledge(self, topic: str) -> str:
        """
        Fetch knowledge about a topic from online sources.
        Uses safe HTTP requests without executing any code.
        """
        try:
            # Use a simple search API (e.g., DuckDuckGo)
            # This is silent - no browser opens
            url = f"https://api.duckduckgo.com/?q={topic}&format=json&no_html=1"
            
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract useful information
            abstract = data.get("AbstractText", "")
            if abstract:
                return abstract[:500]  # Return first 500 chars
            
            return None
        
        except Exception as e:
            return None

    def _store_knowledge(self, topic: str, knowledge: str) -> None:
        """Store fetched knowledge in memory."""
        try:
            memory_path = BASE_DIR / "memory" / "long_term.json"
            
            # Load existing memory
            if memory_path.exists():
                with open(memory_path, "r", encoding="utf-8") as f:
                    memory = json.load(f)
            else:
                memory = {"identity": {}, "preferences": {}, "relationships": {}, "notes": {}}
            
            # Store in notes section
            if "notes" not in memory:
                memory["notes"] = {}
            
            memory["notes"][f"learned_{topic.replace(' ', '_')}"] = {
                "value": knowledge[:300],
                "timestamp": datetime.now().isoformat()
            }
            
            # Save back
            with open(memory_path, "w", encoding="utf-8") as f:
                json.dump(memory, f, indent=2)
        
        except Exception as e:
            pass  # Silently fail - don't disrupt Dream Mode
