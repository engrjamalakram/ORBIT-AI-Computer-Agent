import time
from pathlib import Path

from ..config import CONFIG
from . import tool

MAX_EDGE = 1568  # Anthropic's sweet spot for vision input


def _save(pil_image, prefix="shot"):
    from PIL import Image

    img = pil_image
    if max(img.size) > MAX_EDGE:
        scale = MAX_EDGE / max(img.size)
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    if img.mode != "RGB":
        img = img.convert("RGB")

    path = CONFIG.shots_dir / f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000}.jpg"
    img.save(path, "JPEG", quality=78, optimize=True)
    _prune()
    return path


def _prune(keep=60):
    shots = sorted(CONFIG.shots_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in shots[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


@tool(
    "screenshot",
    "Look at the laptop screen. The image comes back to YOU so you can read what is on "
    "screen and decide the next step. By default it is NOT sent to the user - use it freely "
    "while working. Only set show=true when the user actually asked to see the screen, or "
    "when you are finished and showing the final result. Do not send the user a picture of "
    "every intermediate step.",
    {
        "monitor": {
            "type": "integer",
            "description": "0 = all monitors stitched together (default), 1 = primary, 2 = second, etc.",
        },
        "region": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Optional [left, top, width, height] crop in screen pixels.",
        },
        "show": {
            "type": "boolean",
            "description": "true = also send this image to the user in Discord. Default false.",
        },
        "note": {"type": "string", "description": "Short caption, only used when show=true."},
    },
)
def screenshot(monitor=0, region=None, note=None, show=False):
    import mss
    from PIL import Image

    with mss.mss() as sct:
        if region and len(region) == 4:
            box = {"left": region[0], "top": region[1], "width": region[2], "height": region[3]}
        else:
            index = int(monitor or 0)
            if index >= len(sct.monitors):
                return {"text": f"No monitor {index}. Available: 0..{len(sct.monitors) - 1}"}
            box = sct.monitors[index]
        raw = sct.grab(box)

    img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    path = _save(img)
    return {
        "text": f"Screen captured ({raw.size[0]}x{raw.size[1]}). Look at the image below."
                + ("" if show else " (not sent to the user)"),
        "images": [path],
        "captions": [note or ""],
        "show": bool(show),
    }


@tool(
    "list_monitors",
    "List the connected monitors and their pixel geometry. Useful before taking a "
    "screenshot of a specific screen or before clicking at coordinates.",
    {},
)
def list_monitors():
    import mss

    with mss.mss() as sct:
        lines = []
        for i, mon in enumerate(sct.monitors):
            label = "all screens combined" if i == 0 else f"monitor {i}"
            lines.append(
                f"{i}: {label} - {mon['width']}x{mon['height']} at ({mon['left']}, {mon['top']})"
            )
    return {"text": "\n".join(lines)}


@tool(
    "send_screenshot_file",
    "Send an existing image file from the laptop to the user in Discord.",
    {"path": {"type": "string", "description": "Full path to the image."}},
    required=["path"],
)
def send_screenshot_file(path):
    p = Path(path)
    if not p.exists():
        return {"text": f"No such file: {p}"}
    return {"text": f"Sent {p.name} to Discord.", "files": [p]}
