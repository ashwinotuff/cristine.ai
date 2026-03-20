"""Emotional Companion Chat Action

Provides empathetic, supportive AI responses for emotional/mental health concerns.
Uses Gemini API with a warm, human-like tone and optional session context.

Usage:
    result = emotional_companion(
        parameters={"text": "Help me with work stress"},
        player=ui_instance,
    )
"""

import json
from pathlib import Path

import google.generativeai as genai

from memory.emotional_session import get_session, reset_session


def _get_api_key() -> str:
    """Retrieve Gemini API key from config."""
    config_path = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (data.get("gemini_api_key") or "").strip()
    except Exception as e:
        print(f"[EmotionalCompanion] API key error: {e}")
        return ""


EMPATHETIC_SYSTEM_PROMPT = """
You are Cristine, a deeply empathetic and compassionate AI companion.
Your role is to provide warm, supportive, and understanding responses to emotional and mental health concerns.

CORE PRINCIPLES:
1. Validation: Always affirm the user's feelings. Never dismiss or minimize their concerns.
2. Active Listening: Reflect back what you hear to show understanding.
3. Non-Clinical Warmth: Avoid clinical or diagnostic language. Sound genuinely human and caring.
4. Hope and Agency: Gently encourage positive actions, but without pressure.
5. Continuity: Reference previous concerns from this session to show you remember and care.
6. Boundaries: If the user expresses severe crises (suicidal ideation, self-harm),
   acknowledge their pain, encourage professional help, and provide crisis resources.

TONE:
- Warm, compassionate, understanding, and genuinely interested
- Speak as a friend who cares, not a therapist or chatbot
- Use gentle humor where appropriate, but never at the user's expense
- Maintain a calm, patient demeanor even if the user is frustrated

RESPONSE STRUCTURE:
1. Validate their feeling (1-2 sentences)
2. Show understanding through reflection (1-2 sentences)
3. Offer a gentle insight, question, or supportive suggestion (2-3 sentences)
4. Leave space for them to continue sharing or take action (1 sentence)

Remember: You are here to listen, understand, and support - not to fix or judge.
"""


def _call_gemini_with_empathy(user_concern: str, session_context: str, tone: str = "auto", player=None) -> str:
    """Call Gemini API with the empathetic system prompt and optional session context."""

    api_key = _get_api_key()
    if not api_key:
        return "Empathy module not configured. Add your Gemini API key in Preferences."

    genai.configure(api_key=api_key)

    tone_instruction = ""
    if tone == "supportive":
        tone_instruction = "\nFocus on validation and comfort. The user needs to feel heard."
    elif tone == "reflective":
        tone_instruction = "\nHelp the user explore their feelings deeper. Ask gentle questions."
    elif tone == "actionable":
        tone_instruction = "\nGently suggest constructive steps the user might consider."

    full_prompt = f"{EMPATHETIC_SYSTEM_PROMPT}{tone_instruction}"
    if session_context:
        full_prompt += f"\n\nPrevious conversation in this session:\n{session_context}"

    fallback_msg = (
        "I'm having a moment of trouble listening, but I'm still here for you. "
        "Please tell me what's on your mind, and let's talk through it together."
    )

    # Two-shot retry: small model first, then a more capable fallback.
    model_candidates = [
        ("gemini-2.5-flash-lite", 30),
        ("gemini-2.5-flash", 45),
    ]

    last_err = None
    for attempt, (model_name, timeout_s) in enumerate(model_candidates, 1):
        try:
            model = genai.GenerativeModel(model_name=model_name, system_instruction=full_prompt)
            response = model.generate_content(
                f"User's concern:\n{user_concern}",
                timeout=int(timeout_s),
            )
            text = (getattr(response, "text", "") or "").strip()
            if text:
                return text
            last_err = RuntimeError("Empty response from Gemini")
        except Exception as e:
            last_err = e
            msg = f"[EmotionalCompanion] Gemini error (attempt {attempt}/{len(model_candidates)}): {e}"
            print(msg)
            if player:
                try:
                    player.write_log(msg, tag="sys", is_stream=False)
                except Exception:
                    pass
            try:
                import time as _time

                _time.sleep(0.8)
            except Exception:
                pass

    msg = f"[EmotionalCompanion] Gemini failed: {last_err}"
    print(msg)
    if player:
        try:
            player.write_log(msg, tag="sys", is_stream=False)
        except Exception:
            pass

    return fallback_msg


def emotional_companion(parameters: dict, player=None, session_memory=None) -> str:
    """Main action for Emotional Companion Chat."""

    user_text = (parameters or {}).get("text", "").strip()
    tone = (parameters or {}).get("tone", "auto")
    should_reset = bool((parameters or {}).get("reset", False))

    if not user_text:
        return "I'm here to listen. What's on your mind right now?"

    if should_reset:
        reset_session()

    session = get_session()
    session_context = session.get_context()
    mood_trend = session.get_mood_trend()

    ai_response = _call_gemini_with_empathy(user_text, session_context, tone, player=player)

    mood_tag = _detect_mood(user_text)
    session.add_turn(user_text, ai_response, mood_tag)

    if player:
        player.write_log(f"You (emotional): {user_text}", tag="you", is_stream=False)
        if len(session.conversation_turns) % 3 == 0:
            player.write_log(f"[Session] {mood_trend}", tag="sys", is_stream=False)

    print(f"[EmotionalCompanion] Session: {session.session_id} | Mood: {mood_tag}")

    return ai_response


def _detect_mood(text: str) -> str:
    """Simple heuristic to detect mood from user text."""

    text_lower = text.lower()

    if any(word in text_lower for word in ["stress", "anxiety", "anxious", "worried", "overwhelm", "panic"]):
        return "stressed"

    if any(word in text_lower for word in ["sad", "depressed", "unhappy", "miserable", "down", "lonely"]):
        return "sad"

    if any(word in text_lower for word in ["angry", "frustrated", "furious", "mad", "irritated", "annoyed"]):
        return "frustrated"

    if any(word in text_lower for word in ["better", "hopeful", "grateful", "happy", "excited", "good"]):
        return "hopeful"

    if any(word in text_lower for word in ["confused", "lost", "don't know", "unclear", "uncertain"]):
        return "confused"

    return "neutral"
