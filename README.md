# AI Agent

A local AI agent with a web-based interface that can run PowerShell commands, search the web, read/write files, take screenshots, and make HTTP requests — all from a clean glassmorphism UI in your browser.

## Features

- **Chat interface** — Glassmorphism UI served via Flask in the browser
- **Tools** — PowerShell, web search (DuckDuckGo), file read/write, HTTP requests, screenshot analysis
- **Persistent memory** — The agent remembers information between sessions (stored locally in JSON)
- **Terminal mode** — Run `agent.py` directly in the terminal with per-tool approval flow
- **Multi-agent hub** — Optional: connect to a shared chat hub and communicate with other agents

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

Then open **http://localhost:5000** in your browser.

## Running the terminal agent

```
.\venv\Scripts\activate
python agent.py
```

The agent will ask for your approval before running any PowerShell command or writing files.

## Files

| File                      | Description                                                   |
| ------------------------- | ------------------------------------------------------------- |
| `app.py`                  | Flask server with web UI and all tools                        |
| `agent.py`                | Terminal agent with approval flow and optional hub support    |
| `calculator_functions.py` | Helper functions for arithmetic operations                    |
| `tray.py`                 | System tray icon for quick launch                             |
| `templates/index.html`    | Web UI (HTML/JS)                                              |
| `.env`                    | Your secret config (never committed, listed in .gitignore)    |
| `.env.example`            | Template for the `.env` file                                  |

## Security notes

- Never share your `.env` file or API key
- Every API call costs money via your OpenAI account
- The web interface (`app.py`) is intended for local use — do not expose it to the internet
