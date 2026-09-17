"""Central safety policy for ORBIT tool execution.

Every LLM tool call must pass through this module before a handler runs.  Keeping the
policy here makes the API and Claude Agent SDK brains enforce the same rules.
"""

import re
from typing import Awaitable, Callable

# Tool-level actions that can change state or have irreversible external effects.
# These are deliberately broader than the old API-only list so both brains share one policy.
ALWAYS_CONFIRM = {
    "write_file": "writes or modifies a file on disk",
    "delete_path": "permanently deletes files or folders",
    "kill_process": "force-closes a running program",
    "free_ram": "closes running applications to free memory",
    "wifi_add_network": "stores a Wi-Fi network and password on the laptop",
    "whatsapp_send": "sends an external message to a contact",
    "clipboard": "changes the Windows clipboard",
}

# Shell commands that look destructive, privileged, externally consequential, or system-changing.
SHELL_CONFIRM_PATTERNS = [
    (r"\bremove-item\b|\brm\b|\bdel\b|\berase\b|\brd\b|\brmdir\b", "deletes files"),
    (r"\bformat(-volume)?\b|\bdiskpart\b|\bclear-disk\b|\binitialize-disk\b", "wipes a disk"),
    (r"\bshutdown\b|\bstop-computer\b|\brestart-computer\b|\blogoff\b", "powers off / restarts"),
    (r"\breg\s+(add|delete|import)\b|\bset-itemproperty\b.*hk(lm|cu)|\bnew-itemproperty\b", "edits the registry"),
    (r"\bnet\s+user\b|\bnet\s+localgroup\b|\bnew-localuser\b|\badd-localgroupmember\b", "changes Windows accounts"),
    (r"\buninstall\b|\bmsiexec\b.*/x|\bwinget\s+uninstall\b|\bchoco\s+uninstall\b", "uninstalls software"),
    (r"\bvssadmin\b.*delete|\bwbadmin\b.*delete|\bcipher\b.*/w", "destroys backups / shadow copies"),
    (r"\bbcdedit\b|\bbootrec\b|\bsfc\b\s*/scannow", "touches boot configuration"),
    (r"\bset-executionpolicy\b|\bdisable-\w*(defender|firewall)\b|\bset-mppreference\b", "weakens security settings"),
    (r"\bstop-service\b|\bsc\s+delete\b|\bsc\s+config\b|\bset-service\b", "changes Windows services"),
    (r"\btaskkill\b|\bstop-process\b", "force-kills processes"),
    (r"\bschtasks\b\s*/(create|delete|change)|\bregister-scheduledtask\b", "changes scheduled tasks"),
    (r"(iwr|invoke-webrequest|curl|wget|irm|invoke-restmethod)[^|\n]*\|\s*(iex|invoke-expression)", "downloads and runs code"),
    (r"\bstart-process\b[^\n]*-verb\s+runas", "relaunches something as administrator"),
    (r"\bnetsh\b|\bnew-netfirewallrule\b", "changes network / firewall config"),
    (r"\bgit\b\s+(push|reset\s+--hard|clean\s+-\w*f)", "rewrites or publishes a git repo"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), why) for p, why in SHELL_CONFIRM_PATTERNS]


def classify(tool_name: str, args: dict):
    """Return (needs_confirmation: bool, reason: str)."""
    args = args or {}

    if tool_name in ALWAYS_CONFIRM:
        return True, ALWAYS_CONFIRM[tool_name]

    if tool_name == "power_action":
        action = str(args.get("action", "")).lower()
        if action in ("shutdown", "restart", "logoff", "hibernate"):
            return True, f"will {action} the laptop"
        return False, ""

    if tool_name == "run_powershell":
        command = str(args.get("command", ""))
        # PowerShell is an unrestricted OS execution boundary.  Even a command that does not
        # match a known destructive regex must be approved before the agent can run it.
        for pattern, why in _COMPILED:
            if pattern.search(command):
                return True, why
        return True, "executes a PowerShell command on the laptop"

    return False, ""


def describe(tool_name: str, args: dict, limit: int = 900) -> str:
    """A short human-readable preview of what is about to happen."""
    args = args or {}
    if tool_name == "run_powershell":
        body = str(args.get("command", ""))
    elif tool_name == "write_file":
        content = str(args.get("content", ""))
        preview = content[:300] + ("..." if len(content) > 300 else "")
        body = f"path: {args.get('path')}\nmode: {args.get('mode', 'overwrite')}\n---\n{preview}"
    elif tool_name == "whatsapp_send":
        body = f"contact: {args.get('contact')}\nmessage: {args.get('message')}"
    elif tool_name == "wifi_add_network":
        # Never put the Wi-Fi password into a Discord confirmation message or log.
        body = f"ssid: {args.get('ssid')}\nsecurity: {args.get('security', 'WPA2PSK')}\npassword: [REDACTED]"
    elif tool_name == "clipboard" and str(args.get("action", "")).lower() == "set":
        body = f"action: set\ntext: [REDACTED]"
    else:
        body = "\n".join(f"{k}: {v}" for k, v in args.items())
    return body[:limit] + ("\n... (truncated)" if len(body) > limit else "")


async def execute(
    tool_name: str,
    args: dict,
    handler: Callable,
    confirm_callback: Callable[[str, str, str], Awaitable[bool]] | None = None,
):
    """Authorize and execute one tool call.

    This is the single policy gateway used by both ORBIT brains.  A caller that supplies a
    confirmation callback can present the approval UI; without approval, risky actions never
    reach the underlying handler.
    """
    needs_confirmation, reason = classify(tool_name, args)
    if needs_confirmation:
        if confirm_callback is None:
            return {
                "text": f"DENIED: '{tool_name}' requires owner confirmation, but no confirmation channel is available."
            }, False
        approved = await confirm_callback(tool_name, reason, describe(tool_name, args))
        if not approved:
            return {
                "text": (
                    "DENIED: the owner refused this action. Do not retry it or attempt an equivalent "
                    "action another way. Ask them what to do instead."
                )
            }, False

    return await __import__("asyncio").to_thread(handler, **(args or {})), True
