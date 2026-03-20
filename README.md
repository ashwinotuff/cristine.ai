# CRISTINE (Windows)

Cristine is a Windows-first desktop assistant built in Python with a HUD UI, voice mode, and automation tools (browser, files, terminal, desktop controls).

## Requirements

- Windows 10/11
- Python 3.10+
- Gemini API key

## Install

```bash
python setup.py
```

## Configure API key

Cristine reads the key in this order:

1) `GEMINI_API_KEY` environment variable (recommended)
2) `config/api_keys.json` (`{"gemini_api_key": "..."}`)
3) UI setup prompt (writes `config/api_keys.json`)

Template: `config/api_keys.example.json`

## Run

```bash
python main.py
```

## Safety note

Some tools can control mouse/keyboard or run commands. Keep on-screen automation disabled unless you’re supervising (`automation_allow_ui` in `config/preferences.json`).
