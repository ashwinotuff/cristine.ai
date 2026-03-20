import json
import os
import sys
import threading
from pathlib import Path
import google.generativeai as genai

# ─── REAL-TIME TRANSLATION STATE ───────────────────────────────────────────
_translation_mode = False
_source_lang      = "English"
_target_lang      = "Spanish"
_audio_buffer     = bytearray()
_lock             = threading.Lock()

def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

def _get_api_key() -> str:
    """Loads API key from config."""
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("gemini_api_key", "")
    except Exception:
        return ""

def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """Uses Gemini to translate text between languages."""
    if not text:
        return "No text provided for translation."
    
    try:
        genai.configure(api_key=_get_api_key())
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        prompt = (
            f"You are a professional translator. Translate the following text from "
            f"{source_lang} to {target_lang}. Return ONLY the translated text.\n\n"
            f"Text: {text}"
        )
        
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Translation error: {str(e)}"

def start_live_translation(source_lang: str, target_lang: str) -> str:
    """Enables real-time speech translation mode."""
    global _translation_mode, _source_lang, _target_lang
    with _lock:
        _translation_mode = True
        _source_lang      = source_lang
        _target_lang      = target_lang
    return f"Live translation active: {source_lang} -> {target_lang}"

def stop_live_translation() -> str:
    """Disables real-time speech translation mode."""
    global _translation_mode
    with _lock:
        _translation_mode = False
    return "Live translation deactivated."

def process_audio_stream(audio_chunk: bytes, player=None, speak=None):
    """
    Processes audio chunks from the main stream.
    In a full production implementation, this would use a VAD (Voice Activity Detection)
    to segment audio and send to an STT engine (like Whisper or Gemini).
    """
    global _translation_mode, _audio_buffer, _source_lang, _target_lang
    
    if not _translation_mode:
        return
    
    # Placeholder for streaming STT + Translation logic
    # This function is designed to be hooked into the main.py _listen_audio loop.
    pass

def real_time_translation(parameters: dict, player=None, speak=None) -> str:
    """
    Main entry point for Cristine's agent/live system.
    
    parameters:
        text        : Text to translate (if mode is 'text')
        source_lang : Source language
        target_lang : Target language
        mode        : 'text' | 'start_live' | 'stop_live'
    """
    try:
        p      = parameters or {}
        mode   = p.get("mode", "text").lower().strip()
        source = p.get("source_lang", "English")
        target = p.get("target_lang", "Spanish")
        text   = p.get("text", "")

        if mode == "text":
            result = translate_text(text, source, target)
            if player:
                player.write_log(f"Translation ({target}): {result}", tag="ai")
            return json.dumps({"status": "success", "result": result, "mode": "text"})

        elif mode == "start_live":
            msg = start_live_translation(source, target)
            if player:
                player.write_log(f"SYS: {msg}", tag="sys")
            return json.dumps({"status": "success", "message": msg, "mode": "live_start"})

        elif mode == "stop_live":
            msg = stop_live_translation()
            if player:
                player.write_log(f"SYS: {msg}", tag="sys")
            return json.dumps({"status": "success", "message": msg, "mode": "live_stop"})

        else:
            return json.dumps({"status": "error", "message": f"Unknown mode: {mode}"})

    except Exception as e:
        err = f"Translation Tool Failure: {str(e)}"
        if player:
            player.write_log(err, tag="sys")
        return json.dumps({"status": "error", "message": err})
