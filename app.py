from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, Response
from openai import OpenAI
from pathlib import Path
from PIL import ImageGrab
import subprocess
import json
import httpx
import io
import base64
import re
import datetime
import threading
import queue
import uuid
import os

load_dotenv()

app = Flask(__name__)
client = OpenAI()

BASE_DIR     = Path(__file__).parent
MEMORY_FILE  = BASE_DIR / "agent_memory.json"
COMMAND_LOG  = BASE_DIR / "command_log.txt"

SYSTEM_PROMPT = (
    "Du är en personlig AI-assistent som körs lokalt på användarens Windows-dator. "
    "Du har tillgång till verktyg: PowerShell-kommandon, webbsökning, filhantering, "
    "HTTP-anrop, persistent minne och skärmdumpsanalys.\n\n"
    "SÄKERHETSREGLER som du ALLTID måste följa:\n"
    "1. Radera ALDRIG filer utan att användaren uttryckligen bett om det och bekräftat.\n"
    "2. Modifiera ALDRIG Windows-systemfiler, registret, boot-konfiguration eller säkerhetsinställningar.\n"
    "3. Starta ALDRIG om eller stäng ALDRIG av datorn.\n"
    "4. Skapa ALDRIG nya användarkonton eller ändra lösenord.\n"
    "5. Skicka ALDRIG känslig information (lösenord, API-nycklar, personuppgifter) via HTTP.\n"
    "6. Arbeta ALLTID i användarens egna mappar (Desktop, Documents, Downloads, projekt).\n"
    "Om en begäran kräver en farlig åtgärd, neka och förklara varför."
)

