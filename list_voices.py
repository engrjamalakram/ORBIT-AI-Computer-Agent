"""Show the ElevenLabs voices available on your account, so you can pick one for ORBIT.

Run:  .venv\\Scripts\\python.exe list_voices.py
"""

import requests

from agent.config import CONFIG

if not CONFIG.elevenlabs_key:
    print("\n  No ELEVENLABS_API_KEY in .env - run SET_VOICE_KEY.bat first.\n")
    raise SystemExit(1)

resp = requests.get(
    "https://api.elevenlabs.io/v1/voices",
    headers={"xi-api-key": CONFIG.elevenlabs_key},
    timeout=30,
)
if resp.status_code != 200:
    print(f"\n  ElevenLabs said {resp.status_code}: {resp.text[:300]}\n")
    raise SystemExit(1)

voices = resp.json().get("voices", [])
print(f"\n  {len(voices)} voice(s) on your account:\n")
print(f"  {'VOICE ID':<24} {'NAME':<22} DESCRIPTION")
print("  " + "-" * 78)
for v in voices:
    labels = v.get("labels") or {}
    desc = ", ".join(f"{k}={val}" for k, val in labels.items() if val)
    print(f"  {v.get('voice_id',''):<24} {(v.get('name') or '')[:21]:<22} {desc[:34]}")

print("""
  To use one, put its VOICE ID in .env:

     ELEVENLABS_VOICE_EN=<id for English>
     ELEVENLABS_VOICE_UR=<id for Urdu>     (leave blank to use the same voice)

  For Urdu, search the ElevenLabs Voice Library for a native Urdu or Hindi
  speaker and click "Add to my voices" - it will then appear in this list.
""")
