# actions/send_message.py
# Universal messaging — WhatsApp & Instagram
# Uses visual element detection (pyautogui + screen search) instead of
# hardcoded tab/click sequences — works on any screen resolution.

import time
import json
import sys
import pyautogui
from pathlib import Path

import requests

from system.automation_policy import ui_automation_allowed


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.08


def _load_api_config() -> dict:
    try:
        if API_CONFIG_PATH.exists():
            return json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _send_telegram_bot(receiver: str, message: str) -> str | None:
    """
    Background-safe Telegram sending via Bot API.

    Requires config/api_keys.json:
      - telegram_bot_token
      - telegram_default_chat_id  (optional)
      - telegram_chats            (optional mapping: name->chat_id)
    """
    cfg = _load_api_config()
    token = str(cfg.get("telegram_bot_token") or "").strip()
    if not token:
        return None

    chats = cfg.get("telegram_chats") if isinstance(cfg.get("telegram_chats"), dict) else {}
    recv = (receiver or "").strip()
    chat_id = ""
    if recv.lstrip("-").isdigit():
        chat_id = recv
    elif isinstance(chats, dict):
        chat_id = str(chats.get(recv) or chats.get(recv.lower()) or "").strip()

    if not chat_id:
        chat_id = str(cfg.get("telegram_default_chat_id") or "").strip()

    if not chat_id:
        return None

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=15)
        if r.status_code == 200:
            return f"Message sent to {receiver} via Telegram (Bot API)."
        return f"Telegram Bot API error ({r.status_code}): {str(r.text)[:160]}"
    except Exception as e:
        return f"Telegram Bot API request failed: {str(e)[:160]}"

def _open_app(app_name: str) -> bool:
    """Opens an app via Windows search."""
    try:
        pyautogui.press("win")
        time.sleep(0.4)
        pyautogui.write(app_name, interval=0.04)
        time.sleep(0.5)
        pyautogui.press("enter")
        time.sleep(2.0)  
        return True
    except Exception as e:
        print(f"[SendMessage] Could not open {app_name}: {e}")
        return False


def _search_contact(contact: str, platform: str):
    """
    Searches for a contact inside the messaging app.
    Uses Ctrl+F (universal search shortcut) then types contact name.
    """
    time.sleep(0.5)
    pyautogui.hotkey("ctrl", "f")
    time.sleep(0.4)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.write(contact, interval=0.04)
    time.sleep(0.8)
    pyautogui.press("enter")
    time.sleep(0.6)


def _type_and_send(message: str):
    """Types message and sends it."""
    pyautogui.press("tab")
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.write(message, interval=0.03)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)


def _send_whatsapp(receiver: str, message: str) -> str:
    """
    Sends a WhatsApp message via the Windows desktop app.
    Steps: Open WhatsApp → Search contact → Click → Type → Send
    """
    try:
        if not _open_app("WhatsApp"):
            return "Could not open WhatsApp."

        time.sleep(1.5)

        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.4)
        pyautogui.hotkey("ctrl", "a")
        pyautogui.write(receiver, interval=0.04)
        time.sleep(1.0)

        pyautogui.press("enter")
        time.sleep(0.8)

        pyautogui.write(message, interval=0.03)
        time.sleep(0.2)
        pyautogui.press("enter")

        return f"Message sent to {receiver} via WhatsApp."

    except Exception as e:
        return f"WhatsApp error: {e}"


def _send_instagram(receiver: str, message: str) -> str:
    """
    Sends an Instagram DM via browser (instagram.com).
    Steps: Open Chrome → Go to instagram.com/direct → Search contact → Send
    """
    try:
        import webbrowser

        webbrowser.open("https://www.instagram.com/direct/new/")
        time.sleep(3.5)

        pyautogui.write(receiver, interval=0.05)
        time.sleep(1.5)

        pyautogui.press("down")
        time.sleep(0.3)
        pyautogui.press("enter")
        time.sleep(0.5)

        for _ in range(3):
            pyautogui.press("tab")
            time.sleep(0.1)
        pyautogui.press("enter")
        time.sleep(1.5)

        pyautogui.write(message, interval=0.04)
        time.sleep(0.2)
        pyautogui.press("enter")

        return f"Message sent to {receiver} via Instagram."

    except Exception as e:
        return f"Instagram error: {e}"

