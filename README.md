# AI Agent

A local AI agent with a web-based interface that can run PowerShell commands, search the web, read/write files, take screenshots, and make HTTP requests — all from a clean glassmorphism UI in your browser.

## Features

- **Chat interface** — Glassmorphism UI served via Flask in the browser
- **Tools** — PowerShell, web search (DuckDuckGo), file read/write, HTTP requests, desktop screenshot analysis, rendered website screenshots (Playwright)
- **Persistent memory** — The agent remembers information between sessions (stored locally in JSON)
- **Terminal mode** — Run `agent.py` directly in the terminal with per-tool approval flow

## Requirements

- Python 3.10+
- An OpenAI account with an API key and credits

## Setup

1. Clone the repo and create a virtual environment:

   ```
   python -m venv venv
   .\venv\Scripts\activate
   ```

2. Install dependencies:

   ```
   pip install -r requirements.txt
   playwright install chromium
   ```

3. Copy `.env.example` to `.env` and fill in your values:

   ```
   copy .env.example .env
   ```

   Open `.env` and add your OpenAI API key.

## Running the web interface

```
.\venv\Scripts\activate
python app.py
```

Then open **http://localhost:5733** in your browser.

## Running the terminal agent

```
.\venv\Scripts\activate
python agent.py
```

The agent will ask for your approval before running any PowerShell command or writing files.

## Running the tests

```
.\venv\Scripts\activate
pip install -r requirements-dev.txt
pytest
```

## Architecture

There are two independent entry points, sharing the same OpenAI function-calling pattern but with different security models:

- **`app.py`** — Flask web UI. Tools run automatically, gated by a regex blocklist (`BLOCKED_PATTERNS`/`BLOCKED_WRITE_PATHS`) that rejects obviously dangerous commands/paths before execution.
- **`agent.py`** — Terminal agent. No blocklist; instead every `run_bash`/`write_file` call requires explicit `y/n` approval from the person at the keyboard.

`app.py` can also spawn `agent.py` as a subprocess and stream its stdin/stdout over Server-Sent Events, powering the "Terminal" tab in the web UI.

## Files

| File                      | Description                                                   |
| ------------------------- | ------------------------------------------------------------- |
| `app.py`                  | Flask server with web UI and all tools                        |
| `agent.py`                | Terminal agent with approval flow                              |
| `tray.py`                 | System tray icon for quick launch                             |
| `templates/index.html`    | Web UI (HTML/JS)                                              |
| `tests/`                  | pytest tests for the security blocklist and memory store      |
| `.env`                    | Your secret config (never committed, listed in .gitignore)    |
| `.env.example`            | Template for the `.env` file                                  |

## Security notes

- Never share your `.env` file or API key
- Every API call costs money via your OpenAI account
- The web interface (`app.py`) is intended for local use — do not expose it to the internet
