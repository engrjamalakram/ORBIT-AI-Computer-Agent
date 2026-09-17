import os
import subprocess
import time

from ..config import CONFIG
from . import tool

_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _gb(value):
    return f"{value / (1024 ** 3):.1f} GB"


@tool(
    "system_status",
    "Full health snapshot of the laptop: CPU, RAM, disks, battery, uptime, network and the "
    "heaviest running processes. Use this when the user asks how the laptop is doing, why it "
    "is slow, or whether it is plugged in.",
    {},
)
def system_status():
    import psutil

    lines = []
    lines.append(f"host: {os.environ.get('COMPUTERNAME', '?')}   user: {os.environ.get('USERNAME', '?')}")
    lines.append(f"local time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    boot = psutil.boot_time()
    up = int(time.time() - boot)
    lines.append(f"uptime: {up // 86400}d {up % 86400 // 3600}h {up % 3600 // 60}m")

    # short sampling window: 0.6s was a noticeable chunk of every reply's latency
    lines.append(f"\nCPU: {psutil.cpu_percent(interval=0.2):.0f}% across {psutil.cpu_count()} logical cores")

    mem = psutil.virtual_memory()
    lines.append(f"RAM: {mem.percent:.0f}% used - {_gb(mem.used)} of {_gb(mem.total)} ({_gb(mem.available)} free)")

    battery = psutil.sensors_battery()
    if battery:
        state = "charging" if battery.power_plugged else "on battery"
        left = ""
        if not battery.power_plugged and battery.secsleft and battery.secsleft > 0:
            left = f", ~{battery.secsleft // 3600}h {battery.secsleft % 3600 // 60}m left"
        lines.append(f"Battery: {battery.percent:.0f}% ({state}{left})")

    lines.append("\nDisks:")
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        lines.append(
            f"  {part.device:<6} {usage.percent:>3.0f}% used - {_gb(usage.free)} free of {_gb(usage.total)}"
        )

    net = psutil.net_io_counters()
    lines.append(f"\nNetwork since boot: {_gb(net.bytes_sent)} sent / {_gb(net.bytes_recv)} received")

    procs = []
    for proc in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            procs.append((proc.info["memory_info"].rss, proc.info["pid"], proc.info["name"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError, TypeError):
            continue
    procs.sort(reverse=True)
    lines.append("\nTop memory users:")
    for rss, pid, name in procs[:12]:
        lines.append(f"  {rss / (1024 ** 2):>7.0f} MB  pid {pid:<7} {name}")

    return {"text": "\n".join(lines)}


@tool(
    "list_processes",
    "List running processes, optionally filtered by name.",
    {
        "name_contains": {"type": "string", "description": "Only show processes whose name contains this."},
        "limit": {"type": "integer", "description": "Max rows. Default 40."},
    },
)
def list_processes(name_contains=None, limit=40):
    import psutil

    needle = (name_contains or "").lower()
    rows = []
    for proc in psutil.process_iter(["pid", "name", "memory_info", "username"]):
        try:
            info = proc.info
            if needle and needle not in (info["name"] or "").lower():
                continue
            mem = info["memory_info"].rss / (1024 ** 2) if info["memory_info"] else 0
            rows.append((mem, f"pid {info['pid']:<7} {mem:>7.0f} MB  {info['name']}"))
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError, TypeError):
            continue
    rows.sort(reverse=True)
    if not rows:
        return {"text": f"No processes matching '{name_contains}'."}
    body = "\n".join(row for _, row in rows[: int(limit or 40)])
    return {"text": f"{len(rows)} process(es):\n{body}"[: CONFIG.max_tool_output]}


@tool(
    "kill_process",
    "Force-close a running program by PID or by name. Asks the user first.",
    {
        "pid": {"type": "integer", "description": "Exact process ID."},
        "name": {"type": "string", "description": "Process name, e.g. chrome.exe - kills every match."},
    },
)
def kill_process(pid=None, name=None):
    import psutil

    protected = {
        "system", "system idle process", "registry", "smss.exe", "csrss.exe",
        "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe", "svchost.exe",
        "dwm.exe", "explorer.exe", "fontdrvhost.exe", "sihost.exe", "ctfmon.exe",
        "runtimebroker.exe", "audiodg.exe", "conhost.exe", "taskhostw.exe",
        "searchindexer.exe", "memory compression", "msmpeng.exe", "nissrv.exe",
        "securityhealthservice.exe", "python.exe", "pythonw.exe", "wscript.exe",
        "cmd.exe", "powershell.exe", "node.exe",
    }
    me = psutil.Process().pid
    killed = []
    failed = []

    def attempt(proc, label):
        try:
            proc_name = (proc.name() or "").lower()
            if proc.pid == me or proc_name in protected:
                failed.append(f"{label}: protected process")
                return
            proc.kill()
            killed.append(label)
        except Exception as exc:
            failed.append(f"{label}: {exc}")

    if pid:
        try:
            proc = psutil.Process(int(pid))
            attempt(proc, f"{proc.name()} (pid {pid})")
        except Exception as exc:
            failed.append(f"pid {pid}: {exc}")
    if name:
        needle = name.lower()
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if needle in (proc.info["name"] or "").lower():
                    attempt(proc, f"{proc.info['name']} (pid {proc.info['pid']})")
            except Exception as exc:
                failed.append(f"{proc.info.get('name')}: {exc}")
    if not killed and not failed:
        return {"text": "Nothing matched - no process was killed."}
    out = []
    if killed:
        out.append("Killed: " + ", ".join(killed))
    if failed:
        out.append("Failed: " + "; ".join(failed))
    return {"text": "\n".join(out)}


@tool(
    "free_ram",
    "Free up memory on the laptop by closing the biggest non-essential programs. Use this when "
    "the owner says the laptop is slow or asks to free RAM, or when you notice memory is nearly "
    "full. It never touches Windows system processes, the owner's shells, or this agent itself. "
    "Report how much was freed. Preview first with dry_run=true if unsure.",
    {
        "target_free_gb": {
            "type": "number",
            "description": "Stop once this much RAM is free. Default 2.0 GB.",
        },
        "keep": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Extra process names to protect, e.g. ['chrome.exe'].",
        },
        "dry_run": {
            "type": "boolean",
            "description": "true = only list what WOULD be closed. Default false.",
        },
    },
)
def free_ram(target_free_gb=2.0, keep=None, dry_run=False):
    import psutil

    protected = {
        # Windows core - killing these breaks or reboots the machine
        "system", "system idle process", "registry", "smss.exe", "csrss.exe", "wininit.exe",
        "winlogon.exe", "services.exe", "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe",
        "fontdrvhost.exe", "sihost.exe", "ctfmon.exe", "runtimebroker.exe", "audiodg.exe",
        "conhost.exe", "taskhostw.exe", "searchindexer.exe", "memory compression",
        # security
        "msmpeng.exe", "nissrv.exe", "securityhealthservice.exe",
        # us
        "python.exe", "pythonw.exe", "wscript.exe", "cmd.exe", "powershell.exe", "node.exe",
    }
    protected.update(name.lower() for name in (keep or []))

    me = psutil.Process().pid
    target_bytes = float(target_free_gb or 2.0) * (1024 ** 3)
    before = psutil.virtual_memory().available

    if before >= target_bytes:
        return {"text": f"Already {before / (1024 ** 3):.1f} GB free - nothing closed."}

    candidates = []
    for proc in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            info = proc.info
            name = (info["name"] or "").lower()
            if not name or name in protected or info["pid"] == me:
                continue
            rss = info["memory_info"].rss if info["memory_info"] else 0
            if rss > 60 * 1024 * 1024:      # only worth closing if over 60 MB
                candidates.append((rss, info["pid"], info["name"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError, TypeError):
            continue

    candidates.sort(reverse=True)
    if not candidates:
        return {"text": f"Only {before / (1024 ** 3):.1f} GB free, but nothing safe to close."}

    if dry_run:
        preview = "\n".join(f"  {r / (1024 ** 2):>6.0f} MB  {n} (pid {p})" for r, p, n in candidates[:12])
        return {"text": f"Would close, biggest first ({before / (1024 ** 3):.1f} GB free now):\n{preview}"}

    closed, freed = [], 0
    for rss, pid, name in candidates:
        if psutil.virtual_memory().available >= target_bytes:
            break
        try:
            psutil.Process(pid).terminate()      # polite close first
            closed.append(f"{name} ({rss / (1024 ** 2):.0f} MB)")
            freed += rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    psutil.wait_procs([p for p in psutil.process_iter() if p.pid in
                       {c[1] for c in candidates}], timeout=3)
    after = psutil.virtual_memory().available

    if not closed:
        return {"text": f"Couldn't close anything (permissions). Still {after / (1024 ** 3):.1f} GB free."}
    return {
        "text": f"Closed {len(closed)}: {', '.join(closed[:8])}\n"
                f"RAM free: {before / (1024 ** 3):.1f} GB -> {after / (1024 ** 3):.1f} GB"
    }


@tool(
    "power_action",
    "Lock, sleep, hibernate, restart, shut down or sign out of the laptop. "
    "lock and sleep run immediately; shutdown/restart/logoff/hibernate ask the user first.",
    {
        "action": {
            "type": "string",
            "enum": ["lock", "sleep", "hibernate", "shutdown", "restart", "logoff"],
        },
        "delay_seconds": {"type": "integer", "description": "Delay for shutdown/restart. Default 5."},
    },
    required=["action"],
)
def power_action(action, delay_seconds=5):
    action = action.lower()
    delay = int(delay_seconds or 5)
    commands = {
        "lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
        "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
        "hibernate": ["shutdown", "/h"],
        "shutdown": ["shutdown", "/s", "/t", str(delay)],
        "restart": ["shutdown", "/r", "/t", str(delay)],
        "logoff": ["shutdown", "/l"],
    }
    if action not in commands:
        return {"text": f"Unknown action '{action}'."}
    try:
        subprocess.Popen(commands[action], creationflags=_FLAGS)
    except Exception as exc:
        return {"text": f"Failed: {exc}"}
    suffix = f" in {delay}s" if action in ("shutdown", "restart") else ""
    return {"text": f"{action}{suffix} triggered. (Note: the agent goes offline when the laptop powers down.)"}


@tool(
    "clipboard",
    "Read or set the Windows clipboard.",
    {
        "action": {"type": "string", "enum": ["get", "set"]},
        "text": {"type": "string", "description": "Text to put on the clipboard when action=set."},
    },
    required=["action"],
)
def clipboard(action, text=None):
    try:
        import pyperclip
    except ImportError:
        return {"text": "pyperclip is not installed."}
    try:
        if action == "set":
            pyperclip.copy(text or "")
            return {"text": f"Clipboard set ({len(text or '')} characters)."}
        content = pyperclip.paste() or ""
        return {"text": f"Clipboard contains:\n{content[:CONFIG.max_tool_output]}" if content else "Clipboard is empty."}
    except Exception as exc:
        return {"text": f"Clipboard error: {exc}"}


@tool(
    "media_control",
    "Control audio: volume up/down/mute and play-pause/next/previous track. "
    "Volume steps move about 2% each, so pass repeat for bigger jumps.",
    {
        "action": {
            "type": "string",
            "enum": ["volume_up", "volume_down", "mute", "play_pause", "next_track", "prev_track"],
        },
        "repeat": {"type": "integer", "description": "How many times to press. Default 1."},
    },
    required=["action"],
)
def media_control(action, repeat=1):
    try:
        import pyautogui
    except Exception as exc:
        return {"text": f"pyautogui unavailable: {exc}"}

    keys = {
        "volume_up": "volumeup",
        "volume_down": "volumedown",
        "mute": "volumemute",
        "play_pause": "playpause",
        "next_track": "nexttrack",
        "prev_track": "prevtrack",
    }
    if action not in keys:
        return {"text": f"Unknown action '{action}'."}
    times = max(1, min(int(repeat or 1), 50))
    for _ in range(times):
        pyautogui.press(keys[action])
        time.sleep(0.03)
    return {"text": f"Pressed {keys[action]} x{times}."}