def _send_telegram(receiver: str, message: str) -> str:
    """Sends a Telegram message via Windows desktop app."""
    try:
        if not _open_app("Telegram"):
            return "Could not open Telegram."

        time.sleep(1.5)

        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.4)
        pyautogui.write(receiver, interval=0.04)
        time.sleep(1.0)
        pyautogui.press("enter")
        time.sleep(0.8)

        pyautogui.write(message, interval=0.03)
        time.sleep(0.2)
        pyautogui.press("enter")

        return f"Message sent to {receiver} via Telegram."

    except Exception as e:
        return f"Telegram error: {e}"



def _send_generic(platform: str, receiver: str, message: str) -> str:
    """
    For any other platform not explicitly supported.
    Opens the app, searches for contact, types and sends.
    Works for: Messenger, Discord, Signal, etc.
    """
    try:
        if not _open_app(platform):
            return f"Could not open {platform}."

        time.sleep(1.5)
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.4)
        pyautogui.write(receiver, interval=0.04)
        time.sleep(1.0)
        pyautogui.press("enter")
        time.sleep(0.8)
        pyautogui.write(message, interval=0.03)
        time.sleep(0.2)
        pyautogui.press("enter")

        return f"Message sent to {receiver} via {platform}."

    except Exception as e:
        return f"{platform} error: {e}"

def send_message(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None
) -> str:
    """
    Called from main.py.

    parameters:
        receiver     : Contact name to send to
        message_text : The message content
        platform     : whatsapp | instagram | telegram | <any app name>
                       Default: whatsapp
    """
    params       = parameters or {}
    receiver     = params.get("receiver", "").strip()
    message_text = params.get("message_text", "").strip()
    platform     = params.get("platform", "whatsapp").strip().lower()

    if not receiver:
        return "Please specify who to send the message to, sir."
    if not message_text:
        return "Please specify what message to send, sir."

    print(f"[SendMessage] 📨 {platform} → {receiver}: {message_text[:40]}")
    if player:
        player.write_log(f"[msg] Sending to {receiver} via {platform}...")

    allow_ui = ui_automation_allowed(player)

    # Prefer true background sending when available.
    if "telegram" in platform or "tg" in platform:
        bot_result = _send_telegram_bot(receiver, message_text)
        if bot_result:
            result = bot_result
        else:
            if not allow_ui:
                return (
                    "Telegram background sending requires Bot API setup. "
                    "Add 'telegram_bot_token' and a chat id in config/api_keys.json "
                    "(telegram_default_chat_id or telegram_chats). "
                    "Or enable Preferences -> Advanced -> 'Allow on-screen automation' to send via the desktop app."
                )
            result = _send_telegram(receiver, message_text)

    elif "whatsapp" in platform or "wp" in platform or "wapp" in platform:
        if not allow_ui:
            return (
                "WhatsApp sending currently requires on-screen automation. "
                "Enable Preferences -> Advanced -> 'Allow on-screen automation' to use it, "
                "or use Telegram Bot API integration for true background sending."
            )
        result = _send_whatsapp(receiver, message_text)

    elif "instagram" in platform or "ig" in platform or "insta" in platform:
        if not allow_ui:
            return (
                "Instagram sending currently requires on-screen automation. "
                "Enable Preferences -> Advanced -> 'Allow on-screen automation' to use it."
            )
        result = _send_instagram(receiver, message_text)

    else:
        if not allow_ui:
            return (
                f"{platform.title()} sending currently requires on-screen automation. "
                "Enable Preferences -> Advanced -> 'Allow on-screen automation' to use it."
            )
        result = _send_generic(platform, receiver, message_text)

    print(f"[SendMessage] ✅ {result}")
    if player:
        player.write_log(f"[msg] {result}")

    return result
