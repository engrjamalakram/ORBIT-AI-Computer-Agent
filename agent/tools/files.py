import os
import shutil
from pathlib import Path

from ..config import CONFIG
from . import tool

TEXT_SUFFIXES = {
    ".txt", ".md", ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yml", ".yaml",
    ".html", ".css", ".csv", ".log", ".ini", ".cfg", ".env", ".bat", ".ps1",
    ".sh", ".xml", ".sql", ".toml", ".java", ".c", ".cpp", ".h", ".php", ".rb", ".go",
}
DISCORD_FILE_LIMIT = 9 * 1024 * 1024


def _human(size):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024


@tool(
    "list_dir",
    "List the contents of a folder with sizes and modified times. Use this to explore the "
    "laptop before reading or changing anything.",
    {
        "path": {"type": "string", "description": "Folder path. Use ~ for the user's home folder."},
        "show_hidden": {"type": "boolean", "description": "Include hidden/system entries. Default false."},
    },
    required=["path"],
)
def list_dir(path, show_hidden=False):
    import time

    folder = Path(os.path.expanduser(str(path)))
    if not folder.exists():
        return {"text": f"Not found: {folder}"}
    if not folder.is_dir():
        return {"text": f"Not a folder: {folder}"}

    rows = []
    try:
        entries = sorted(folder.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return {"text": f"Access denied: {folder}"}

    for entry in entries:
        if not show_hidden and entry.name.startswith("."):
            continue
        try:
            stat = entry.stat()
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))
            size = "<DIR>" if entry.is_dir() else _human(stat.st_size)
            rows.append(f"{when}  {size:>9}  {entry.name}")
        except OSError:
            rows.append(f"{'?':>17}  {entry.name}  (unreadable)")

    body = "\n".join(rows) or "(empty folder)"
    return {"text": f"{folder}  -  {len(rows)} items\n\n{body}"[: CONFIG.max_tool_output]}


@tool(
    "read_file",
    "Read a text file from the laptop.",
    {
        "path": {"type": "string", "description": "Full path to the file."},
        "max_chars": {"type": "integer", "description": "Cap on characters returned. Default 6000."},
    },
    required=["path"],
)
def read_file(path, max_chars=None):
    limit = int(max_chars or CONFIG.max_tool_output)
    target = Path(os.path.expanduser(str(path)))
    if not target.exists():
        return {"text": f"Not found: {target}"}
    if target.is_dir():
        return {"text": f"That is a folder, not a file: {target}"}
    if target.stat().st_size > 20 * 1024 * 1024:
        return {"text": f"File is {_human(target.stat().st_size)} - too big to read. Search it instead."}

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return {"text": f"Could not read {target}: {exc}"}

    if len(content) > limit:
        content = content[:limit] + f"\n\n... [truncated, file has {len(content)} characters total]"
    return {"text": f"{target}\n\n{content}"}


@tool(
    "write_file",
    "Create or overwrite a text file on the laptop. This asks the user for confirmation first.",
    {
        "path": {"type": "string", "description": "Full path to write."},
        "content": {"type": "string", "description": "Full text content."},
        "mode": {
            "type": "string",
            "enum": ["overwrite", "append"],
            "description": "overwrite replaces the file, append adds to the end. Default overwrite.",
        },
    },
    required=["path", "content"],
)
def write_file(path, content, mode="overwrite"):
    target = Path(os.path.expanduser(str(path)))
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    try:
        with open(target, "a" if mode == "append" else "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
    except Exception as exc:
        return {"text": f"Write failed: {exc}"}
    verb = "Appended to" if mode == "append" else ("Overwrote" if existed else "Created")
    return {"text": f"{verb} {target} ({len(content)} characters)."}


@tool(
    "delete_path",
    "Delete a file or a whole folder. Permanent - asks the user first.",
    {
        "path": {"type": "string", "description": "File or folder to delete."},
        "recursive": {"type": "boolean", "description": "Required true to delete a non-empty folder."},
    },
    required=["path"],
)
def delete_path(path, recursive=False):
    target = Path(os.path.expanduser(str(path)))
    if not target.exists():
        return {"text": f"Nothing to delete, does not exist: {target}"}
    try:
        if target.is_dir():
            if not recursive and any(target.iterdir()):
                return {"text": f"{target} is not empty. Call again with recursive=true if that is intended."}
            shutil.rmtree(target)
        else:
            target.unlink()
    except Exception as exc:
        return {"text": f"Delete failed: {exc}"}
    return {"text": f"Deleted {target}"}


@tool(
    "search_files",
    "Find files by name pattern, and optionally by the text inside them.",
    {
        "root": {"type": "string", "description": "Folder to search under."},
        "pattern": {"type": "string", "description": "Glob for the filename, e.g. *.pdf or invoice*. Default *"},
        "contains": {"type": "string", "description": "Only return files whose text contains this string."},
        "limit": {"type": "integer", "description": "Max results. Default 60."},
    },
    required=["root"],
)
def search_files(root, pattern="*", contains=None, limit=60):
    base = Path(os.path.expanduser(str(root)))
    if not base.exists():
        return {"text": f"Not found: {base}"}

    limit = int(limit or 60)
    hits = []
    scanned = 0
    for found in base.rglob(pattern or "*"):
        scanned += 1
        if scanned > 200_000:
            break
        if not found.is_file():
            continue
        if contains:
            if found.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                if contains.lower() not in found.read_text(encoding="utf-8", errors="ignore").lower():
                    continue
            except OSError:
                continue
        try:
            hits.append(f"{_human(found.stat().st_size):>9}  {found}")
        except OSError:
            continue
        if len(hits) >= limit:
            break

    if not hits:
        return {"text": f"No matches under {base} for pattern '{pattern}'" + (f" containing '{contains}'" if contains else "")}
    return {"text": f"{len(hits)} match(es):\n\n" + "\n".join(hits)}


@tool(
    "send_file_to_discord",
    "Upload a file from the laptop to Discord so the user can open it on their phone. "
    "Max ~9 MB - zip or split bigger files first.",
    {
        "path": {"type": "string", "description": "Full path of the file to send."},
        "note": {"type": "string", "description": "Optional caption."},
    },
    required=["path"],
)
def send_file_to_discord(path, note=None):
    target = Path(os.path.expanduser(str(path)))
    if not target.exists() or not target.is_file():
        return {"text": f"Not a file: {target}"}
    size = target.stat().st_size
    if size > DISCORD_FILE_LIMIT:
        return {"text": f"{target.name} is {_human(size)}, over the ~9MB Discord limit. Zip or split it first."}
    return {"text": f"Uploading {target.name} ({_human(size)}) to Discord.", "files": [target], "captions": [note or ""]}