TOOL_META = {
    "run_bash":        {"icon": "💻", "label": "PowerShell"},
    "web_search":      {"icon": "🔍", "label": "Webbsökning"},
    "read_file":       {"icon": "📄", "label": "Läser fil"},
    "write_file":      {"icon": "💾", "label": "Skriver fil"},
    "save_memory":     {"icon": "🧠", "label": "Sparar minne"},
    "read_memory":     {"icon": "🧠", "label": "Läser minne"},
    "http_request":    {"icon": "🌐", "label": "HTTP"},
    "take_screenshot": {"icon": "📷", "label": "Skärmdump"},
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Kör ett PowerShell-kommando på Windows-datorn och returnera output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "PowerShell-kommandot att köra"}
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Sök på internet via DuckDuckGo. Returnerar titlar, URL:er och sammanfattningar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Sökfrågan"},
                    "max_results": {"type": "integer", "description": "Max antal resultat (standard 5)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Läs innehållet i en fil på disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolut sökväg till filen"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Skriv text till en fil (skapar om den inte finns, skriver över annars).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolut sökväg till filen"},
                    "content": {"type": "string", "description": "Innehållet att skriva"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Spara en nyckel-värde-post i persistent minne (finns kvar mellan sessioner).",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Nyckelnamn"},
                    "value": {"type": "string", "description": "Värdet att spara"},
                },
                "required": ["key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": "Läs från persistent minne. Använd '_all' för att se allt sparat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Nyckelnamn, eller '_all' för allt"}
                },
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "http_request",
            "description": "Gör ett HTTP-anrop till en URL och returnera svaret.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL:en att anropa"},
                    "method": {"type": "string", "description": "HTTP-metod: GET, POST, PUT, DELETE"},
                    "headers": {"type": "object", "description": "HTTP-headers som key-value"},
                    "body": {"type": "string", "description": "Request body för POST/PUT"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Ta en skärmdump av hela skärmen och analysera vad som visas.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

conversation_history = []


# ── Security ──────────────────────────────────────────────────────────

# Patterns that are always blocked regardless of what the AI asks
BLOCKED_PATTERNS = [
    r"Format-Volume", r"Format-Disk", r"format\s+[a-zA-Z]:",
    r"Remove-Item.{0,60}(-Recurse|-rf).{0,60}(C:\\Windows|C:\\Program|System32|SysWOW)",
    r"rm\s+-[rf]", r"del\s+/[sfq]",
    r"bcdedit", r"bootrec",
    r"Stop-Computer", r"Restart-Computer",
    r"Disable-WindowsOptionalFeature",
    r"reg\s+(delete|add).{0,30}HKLM\\(SYSTEM|SOFTWARE\\Microsoft\\Windows NT)",
    r"net\s+user\s+\w+\s+.+",         # creating/changing users
    r"Set-ExecutionPolicy\s+Unrestricted",
    r"Invoke-Expression.*http",        # downloading and running remote code
    r"iex\s*\(",
    r"DownloadString.*http.*Invoke",
]

BLOCKED_WRITE_PATHS = [
    r"C:\\Windows",
    r"C:\\Program Files",
    r"C:\\ProgramData\\Microsoft",
    r"C:\\System Volume Information",
]

_BLOCKED_RE   = [re.compile(p, re.IGNORECASE) for p in BLOCKED_PATTERNS]
_BLOCKED_PATH = [re.compile(p, re.IGNORECASE) for p in BLOCKED_WRITE_PATHS]


def _is_blocked_command(command: str) -> str | None:
    for pattern in _BLOCKED_RE:
        if pattern.search(command):
            return f"Blockerat av säkerhetsskäl: matchar förbjudet mönster ({pattern.pattern[:40]})"
    return None


def _is_blocked_path(path: str) -> str | None:
    for pattern in _BLOCKED_PATH:
        if pattern.match(path):
            return f"Skrivning till systemkatalog är blockerad: {path}"
    return None


def _log_command(tool: str, detail: str) -> None:
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(COMMAND_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {tool}: {detail}\n")
    except Exception:
        pass


# ── Tool implementations ──────────────────────────────────────────────

def run_bash(command: str) -> str:
    blocked = _is_blocked_command(command)
    if blocked:
        _log_command("BLOCKED run_bash", command)
        return f"⛔ {blocked}"
    _log_command("run_bash", command)
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=30,
        )
        out = result.stdout.strip()
        if result.stderr.strip():
            out += f"\nSTDERR:\n{result.stderr.strip()}"
        return out or "(inget output)"
    except subprocess.TimeoutExpired:
        return "Kommandot avbröts — tog längre än 30 sekunder."
    except Exception as e:
        return f"Fel: {e}"


def web_search(query: str, max_results: int = 5) -> str:
    _log_command("web_search", query)
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "Inga resultat."
        parts = []
        for r in results:
            parts.append(f"{r['title']}\n{r['href']}\n{r.get('body', '')}")
        return "\n\n---\n\n".join(parts)
    except Exception as e:
        return f"Sökning misslyckades: {e}"


def read_file(path: str) -> str:
    try:
        p = Path(path)
        if not p.exists():
            return f"Finns inte: {path}"
        if p.stat().st_size > 500_000:
            return f"Filen är för stor ({p.stat().st_size // 1024} KB). Använd PowerShell för att läsa delar."
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Fel: {e}"


def write_file(path: str, content: str) -> str:
    blocked = _is_blocked_path(path)
    if blocked:
        _log_command("BLOCKED write_file", path)
        return f"⛔ {blocked}"
    _log_command("write_file", path)
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Sparad: {path}"
    except Exception as e:
        return f"Fel: {e}"


def load_memory() -> dict:
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    return {}


def save_memory_entry(key: str, value: str) -> str:
    mem = load_memory()
    mem[key] = value
    MEMORY_FILE.write_text(json.dumps(mem, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"Sparat: {key}"


def get_memory_entry(key: str) -> str:
    mem = load_memory()
    if key == "_all":
        return "\n".join(f"{k}: {v}" for k, v in mem.items()) if mem else "Minnet är tomt."
    return f"{key}: {mem[key]}" if key in mem else f"Inget sparat för '{key}'."


def do_http_request(url: str, method: str = "GET", headers: dict = None, body: str = None) -> str:
    _log_command("http_request", f"{method} {url}")
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as c:
            resp = c.request(method.upper(), url, headers=headers or {}, content=body)
        return f"Status: {resp.status_code}\n\n{resp.text[:3000]}"
    except Exception as e:
        return f"Fel: {e}"


def capture_screenshot() -> str:
    img = ImageGrab.grab()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def build_system_prompt() -> str:
    prompt = SYSTEM_PROMPT
    mem = load_memory()
    if mem:
        lines = "\n".join(f"- {k}: {v}" for k, v in mem.items())
        prompt += f"\n\nDitt sparade minne från tidigare sessioner:\n{lines}"
    return prompt


def dispatch(name: str, args: dict):
    """Returns (output_str, is_screenshot, b64_or_none)"""
    if name == "run_bash":
        return run_bash(args["command"]), False, None
    if name == "web_search":
        return web_search(args["query"], args.get("max_results", 5)), False, None
    if name == "read_file":
        return read_file(args["path"]), False, None
    if name == "write_file":
        return write_file(args["path"], args["content"]), False, None
    if name == "save_memory":
        return save_memory_entry(args["key"], args["value"]), False, None
    if name == "read_memory":
        return get_memory_entry(args["key"]), False, None
    if name == "http_request":
        return do_http_request(
            args["url"], args.get("method", "GET"),
            args.get("headers"), args.get("body")
        ), False, None
    if name == "take_screenshot":
        b64 = capture_screenshot()
        return "Skärmdump tagen och analyserad.", True, b64
    return "Okänt verktyg.", False, None


# ── Routes ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/ask", methods=["POST"])
def ask():
    global conversation_history
    question = request.json.get("question", "")
    conversation_history.append({"role": "user", "content": question})

    actions = []

    while True:
        messages = [{"role": "system", "content": build_system_prompt()}] + conversation_history

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        if msg.tool_calls:
            conversation_history.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments)
                meta = TOOL_META.get(name, {"icon": "🔧", "label": name})

                output, is_screenshot, b64 = dispatch(name, args)

                detail = (
                    args.get("command") or args.get("query") or
                    args.get("path") or args.get("url") or
                    args.get("key") or "skärmdump"
                )
                actions.append({
                    "tool": name,
                    "icon": meta["icon"],
                    "label": meta["label"],
                    "detail": detail,
                    "output": output,
                    "is_screenshot": is_screenshot,
                })

                if is_screenshot:
                    conversation_history.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": [
                            {"type": "text", "text": "Skärmdump tagen."},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                        ],
                    })
                else:
                    conversation_history.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": output,
                    })
        else:
            answer = msg.content
            conversation_history.append({"role": "assistant", "content": answer})
            return jsonify({"answer": answer, "actions": actions})


