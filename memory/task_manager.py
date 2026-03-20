"""
Task Manager for Cristine
Manages personal productivity tasks with persistence
"""

import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import sys
import uuid

def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
TASKS_PATH = BASE_DIR / "memory" / "tasks.json"


class Task:
    """Represents a single task"""
    
    def __init__(self, task: str, status: str = "pending", created: str = None, task_id: str = None, completed: str = None):
        self.id = task_id or str(uuid.uuid4())[:8]
        self.task = task
        self.status = status  # "pending" or "completed"
        self.created = created or datetime.now().strftime("%Y-%m-%d")
        self.completed = completed
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON storage"""
        data = {
            "id": self.id,
            "task": self.task,
            "status": self.status,
            "created": self.created
        }
        if self.completed:
            data["completed"] = self.completed
        return data
    
    @staticmethod
    def from_dict(data: Dict) -> 'Task':
        """Create from dictionary"""
        return Task(
            task=data["task"],
            status=data.get("status", "pending"),
            created=data.get("created"),
            task_id=data.get("id"),
            completed=data.get("completed")
        )
    
    def mark_complete(self) -> None:
        """Mark task as completed"""
        self.status = "completed"
        self.completed = datetime.now().strftime("%Y-%m-%d")
    
    def mark_pending(self) -> None:
        """Mark task as pending"""
        self.status = "pending"
        self.completed = None


class TaskManager:
    """Manages tasks - CRUD operations and persistence"""
    
    def __init__(self):
        self.tasks: List[Task] = []
        self._load_tasks()
    
    def _load_tasks(self) -> None:
        """Load tasks from JSON file"""
        try:
            if TASKS_PATH.exists():
                with open(TASKS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.tasks = [Task.from_dict(item) for item in data]
                    print(f"[TaskMgr] Loaded {len(self.tasks)} tasks")
            else:
                self.tasks = []
        except Exception as e:
            print(f"[TaskMgr] Error loading tasks: {e}")
            self.tasks = []
    
    def save_tasks(self) -> bool:
        """Save tasks to JSON file"""
        try:
            TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(TASKS_PATH, "w", encoding="utf-8") as f:
                data = [task.to_dict() for task in self.tasks]
                json.dump(data, f, indent=2)
            print(f"[TaskMgr] Saved {len(self.tasks)} tasks")
            return True
        except Exception as e:
            print(f"[TaskMgr] Error saving tasks: {e}")
            return False
    
    def add_task(self, task_text: str) -> Optional[Task]:
        """Add a new task"""
        try:
            if not task_text or not task_text.strip():
                print("[TaskMgr] Task text cannot be empty")
                return None
            
            # Clean up task text (remove "cristine" prefix if present)
            task_text = task_text.strip()
            if task_text.lower().startswith("cristine "):
                task_text = task_text[9:].strip()
            if task_text.lower().startswith("add task "):
                task_text = task_text[9:].strip()
            
            task = Task(task_text, status="pending")
            self.tasks.append(task)
            self.save_tasks()
            print(f"[TaskMgr] Added task: {task_text}")
            return task
        except Exception as e:
            print(f"[TaskMgr] Error adding task: {e}")
            return None
    
    def delete_task(self, task_id: str) -> bool:
        """Delete a task by ID"""
        try:
            original_count = len(self.tasks)
            self.tasks = [t for t in self.tasks if t.id != task_id]
            
            if len(self.tasks) < original_count:
                self.save_tasks()
                print(f"[TaskMgr] Deleted task {task_id}")
                return True
            return False
        except Exception as e:
            print(f"[TaskMgr] Error deleting task: {e}")
            return False
    
    def complete_task(self, task_id: str) -> bool:
        """Mark a task as complete"""
        try:
            for task in self.tasks:
                if task.id == task_id:
                    task.mark_complete()
                    self.save_tasks()
                    print(f"[TaskMgr] Completed task: {task.task}")
                    return True
            return False
        except Exception as e:
            print(f"[TaskMgr] Error completing task: {e}")
            return False
    
    def uncomplete_task(self, task_id: str) -> bool:
        """Mark a task as pending again"""
        try:
            for task in self.tasks:
                if task.id == task_id:
                    task.mark_pending()
                    self.save_tasks()
                    return True
            return False
        except Exception as e:
            print(f"[TaskMgr] Error uncompleting task: {e}")
            return False
    
    def get_all_tasks(self) -> List[Dict]:
        """Get all tasks as dictionaries"""
        return [task.to_dict() for task in self.tasks]
    
    def get_pending_tasks(self) -> List[Task]:
        """Get all pending tasks"""
        return [t for t in self.tasks if t.status == "pending"]
    
    def get_completed_tasks(self) -> List[Task]:
        """Get all completed tasks"""
        return [t for t in self.tasks if t.status == "completed"]
    
    def get_task_summary(self) -> str:
        """Get summary of tasks for display"""
        pending = self.get_pending_tasks()
        completed = self.get_completed_tasks()
        
        lines = ["Today's Tasks\n"]
        
        if pending or completed:
            for task in pending:
                lines.append(f"[ ] {task.task}")
            for task in completed:
                lines.append(f"[x] {task.task}")
        else:
            lines.append("No tasks yet. Add one to get started!")
        
        return "\n".join(lines)
    
    def cleanup_old_tasks(self) -> int:
        """Remove tasks not touched for 7 days. Returns count of removed tasks."""
        try:
            from datetime import datetime, timedelta
            now = datetime.now()
            cutoff_date = now - timedelta(days=7)
            cutoff_str = cutoff_date.strftime("%Y-%m-%d")
            
            initial_count = len(self.tasks)
            
            # Remove tasks older than 7 days
            self.tasks = [
                task for task in self.tasks 
                if task.created > cutoff_str or task.status == "pending"  # Keep pending tasks regardless
            ]
            
            removed = initial_count - len(self.tasks)
            if removed > 0:
                self.save_tasks()
                print(f"[TaskMgr] Auto-cleanup: Removed {removed} old completed tasks")
            
            return removed
        except Exception as e:
            print(f"[TaskMgr] Error in cleanup: {e}")
            return 0
    
    def clear_all_tasks(self) -> bool:
        """Delete all tasks"""
        try:
            self.tasks = []
            self.save_tasks()
            print("[TaskMgr] Cleared all tasks")
            return True
        except Exception as e:
            print(f"[TaskMgr] Error clearing tasks: {e}")
            return False


# Global instance
_task_manager = None

def get_task_manager() -> TaskManager:
    """Get or create global task manager instance"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
