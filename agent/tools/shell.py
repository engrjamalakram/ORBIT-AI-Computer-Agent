import subprocess

from ..config import CONFIG
from . import tool

_FLAGS = 0
try:
    _FLAGS = subprocess.CREATE_NO_WINDOW  # keeps console windows from flashing
except AttributeError:
    pass


def _clip(text, limit):
    text = text or ""
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2 :]
    return f"{head}\n\n... [{len(text) - limit} characters cut] ...\n\n{tail}"


@tool(
    "run_powershell",
    "Run a PowerShell command on the laptop and get stdout/stderr back. This is the "
    "general-purpose escape hatch - use it for anything the other tools do not cover "
    "(installing software, winget, git, network checks, WMI, scheduled tasks, etc). "
    "Runs non-interactively, so never use commands that wait for input (Read-Host, "
    "pause, git rebase -i). Windows PowerShell 5.1: no && or || chaining, no ternary.",
    {
        "command": {"type": "string", "description": "PowerShell command or script to run."},
        "working_dir": {"type": "string", "description": "Optional folder to run it in."},
        "timeout": {"type": "integer", "description": "Seconds before it is killed. Default 180."},
    },
    required=["command"],
)
def run_powershell(command, working_dir=None, timeout=None):
    timeout = int(timeout or CONFIG.shell_timeout)
    try:
        proc = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=working_dir or None,
            creationflags=_FLAGS,
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"text": f"TIMEOUT: command still running after {timeout}s and was killed."}
    except Exception as exc:
        return {"text": f"FAILED to launch PowerShell: {exc}"}

    parts = [f"exit code: {proc.returncode}"]
    if proc.stdout.strip():
        parts.append("--- stdout ---\n" + proc.stdout.strip())
    if proc.stderr.strip():
        parts.append("--- stderr ---\n" + proc.stderr.strip())
    if not proc.stdout.strip() and not proc.stderr.strip():
        parts.append("(no output)")
    return {"text": _clip("\n".join(parts), CONFIG.max_tool_output)}