@app.route("/reset", methods=["POST"])
def reset():
    global conversation_history
    conversation_history = []
    return jsonify({"ok": True})


# ── Terminal (agent.py runner) ────────────────────────────────────────

_terminals = {}  # sid -> {'proc': Popen, 'q': Queue}


def _spawn_agent(sid: str) -> None:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [str(BASE_DIR / "venv" / "Scripts" / "python.exe"), "-u", str(BASE_DIR / "agent.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(BASE_DIR),
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    q = queue.Queue()
    _terminals[sid] = {"proc": proc, "q": q}

    def _reader():
        try:
            while True:
                ch = proc.stdout.read(1)
                if not ch:
                    break
                q.put(ch)
        finally:
            q.put(None)

    threading.Thread(target=_reader, daemon=True).start()


@app.route("/terminal/start", methods=["POST"])
def terminal_start():
    sid = str(uuid.uuid4())
    _spawn_agent(sid)
    return jsonify({"sid": sid, "cwd": str(BASE_DIR)})


@app.route("/terminal/stream")
def terminal_stream():
    sid = request.args.get("sid", "")
    if sid not in _terminals:
        return jsonify({"error": "Session not found"}), 404

    q = _terminals[sid]["q"]

    def generate():
        buf = ""
        while True:
            try:
                ch = q.get(timeout=0.05)
                if ch is None:
                    if buf:
                        yield f"data: {json.dumps({'text': buf})}\n\n"
                    yield f"data: {json.dumps({'done': True})}\n\n"
                    return
                buf += ch
                if len(buf) >= 32 or "\n" in buf:
                    yield f"data: {json.dumps({'text': buf})}\n\n"
                    buf = ""
            except queue.Empty:
                if buf:
                    yield f"data: {json.dumps({'text': buf})}\n\n"
                    buf = ""
                else:
                    yield ": keepalive\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/terminal/input", methods=["POST"])
def terminal_input():
    data = request.json
    sid = data.get("sid", "")
    text = data.get("text", "")
    if sid not in _terminals:
        return jsonify({"error": "Session not found"}), 404
    try:
        _terminals[sid]["proc"].stdin.write(text + "\n")
        _terminals[sid]["proc"].stdin.flush()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True})


@app.route("/terminal/stop", methods=["POST"])
def terminal_stop():
    sid = request.json.get("sid", "")
    if sid in _terminals:
        try:
            _terminals[sid]["proc"].terminate()
        except Exception:
            pass
        del _terminals[sid]
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True)
