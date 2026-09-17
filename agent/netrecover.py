"""Get the laptop back online by itself after a power cut.

The situation this solves: the electricity goes out, the router dies, the laptop keeps
running on battery. When the power returns the router reboots and the charger starts
charging - but Windows often does NOT rejoin the Wi-Fi on its own, so the laptop sits
there connected to nothing while the owner is out.

So we do it actively:
  - notice the charger came back (electricity restored -> the router is booting)
  - wake the Wi-Fi radio, rescan, and reconnect to a known network
  - renew DHCP if we are "connected" but still have no internet
  - keep trying until the internet is genuinely reachable

Everything here is best-effort and never raises: the worst case is we try again later.
"""

import socket
import subprocess
import time

from .config import CONFIG

_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_LAST_WIFI = CONFIG.runtime_dir / "last_wifi.txt"


def _run(args, timeout=25):
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            creationflags=_FLAGS, errors="replace",
        )
        return (proc.stdout or "") + (proc.stderr or "")
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------- connectivity

def internet_up(timeout=4):
    """True only if something on the internet actually answers - not just 'adapter exists'."""
    for host, port in (("discord.com", 443), ("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def power_plugged():
    """True if charging/on AC, False on battery, None if unknown."""
    try:
        import psutil

        battery = psutil.sensors_battery()
        return None if battery is None else bool(battery.power_plugged)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- wlan helpers

def _after_colon(line):
    return line.split(":", 1)[1].strip() if ":" in line else ""


def wlan_interface():
    for line in _run(["netsh", "wlan", "show", "interfaces"]).splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("name") and ":" in stripped:
            name = _after_colon(stripped)
            if name:
                return name
    return "Wi-Fi"


def wlan_state():
    """Return (state, ssid) e.g. ('connected', 'MyHomeWiFi') or ('disconnected', '')."""
    state, ssid = "", ""
    for line in _run(["netsh", "wlan", "show", "interfaces"]).splitlines():
        stripped = line.strip()
        low = stripped.lower()
        if low.startswith("state") and ":" in stripped:
            state = _after_colon(stripped).lower()
        elif low.startswith("ssid") and not low.startswith("bssid") and ":" in stripped:
            ssid = ssid or _after_colon(stripped)
    return state, ssid


def wlan_profiles():
    """Saved networks, most-recently-successful first."""
    names = []
    for line in _run(["netsh", "wlan", "show", "profiles"]).splitlines():
        stripped = line.strip()
        if "profile" in stripped.lower() and ":" in stripped:
            name = _after_colon(stripped)
            if name and name not in names:
                names.append(name)

    last = ""
    try:
        last = _LAST_WIFI.read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001
        pass
    if last and last in names:                       # try what worked last time first
        names.remove(last)
        names.insert(0, last)
    return names


def visible_ssids():
    """SSIDs currently in range. Empty set means the scan failed - don't treat as 'none exist'."""
    found = set()
    for line in _run(["netsh", "wlan", "show", "networks"]).splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("ssid ") and ":" in stripped:
            name = _after_colon(stripped)
            if name:
                found.add(name)
    return found


def ensure_auto_connect(log=None):
    """Force every saved network to 'connect automatically'.

    A profile set to 'connect manually' is never rejoined by Windows on its own - which is
    exactly how a laptop ends up sitting offline after the router reboots. Cheap to re-apply,
    so we do it at every startup.
    """
    fixed = []
    for profile in wlan_profiles():
        detail = _run(["netsh", "wlan", "show", "profile", f"name={profile}"])
        low = detail.lower()
        if "connect manually" in low or "connection mode" in low and "automatic" not in low:
            out = _run(["netsh", "wlan", "set", "profileparameter",
                        f"name={profile}", "connectionmode=auto"])
            if "updated successfully" in out.lower():
                fixed.append(profile)
    if fixed and log:
        log(f"[net] set to auto-connect: {', '.join(fixed)}")
    return fixed


def add_network(ssid, password, security="WPA2PSK", encryption="AES"):
    """Save a NEW Wi-Fi network so she can join it later without anyone present.

    Use this to pre-load a backup (phone hotspot, neighbour's Wi-Fi) while the laptop is
    still online - otherwise an unknown network is unusable, because Windows has no password.
    """
    import html
    import os
    import tempfile

    name = html.escape(str(ssid))
    key = html.escape(str(password))
    hex_ssid = ssid.encode("utf-8").hex().upper()

    xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
  <name>{name}</name>
  <SSIDConfig><SSID><hex>{hex_ssid}</hex><name>{name}</name></SSID></SSIDConfig>
  <connectionType>ESS</connectionType>
  <connectionMode>auto</connectionMode>
  <MSM><security>
    <authEncryption>
      <authentication>{security}</authentication>
      <encryption>{encryption}</encryption>
      <useOneX>false</useOneX>
    </authEncryption>
    <sharedKey><keyType>passPhrase</keyType><protected>false</protected>
      <keyMaterial>{key}</keyMaterial></sharedKey>
  </security></MSM>
</WLANProfile>"""

    handle, path = tempfile.mkstemp(suffix=".xml")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            f.write(xml)
        out = _run(["netsh", "wlan", "add", "profile", f"filename={path}", "user=all"])
    finally:
        try:
            os.unlink(path)          # never leave the password lying on disk
        except OSError:
            pass
    return ("added" in out.lower() or "successfully" in out.lower()), out.strip()[:300]


def _remember(ssid):
    try:
        _LAST_WIFI.write_text(ssid, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def wlan_connect(profile, interface):
    out = _run(["netsh", "wlan", "connect", f"name={profile}", f"interface={interface}"]).lower()
    return "success" in out or "completed" in out


def _wake_radio(interface):
    """Best effort: turn the adapter back on. Some of these need admin - failure is fine."""
    _run(["netsh", "interface", "set", "interface", f"name={interface}", "admin=enable"], timeout=15)
    _run(["powershell", "-NoProfile", "-Command",
          f"Enable-NetAdapter -Name '{interface}' -Confirm:$false -ErrorAction SilentlyContinue"], timeout=25)


def _renew_dhcp():
    _run(["ipconfig", "/flushdns"], timeout=20)
    _run(["ipconfig", "/renew"], timeout=45)


# ---------------------------------------------------------------- the repair

def repair(log=print):
    """One full attempt to get back online. Returns True if the internet is reachable after."""
    if internet_up():
        return True

    interface = wlan_interface()
    state, ssid = wlan_state()
    log(f"[net] offline (wifi: {state or 'unknown'}{', ' + ssid if ssid else ''}) - repairing")

    # Case 1: Windows thinks we're connected but there's no internet.
    # Usually the router rebooted and our DHCP lease is stale.
    if state.startswith("connected"):
        _renew_dhcp()
        if internet_up():
            log("[net] back online after DHCP renew")
            if ssid:
                _remember(ssid)
            return True
        # lease renew didn't help - drop the link so we can cleanly rejoin
        _run(["netsh", "wlan", "disconnect", f"interface={interface}"], timeout=15)
        time.sleep(2)

    # Case 2: not associated with anything - wake the radio and rejoin a known network.
    _wake_radio(interface)
    time.sleep(2)

    profiles = wlan_profiles()
    if not profiles:
        log("[net] no saved Wi-Fi profiles to connect to")
        return False

    in_range = visible_ssids()
    # If the scan came back empty the radio may still be settling - try everything rather
    # than wrongly concluding nothing is nearby.
    candidates = [p for p in profiles if p in in_range] or profiles

    for profile in candidates[:8]:
        log(f"[net] trying '{profile}'")
        if not wlan_connect(profile, interface):
            continue
        for _ in range(6):                 # give it up to ~12s to associate + get an IP
            time.sleep(2)
            if internet_up():
                log(f"[net] back online via '{profile}'")
                _remember(profile)
                return True
        _renew_dhcp()
        if internet_up():
            log(f"[net] back online via '{profile}' after DHCP renew")
            _remember(profile)
            return True

    log("[net] still offline - will try again shortly")
    return False


def wait_until_online(log=print, first_delay=3):
    """Block until the internet is back, actively repairing - not just waiting.

    Reconnect attempts get slower when nothing changes, but the moment the charger comes
    back (electricity restored) we retry hard, because that means the router is booting.
    """
    if internet_up():
        return

    log("[net] no internet - starting auto-recovery")
    was_plugged = power_plugged()
    delay = first_delay
    since_power_back = None

    while True:
        plugged = power_plugged()
        if plugged and was_plugged is False:
            log("[net] charger reconnected - electricity is back, router should be booting")
            since_power_back = time.time()
            delay = 5                      # retry hard for the next few minutes
        was_plugged = plugged

        if repair(log=log):
            return

        # stay aggressive for 5 minutes after power returns, then ease off
        if since_power_back and (time.time() - since_power_back) < 300:
            delay = 15
        else:
            delay = min(delay * 2, 120)
        time.sleep(delay)
