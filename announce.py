"""Send a one-off message from ORBIT to the owner's Discord channel (REST, no gateway)."""

import sys

import requests

from agent.config import CONFIG

MESSAGE = " ".join(sys.argv[1:]) or "I'm live."

headers = {
    "Authorization": f"Bot {CONFIG.discord_token}",
    "Content-Type": "application/json",
}

guilds = requests.get("https://discord.com/api/v10/users/@me/guilds", headers=headers, timeout=20).json()
if not isinstance(guilds, list) or not guilds:
    print("No guilds found:", guilds)
    raise SystemExit(1)

sent = False
for guild in guilds:
    channels = requests.get(
        f"https://discord.com/api/v10/guilds/{guild['id']}/channels", headers=headers, timeout=20
    ).json()
    if not isinstance(channels, list):
        continue
    for channel in channels:
        if channel.get("type") != 0:  # 0 = text channel
            continue
        resp = requests.post(
            f"https://discord.com/api/v10/channels/{channel['id']}/messages",
            headers=headers,
            json={"content": MESSAGE},
            timeout=20,
        )
        if resp.status_code in (200, 201):
            print(f"SENT to #{channel['name']} in {guild['name']}")
            sent = True
            break
    if sent:
        break

if not sent:
    print("Could not send - no writable text channel found.")
    raise SystemExit(1)
