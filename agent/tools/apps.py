import os
import subprocess
import time

from ..config import CONFIG
from . import tool

_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@tool(
    "open_app",
    "Launch a program or open a file/folder with its default app. Accepts a friendly name "
    "(notepad, chrome, excel, calc, explorer), a full .exe path, or a document path.",
    {
        "target": {"type": "string", "description": "App name, exe path, file path or folder path."},
        "args": {"type": "string", "description": "Optional command-line arguments."},
    },
    required=["target"],
)
def open_app(target, args=None):
    target = os.path.expanduser(str(target))
    friendly = {
        "chrome": "chrome",
        "edge": "msedge",
        "firefox": "firefox",
        "notepad": "notepad",
        "calculator": "calc",
        "calc": "calc",
        "explorer": "explorer",
        "files": "explorer",
        "cmd": "cmd",
        "terminal": "wt",
        "powershell": "powershell",
        "word": "winword",
        "excel": "excel",
        "powerpoint": "powerpnt",
        "vscode": "code",
        "code": "code",
        "paint": "mspaint",
        "settings": "ms-settings:",
        "task manager": "taskmgr",
        "taskmgr": "taskmgr",
        "spotify": "spotify",
        "whatsapp": "whatsapp:",
    }
    resolved = friendly.get(target.lower().strip(), target)
    command = f'Start-Process "{resolved}"'
    if args:
        command += f' -ArgumentList "{args}"'
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=30, creationflags=_FLAGS, errors="replace",
        )
    except Exception as exc:
        return {"text": f"Launch failed: {exc}"}
    if proc.returncode != 0:
        return {"text": f"Could not open '{target}'.\n{proc.stderr.strip()[:800]}"}
    time.sleep(1.2)
    return {"text": f"Launched '{resolved}'. Take a screenshot to see the result."}


@tool(
    "open_url",
    "Open a web address in the default browser.",
    {"url": {"type": "string", "description": "Full URL including https://"}},
    required=["url"],
)
def open_url(url):
    try:
        subprocess.Popen(["cmd", "/c", "start", "", url], creationflags=_FLAGS)
    except Exception as exc:
        return {"text": f"Failed to open URL: {exc}"}
    time.sleep(1.5)
    return {"text": f"Opened {url} in the default browser."}


@tool(
    "list_windows",
    "List the open application windows and their titles. Use this before focusing or "
    "closing a window, and to understand what the user is currently working on.",
    {},
)
def list_windows():
    script = (
        "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | "
        "Select-Object Id, ProcessName, MainWindowTitle | Format-Table -AutoSize | Out-String -Width 200"
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=30, creationflags=_FLAGS, errors="replace",
    )
    out = (proc.stdout or "").strip()
    return {"text": out[: CONFIG.max_tool_output] if out else "No windows with titles are open."}


@tool(
    "focus_window",
    "Bring a window to the front by (part of) its title, so keyboard and mouse actions "
    "go to the right app. Always focus before typing into an app.",
    {
        "title_contains": {"type": "string", "description": "Part of the window title, case-insensitive."},
    },
    required=["title_contains"],
)
def focus_window(title_contains):
    try:
        import pygetwindow as gw
    except Exception as exc:
        return {"text": f"pygetwindow unavailable: {exc}"}

    needle = title_contains.lower()
    matches = [w for w in gw.getAllWindows() if w.title and needle in w.title.lower()]
    if not matches:
        return {"text": f"No open window matching '{title_contains}'. Call list_windows to see what is open."}

    win = matches[0]
    try:
        if win.isMinimized:
            win.restore()
        win.activate()
    except Exception:
        # activate() throws on some Windows builds even when it worked
        try:
            win.minimize()
            win.restore()
        except Exception as exc:
            return {"text": f"Found '{win.title}' but could not focus it: {exc}"}
    time.sleep(0.5)
    extra = f" (also matched: {', '.join(w.title for w in matches[1:4])})" if len(matches) > 1 else ""
    return {"text": f"Focused '{win.title}'.{extra}"}


@tool(
    "close_window",
    "Politely close a window by title (sends a close request, so unsaved-changes prompts "
    "still appear). Use kill_process only if this does not work.",
    {"title_contains": {"type": "string", "description": "Part of the window title."}},
    required=["title_contains"],
)
def close_window(title_contains):
    try:
        import pygetwindow as gw
    except Exception as exc:
        return {"text": f"pygetwindow unavailable: {exc}"}

    needle = title_contains.lower()
    closed = []
    for win in gw.getAllWindows():
        if win.title and needle in win.title.lower():
            try:
                win.close()
                closed.append(win.title)
            except Exception:
                continue
    if not closed:
        return {"text": f"No window matching '{title_contains}'."}
    return {"text": "Closed: " + ", ".join(closed)}
