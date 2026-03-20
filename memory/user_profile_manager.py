"""
User Profile Manager
Handles import, storage, viewing, and deletion of user personal data
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import re

class UserProfileManager:
    """Manages user profile data with import/export capabilities"""
    
    PROFILE_PATH = Path(__file__).parent / "user_profile.json"
    
    def __init__(self):
        self.profile = self._load_profile()
    
    @staticmethod
    def _get_default_profile() -> Dict:
        """Get default profile structure"""
        return {
            "instructions": [],
            "identity": [],
            "career": [],
            "projects": [],
            "preferences": []
        }
    
    def _load_profile(self) -> Dict:
        """Load user profile from JSON file"""
        try:
            if self.PROFILE_PATH.exists():
                with open(self.PROFILE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"[UserProfile] Error loading profile: {e}")
        return self._get_default_profile()
    
    def save_profile(self) -> bool:
        """Save user profile to JSON file"""
        try:
            self.PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(self.PROFILE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.profile, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[UserProfile] Error saving profile: {e}")
            return False
    
    def import_data(self, text: str) -> Dict[str, any]:
        """
        Parse and import user data from exported text
        Returns: {
            'success': bool,
            'imported': {'instructions': [...], 'identity': [...], ...},
            'errors': [list of errors]
        }
        """
        errors = []
        imported = self._get_default_profile()
        
        if not text or not text.strip():
            return {'success': False, 'imported': {}, 'errors': ['No data provided']}
        
        # Split by category headers
        sections = self._parse_sections(text)
        
        for category in ['instructions', 'identity', 'career', 'projects', 'preferences']:
            if category in sections:
                entries = self._parse_entries(sections[category])
                # Avoid duplicates
                for entry in entries:
                    if not self._entry_exists(category, entry):
                        imported[category].append(entry)
        
        # Add imported data to profile
        for category in imported:
            before_count = len(self.profile[category])
            for entry in imported[category]:
                if not self._entry_exists(category, entry):
                    self.profile[category].append(entry)
            after_count = len(self.profile[category])
            if after_count > before_count:
                print(f"[UserProfile] Added {after_count - before_count} entries to {category}")
        
        success = self.save_profile()
        return {
            'success': success,
            'imported': imported,
            'errors': errors,
            'summary': self._get_import_summary(imported)
        }
    
    def _parse_sections(self, text: str) -> Dict[str, str]:
        """Extract category sections from text"""
        sections = {}
        
        # Normalize text
        text = text.replace('\r\n', '\n')
        
        # Define category patterns (case-insensitive)
        patterns = {
            'instructions': r'instructions?:',
            'identity': r'identit(y|ies):',
            'career': r'career:',
            'projects': r'projects?:',
            'preferences': r'preferences?:'
        }
        
        for category, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                start = match.start()
                # Find next category
                remaining_text = text[match.end():]
                next_match = None
                next_pos = len(text)
                
                for other_cat, other_pattern in patterns.items():
                    if other_cat != category:
                        m = re.search(other_pattern, remaining_text, re.IGNORECASE)
                        if m and m.start() < next_pos:
                            next_pos = m.start()
                
                if next_pos < len(remaining_text):
                    sections[category] = remaining_text[:next_pos].strip()
                else:
                    sections[category] = remaining_text.strip()
        
        return sections
    
    def _parse_entries(self, section_text: str) -> List[Dict]:
        """Parse individual entries from a section"""
        entries = []
        lines = section_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Try to extract date and content
            date_match = re.match(r'\[([^\]]+)\]\s*-\s*(.+)', line)
            if date_match:
                date_str = date_match.group(1).strip()
                content = date_match.group(2).strip()
                entry = {
                    'date': date_str if date_str.lower() != 'unknown' else 'unknown',
                    'content': content
                }
            else:
                # No date format, try to extract content
                if re.match(r'^[-•]\s*', line):
                    content = re.sub(r'^[-•]\s*', '', line).strip()
                else:
                    content = line
                
                entry = {
                    'date': 'unknown',
                    'content': content
                }
            
            if entry['content']:
                entries.append(entry)
        
        return entries
    
    def _entry_exists(self, category: str, entry: Dict) -> bool:
        """Check if entry already exists in category"""
        if category not in self.profile:
            return False
        
        for existing in self.profile[category]:
            if existing.get('content') == entry.get('content'):
                return True
        
        return False
    
    def _get_import_summary(self, imported: Dict) -> str:
        """Generate summary of imported data"""
        counts = {cat: len(entries) for cat, entries in imported.items() if entries}
        if not counts:
            return "No data imported"
        
        summary_parts = []
        for cat in ['instructions', 'identity', 'career', 'projects', 'preferences']:
            if counts.get(cat, 0) > 0:
                summary_parts.append(f"{counts[cat]} {cat}")
        
        return f"Imported: {', '.join(summary_parts)}"
    
    def get_profile(self) -> Dict:
        """Get current user profile"""
        return self.profile
    
    def get_category(self, category: str) -> List[Dict]:
        """Get entries for a specific category"""
        return self.profile.get(category, [])
    
    def delete_entry(self, category: str, index: int) -> bool:
        """Delete specific entry from category"""
        try:
            if 0 <= index < len(self.profile.get(category, [])):
                del self.profile[category][index]
                return self.save_profile()
        except Exception as e:
            print(f"[UserProfile] Error deleting entry: {e}")
        return False
    
    def delete_category(self, category: str) -> bool:
        """Delete all entries in a category"""
        try:
            if category in self.profile:
                self.profile[category] = []
                return self.save_profile()
        except Exception as e:
            print(f"[UserProfile] Error deleting category: {e}")
        return False
    
    def delete_all(self) -> bool:
        """Delete all user profile data"""
        try:
            self.profile = self._get_default_profile()
            return self.save_profile()
        except Exception as e:
            print(f"[UserProfile] Error deleting all: {e}")
        return False
    
    def get_export_prompt(self) -> str:
        """Get the copyable prompt for users to export data from other AIs"""
        return """PROMPT TO EXPORT USER DATA

Export all of my stored memories and any context you've learned about me from past conversations. Preserve my words verbatim where possible, especially for instructions and preferences.

## Categories (output in this order):

1. **Instructions**: Rules I've explicitly asked you to follow going forward — tone, format, style, "always do X", "never do Y", and corrections to your behavior. Only include rules from stored memories, not from conversations.

2. **Identity**: Name, age, location, education, family, relationships, languages, and personal interests.

3. **Career**: Current and past roles, companies, and general skill areas.

4. **Projects**: Projects I meaningfully built or committed to. Ideally ONE entry per project. Include what it does, current status, and any key decisions. Use the project name or a short descriptor as the first words of the entry.

5. **Preferences**: Opinions, tastes, and working-style preferences that apply broadly.

## Format:

Use section headers for each category. Within each category, list one entry per line, sorted by oldest date first. Format each line as:

[YYYY-MM-DD] - Entry content here.

If no date is known, use [unknown] instead.

## Output:

• Wrap the entire export in a single code block for easy copying.
• After the code block, state whether this is the complete set or if more remain."""
    
    def is_empty(self) -> bool:
        """Check if profile has any data"""
        for entries in self.profile.values():
            if entries:
                return False
        return True


# Global instance
_profile_manager = None

def get_profile_manager() -> UserProfileManager:
    """Get or create global profile manager instance"""
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = UserProfileManager()
    return _profile_manager
