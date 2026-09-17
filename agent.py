import json
import queue
import subprocess
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client       = OpenAI()
SCRIPT_DIR   = Path(__file__).parent
AGENT_NAME   = "TomasAgent"

task_queue      = queue.Queue()
_approval_queue = queue.Queue()
_waiting_approval = False

# ── Tool definitions ──────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Execute a PowerShell command and return stdout + stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "PowerShell command to run."}
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write UTF-8 text to a file. Use this instead of PowerShell for creating code files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string", "description": "File path (absolute or relative)."},
                    "content": {"type": "string", "description": "Full text content to write."},
                },
                "required": ["path", "content"],
            },
        },
    },
]

# ── Tool implementations ──────────────────────────────────────────────

def run_bash(command: str) -> str:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=30,
            cwd=str(SCRIPT_DIR), stdin=subprocess.DEVNULL,
        )
        output = result.stdout + result.stderr
        return output[:4000] if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds."
    except Exception as e:
        return f"Error: {e}"


def write_file(path: str, content: str) -> str:
    try:
        target = Path(path) if Path(path).is_absolute() else SCRIPT_DIR / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"File written: {target}"
    except Exception as e:
        return f"Error: {e}"


# ── Output helper ─────────────────────────────────────────────────────

def p(text="", end="\n"):
    print(text, end=end, flush=True)

# ── Background threads ────────────────────────────────────────────────

def _input_thread():
    """Reads lines from stdin — routes to approval queue or task queue."""
    global _waiting_approval
    for line in sys.stdin:
        text = line.strip()
        if not text:
            continue
        if _waiting_approval:
            _approval_queue.put(text)
        else:
            task_queue.put(text)


def _ask_approval(prompt: str) -> bool:
    """Thread-safe y/n prompt that doesn't leak into the task queue."""
    global _waiting_approval
    p(prompt, end="")
    _waiting_approval = True
    answer = _approval_queue.get()
    _waiting_approval = False
    return answer.lower() == "y"


# ── Agent loop ────────────────────────────────────────────────────────

def _run_agent(task: str):
    """Runs the ReAct agent loop for one task."""
    messages = [
        {
            "role": "system",
            "content": (
                f"You are {AGENT_NAME}, a helpful AI assistant running on Windows PowerShell.\n"
                f"Working directory: {SCRIPT_DIR}\n"
                "User projects are under C:\\Users\\tomas\\Desktop\\Mina Projekt\\\n"
                "Always quote paths with spaces in PowerShell commands.\n"
                "IMPORTANT: Fully complete the task using tools before giving a final answer."
            ),
        },
        {"role": "user", "content": task},
    ]

    for _ in range(10):
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        if msg.content:
            p(f"[Agent] {msg.content}\n")

        if not msg.tool_calls:
            break

        messages.append({
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

            if name == "write_file":
                p(f"[Tool] write_file: {args['path']}")
                p(f"--- preview ---\n{args['content'][:200]}\n---------------")
                approved = _ask_approval("  Approve? (y/n) > ")
                if approved:
                    out = write_file(args["path"], args["content"])
                    p(f"[Output] {out}\n")
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})
                else:
                    p("[Rejected]\n")
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": "Rejected by user."})

            else:
                command = args["command"]
                p(f"[Tool] run_bash: {command}")
                approved = _ask_approval("  Approve? (y/n) > ")
                if approved:
                    out = run_bash(command)
                    p(f"[Output]\n{out}\n")
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})
                else:
                    p("[Rejected]\n")
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": "Command was rejected by the user."})
    else:
        p("[Max 10 iterations reached — stopping.]")

# ── Entry point ───────────────────────────────────────────────────────

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p("=== AI Agent ===")
    p(f"Name : {AGENT_NAME}")
    p("-" * 50)
    p()

    threading.Thread(target=_input_thread, daemon=True).start()

    p("Task > ", end="")

    while True:
        try:
            content = task_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        p()
        p(f"[USER] {content}\n")

        _run_agent(content)

        p()
        p("Task > ", end="")


if __name__ == "__main__":
    main()
