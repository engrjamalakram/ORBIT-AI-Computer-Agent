"""Mouse and keyboard control - the agent literally drives the laptop."""

import time

from . import tool


def _pyautogui():
    import pyautogui

    pyautogui.FAILSAFE = False  # the laptop is unattended; a corner-mouse abort is useless remotely
    pyautogui.PAUSE = 0.02      # was 0.05 - adds up badly over hundreds of actions
    return pyautogui


@tool(
    "type_text",
    "Put text into whatever window currently has focus. Long text is pasted instantly via the "
    "clipboard instead of typed letter by letter, so use this for whole prompts and paragraphs "
    "- it takes the same time whether it is 10 characters or 5000. Focus the right window first.",
    {
        "text": {"type": "string", "description": "The text to enter."},
        "press_enter": {"type": "boolean", "description": "Press Enter afterwards. Default false."},
        "force_typing": {
            "type": "boolean",
            "description": "Type character by character instead of pasting. Only for fields that "
                           "reject paste. Slow - avoid unless needed.",
        },
    },
    required=["text"],
)
def type_text(text, press_enter=False, force_typing=False, interval=0.01):
    try:
        pyautogui = _pyautogui()
    except Exception as exc:
        return {"text": f"pyautogui unavailable: {exc}"}

    body = str(text)

    # Typing a 3000-character prompt at 10ms/char is 30 seconds. Pasting is instant.
    if not force_typing and len(body) > 120:
        try:
            import pyperclip

            saved = ""
            try:
                saved = pyperclip.paste() or ""
            except Exception:  # noqa: BLE001
                pass

            pyperclip.copy(body)
            time.sleep(0.15)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.25)
            if press_enter:
                pyautogui.press("enter")
            if saved:                      # put the owner's clipboard back
                try:
                    time.sleep(0.1)
                    pyperclip.copy(saved)
                except Exception:  # noqa: BLE001
                    pass
            return {"text": f"Pasted {len(body)} characters"
                            + (" and pressed Enter." if press_enter else ".")}
        except Exception as exc:  # noqa: BLE001 - fall back to typing
            print(f"[input] paste failed ({exc}), typing instead")

    pyautogui.write(body, interval=float(interval or 0.01))
    if press_enter:
        pyautogui.press("enter")
    return {"text": f"Typed {len(body)} characters" + (" and pressed Enter." if press_enter else ".")}


@tool(
    "press_keys",
    "Press a key or a keyboard shortcut. Examples: 'enter', 'esc', 'f5', 'ctrl+s', "
    "'ctrl+shift+esc', 'win+d', 'alt+tab', 'win+l'. Combine with + for chords.",
    {
        "keys": {"type": "string", "description": "Key or chord, e.g. ctrl+s"},
        "repeat": {"type": "integer", "description": "How many times. Default 1."},
    },
    required=["keys"],
)
def press_keys(keys, repeat=1):
    try:
        pyautogui = _pyautogui()
    except Exception as exc:
        return {"text": f"pyautogui unavailable: {exc}"}

    combo = [part.strip().lower() for part in str(keys).replace(" ", "").split("+") if part.strip()]
    if not combo:
        return {"text": "No keys given."}
    times = max(1, min(int(repeat or 1), 100))
    for _ in range(times):
        if len(combo) == 1:
            pyautogui.press(combo[0])
        else:
            pyautogui.hotkey(*combo)
        time.sleep(0.06)
    return {"text": f"Pressed {'+'.join(combo)} x{times}."}


@tool(
    "click",
    "Click the mouse at an exact screen coordinate. Take a screenshot first and read the "
    "pixel position off it - coordinates are in real screen pixels, and the screenshot you "
    "were shown may have been scaled down, so use list_monitors to check the true resolution.",
    {
        "x": {"type": "integer", "description": "X in screen pixels."},
        "y": {"type": "integer", "description": "Y in screen pixels."},
        "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "Default left."},
        "clicks": {"type": "integer", "description": "1 for single, 2 for double. Default 1."},
    },
    required=["x", "y"],
)
def click(x, y, button="left", clicks=1):
    try:
        pyautogui = _pyautogui()
    except Exception as exc:
        return {"text": f"pyautogui unavailable: {exc}"}

    pyautogui.click(x=int(x), y=int(y), button=button or "left", clicks=int(clicks or 1), interval=0.1)
    return {"text": f"{button or 'left'}-clicked {clicks or 1}x at ({x}, {y}). Screenshot to confirm."}


@tool(
    "move_mouse",
    "Move the mouse pointer without clicking - useful for hovering to reveal menus or tooltips.",
    {
        "x": {"type": "integer"},
        "y": {"type": "integer"},
        "duration": {"type": "number", "description": "Seconds for the movement. Default 0.2."},
    },
    required=["x", "y"],
)
def move_mouse(x, y, duration=0.2):
    try:
        pyautogui = _pyautogui()
    except Exception as exc:
        return {"text": f"pyautogui unavailable: {exc}"}

    pyautogui.moveTo(int(x), int(y), duration=float(duration or 0.2))
    return {"text": f"Mouse moved to ({x}, {y})."}


@tool(
    "scroll",
    "Scroll the mouse wheel. Positive amount scrolls up, negative scrolls down.",
    {
        "amount": {"type": "integer", "description": "Wheel clicks, e.g. -5 to scroll down."},
        "x": {"type": "integer", "description": "Optional: move here before scrolling."},
        "y": {"type": "integer", "description": "Optional: move here before scrolling."},
    },
    required=["amount"],
)
def scroll(amount, x=None, y=None):
    try:
        pyautogui = _pyautogui()
    except Exception as exc:
        return {"text": f"pyautogui unavailable: {exc}"}

    if x is not None and y is not None:
        pyautogui.moveTo(int(x), int(y))
    pyautogui.scroll(int(amount) * 120)
    return {"text": f"Scrolled {amount} clicks."}


@tool(
    "drag",
    "Drag the mouse from one point to another with the button held down.",
    {
        "from_x": {"type": "integer"},
        "from_y": {"type": "integer"},
        "to_x": {"type": "integer"},
        "to_y": {"type": "integer"},
        "duration": {"type": "number", "description": "Seconds. Default 0.5."},
    },
    required=["from_x", "from_y", "to_x", "to_y"],
)
def drag(from_x, from_y, to_x, to_y, duration=0.5):
    try:
        pyautogui = _pyautogui()
    except Exception as exc:
        return {"text": f"pyautogui unavailable: {exc}"}

    pyautogui.moveTo(int(from_x), int(from_y))
    pyautogui.dragTo(int(to_x), int(to_y), duration=float(duration or 0.5), button="left")
    return {"text": f"Dragged ({from_x}, {from_y}) -> ({to_x}, {to_y})."}


@tool(
    "wait",
    "Pause before the next action - for example while an app loads or a download finishes.",
    {"seconds": {"type": "number", "description": "How long to wait. Max 120."}},
    required=["seconds"],
)
def wait(seconds):
    duration = max(0.0, min(float(seconds), 120.0))
    time.sleep(duration)
    return {"text": f"Waited {duration:g}s."}
