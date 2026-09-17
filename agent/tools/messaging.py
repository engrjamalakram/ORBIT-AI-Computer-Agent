"""Higher-level helpers for the apps the owner asks about most: WhatsApp and Claude.

These are convenience wrappers around focus + keyboard + screenshot. They are deliberately
'best effort': after driving the UI they hand control back so the agent can screenshot,
read the result, and correct itself (click by coordinate, retry the search, etc.).
"""

import subprocess
import time

from . import tool

_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _pg():
    import pyautogui

    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.05
    return pyautogui


def _run_ps(command, timeout=25):
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, timeout=timeout, creationflags=_FLAGS, errors="replace",
    )


def _focus(title_needle):
    try:
        import pygetwindow as gw
    except Exception:
        return False
    for win in gw.getAllWindows():
        if win.title and title_needle.lower() in win.title.lower():
            try:
                if win.isMinimized:
                    win.restore()
                win.activate()
                time.sleep(0.4)
                return True
            except Exception:
                try:
                    win.minimize(); win.restore(); time.sleep(0.4)
                    return True
                except Exception:
                    return False
    return False


@tool(
    "open_whatsapp",
    "Open (or focus) WhatsApp. mode='desktop' launches the WhatsApp desktop app; mode='web' "
    "opens web.whatsapp.com in the default browser. After this, screenshot to see the state - "
    "if it shows a QR code the owner needs to scan it once from their phone.",
    {"mode": {"type": "string", "enum": ["desktop", "web"], "description": "Default desktop."}},
)
def open_whatsapp(mode="desktop"):
    if mode == "web":
        subprocess.Popen(["cmd", "/c", "start", "", "https://web.whatsapp.com"], creationflags=_FLAGS)
        time.sleep(2.0)
        return {"text": "Opened web.whatsapp.com. Screenshot it - scan the QR from your phone if shown."}

    if _focus("WhatsApp"):
        return {"text": "WhatsApp desktop is already open and now focused. Screenshot to see it."}
    # whatsapp: protocol launches the Store app; fall back to the exe if present.
    _run_ps('Start-Process "whatsapp:"')
    time.sleep(3.0)
    if not _focus("WhatsApp"):
        return {"text": "Tried to launch WhatsApp desktop. If nothing opened it may not be installed - "
                        "use mode='web' instead. Screenshot to check."}
    return {"text": "Launched and focused WhatsApp desktop. Screenshot to see it."}


@tool(
    "whatsapp_send",
    "Send a WhatsApp message to a contact by name, using the WhatsApp DESKTOP app. It focuses "
    "WhatsApp, searches the contact, opens the top match and sends the text. ALWAYS screenshot "
    "afterwards to confirm it went to the right person and actually sent - if the wrong chat "
    "opened, correct it by clicking the right result.",
    {
        "contact": {"type": "string", "description": "Contact or group name as it appears in WhatsApp."},
        "message": {"type": "string", "description": "The message text to send."},
    },
    required=["contact", "message"],
)
def whatsapp_send(contact, message):
    if not _focus("WhatsApp"):
        return {"text": "WhatsApp desktop isn't open. Call open_whatsapp first (or use the browser tools for web)."}

    pg = _pg()
    # Ctrl+N opens the new-chat search box in WhatsApp desktop.
    pg.hotkey("ctrl", "n")
    time.sleep(1.0)
    pg.write(str(contact), interval=0.03)
    time.sleep(1.6)          # let the contact list filter
    pg.press("enter")        # open the top result
    time.sleep(1.0)
    pg.write(str(message), interval=0.01)
    time.sleep(0.3)
    pg.press("enter")        # send
    time.sleep(0.6)
    return {
        "text": f"Attempted to send to '{contact}'. Take a screenshot now to CONFIRM the message "
                f"appears in the right chat. If the wrong chat opened, nothing important was sent - "
                f"search again and click the correct contact.",
    }


@tool(
    "whatsapp_open_chat",
    "Open a specific WhatsApp chat by contact name without sending anything - so you can read "
    "the recent messages. Screenshot afterwards to read the conversation.",
    {"contact": {"type": "string", "description": "Contact or group name."}},
    required=["contact"],
)
def whatsapp_open_chat(contact):
    if not _focus("WhatsApp"):
        return {"text": "WhatsApp desktop isn't open. Call open_whatsapp first."}
    pg = _pg()
    pg.hotkey("ctrl", "n")
    time.sleep(1.0)
    pg.write(str(contact), interval=0.03)
    time.sleep(1.6)
    pg.press("enter")
    time.sleep(0.9)
    return {"text": f"Opened the chat matching '{contact}'. Screenshot to read the messages."}


@tool(
    "open_claude",
    "Open Claude so you can work in the owner's Claude chats. mode='web' opens claude.ai in the "
    "browser (their logged-in session); mode='desktop' launches the Claude desktop app if "
    "installed. Screenshot afterwards to see the chat list.",
    {"mode": {"type": "string", "enum": ["web", "desktop"], "description": "Default web."}},
)
def open_claude(mode="web"):
    if mode == "desktop":
        if _focus("Claude"):
            return {"text": "Claude desktop focused. Screenshot to see it."}
        _run_ps('Start-Process "claude:"')
        time.sleep(2.5)
        if _focus("Claude"):
            return {"text": "Launched Claude desktop. Screenshot to see it."}
        return {"text": "Couldn't open Claude desktop (may not be installed). Try mode='web'."}

    subprocess.Popen(["cmd", "/c", "start", "", "https://claude.ai"], creationflags=_FLAGS)
    time.sleep(2.5)
    return {"text": "Opened claude.ai in the browser. Screenshot it. To find a specific chat, use "
                    "the search in the sidebar - focus the window, then type the chat name."}
