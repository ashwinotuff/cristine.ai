"""
Personality Context Generator
Generates AI prompt context based on user personality preferences
"""

from pathlib import Path
import json
import sys

def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
PREFS_PATH = BASE_DIR / "config" / "preferences.json"

def load_preferences():
    """Load preferences from JSON"""
    try:
        if PREFS_PATH.exists():
            with open(PREFS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def get_personality_context() -> str:
    """
    Generate personality instruction text to include in AI prompts
    
    Returns: A formatted string describing the personality settings
    """
    prefs = load_preferences()
    
    tone = prefs.get("ai_personality_tone", "friendly").capitalize()
    verbosity = prefs.get("ai_personality_verbosity", "balanced").capitalize()
    humor = prefs.get("ai_personality_humor", "light").capitalize()
    style = prefs.get("ai_personality_style", "jarvis")
    
    # Map style values to display names
    style_display = {
        "neutral": "Neutral AI Assistant",
        "jarvis": "Jarvis-like Butler",
        "companion": "Friendly Companion",
        "technical": "Technical Expert"
    }
    
    style_text = style_display.get(style, "Jarvis-like Butler")
    
    context = f"""PERSONALITY DIRECTIVE:
When responding to the user, adopt the following personality traits:

Tone: {tone}
Response Length: {verbosity}
Humor: {humor}
Style: {style_text}

These settings only affect your response style and tone, not your system logic or technical accuracy.
Always prioritize clarity and helpfulness while maintaining these personality traits."""
    
    return context

def get_personality_dict() -> dict:
    """Get personality settings as a dictionary"""
    prefs = load_preferences()
    return {
        "tone": prefs.get("ai_personality_tone", "friendly"),
        "verbosity": prefs.get("ai_personality_verbosity", "balanced"),
        "humor": prefs.get("ai_personality_humor", "light"),
        "style": prefs.get("ai_personality_style", "jarvis"),
    }

def inject_personality_into_prompt(prompt: str) -> str:
    """
    Inject personality context into an AI prompt
    
    Args:
        prompt: The original user prompt
        
    Returns:
        The prompt with personality context prepended
    """
    personality = get_personality_context()
    return f"{personality}\n\nUser Request:\n{prompt}"
