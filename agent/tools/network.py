from .. import netrecover
from . import tool


@tool(
    "network_status",
    "Check the laptop's internet and Wi-Fi state: whether the internet actually works, which "
    "network it's joined to, and whether it's on the charger or running on battery.",
    {},
)
def network_status():
    online = netrecover.internet_up()
    state, ssid = netrecover.wlan_state()
    plugged = netrecover.power_plugged()
    power = "on charger" if plugged else ("on battery" if plugged is False else "unknown")

    lines = [
        f"internet: {'WORKING' if online else 'NOT WORKING'}",
        f"wifi    : {state or 'unknown'}" + (f" to '{ssid}'" if ssid else ""),
        f"power   : {power}",
    ]
    if not online:
        lines.append("\nUse network_repair to try to reconnect.")
    return {"text": "\n".join(lines)}


@tool(
    "wifi_add_network",
    "Save a NEW Wi-Fi network (name + password) on the laptop so it can join that network "
    "later on its own. Use this to pre-load a backup connection - a phone hotspot, an office "
    "or neighbour's Wi-Fi - while the laptop still has internet. Without this, a network the "
    "laptop has never joined cannot be used, because Windows has no password for it. "
    "The network is saved as auto-connect, so Windows will rejoin it by itself.",
    {
        "ssid": {"type": "string", "description": "Exact network name (case-sensitive)."},
        "password": {"type": "string", "description": "The Wi-Fi password."},
        "security": {
            "type": "string",
            "enum": ["WPA2PSK", "WPA3SAE", "WPAPSK", "open"],
            "description": "Security type. Default WPA2PSK (normal home Wi-Fi).",
        },
    },
    required=["ssid", "password"],
)
def wifi_add_network(ssid, password, security="WPA2PSK"):
    if security == "open":
        return {"text": "Open networks need no password - just connect to it directly."}
    ok, detail = netrecover.add_network(ssid, password, security=security)
    if ok:
        return {"text": f"Saved '{ssid}' as an auto-connect network. "
                        f"The laptop can now join it by itself if the main network goes down."}
    return {"text": f"Could not save '{ssid}'.\n{detail}"}


@tool(
    "wifi_list_networks",
    "List the Wi-Fi networks saved on the laptop and which are currently in range. Useful to "
    "check what it could fall back to if the main network dies.",
    {},
)
def wifi_list_networks():
    saved = netrecover.wlan_profiles()
    in_range = netrecover.visible_ssids()
    _, current = netrecover.wlan_state()

    lines = [f"Currently on: {current or 'nothing'}", "", "Saved networks (tried in this order):"]
    for name in saved:
        marks = []
        if name == current:
            marks.append("CONNECTED")
        elif name in in_range:
            marks.append("in range")
        lines.append(f"  - {name}" + (f"  [{', '.join(marks)}]" if marks else ""))
    if in_range - set(saved):
        lines.append("\nIn range but NOT saved (needs a password before it can be used):")
        lines += [f"  - {n}" for n in sorted(in_range - set(saved))]
    return {"text": "\n".join(lines)}


@tool(
    "network_repair",
    "Fix the internet when the laptop is offline: wakes the Wi-Fi radio, rescans, rejoins a "
    "saved network and renews the IP address. Use this if the owner says the internet or Wi-Fi "
    "is down, or if a command failed because there was no connection. Takes up to a minute.",
    {},
)
def network_repair():
    log = []
    ok = netrecover.repair(log=log.append)
    detail = "\n".join(log[-10:])
    if ok:
        _, ssid = netrecover.wlan_state()
        return {"text": f"Back online{f' via {ssid}' if ssid else ''}.\n\n{detail}"}
    return {"text": f"Still offline after trying.\n\n{detail}"}
