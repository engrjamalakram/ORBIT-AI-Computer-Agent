"""Check exactly what your ElevenLabs key can do - plan, credits, and which models work.

Run:  .venv\\Scripts\\python.exe check_voice.py
"""

import requests

from agent import voice
from agent.config import CONFIG

print()
if not CONFIG.elevenlabs_key:
    print("  No ELEVENLABS_API_KEY found in .env")
    print("  Run SET_VOICE_KEY.bat and paste your key.\n")
    raise SystemExit(1)

# ---- 1. account / plan ----
try:
    sub = requests.get(
        "https://api.elevenlabs.io/v1/user/subscription",
        headers={"xi-api-key": CONFIG.elevenlabs_key}, timeout=30,
    )
except Exception as exc:  # noqa: BLE001
    print(f"  Could not reach ElevenLabs: {exc}\n")
    raise SystemExit(1)

if sub.status_code != 200:
    print(f"  Key rejected ({sub.status_code}). Check you copied the whole key.\n")
    raise SystemExit(1)

info = sub.json()
used = info.get("character_count", 0)
limit = info.get("character_limit", 0)
print(f"  Plan            : {info.get('tier', '?')}")
print(f"  Credits used    : {used:,} of {limit:,}  ({max(0, limit-used):,} left)")

# ---- 2. which models actually work ----
voice_en = CONFIG.elevenlabs_voice_en
print(f"\n  Testing models with voice {voice_en} ...\n")

tests = [
    ("eleven_v3 + English + emotion", "eleven_v3",
     "[warmly] Hello! Hmm, everything looks good."),
    ("eleven_v3 + URDU", "eleven_v3",
     "[warmly] السلام علیکم، سب ٹھیک چل رہا ہے۔"),
    ("eleven_multilingual_v2 + English", "eleven_multilingual_v2",
     "Hello, everything looks good."),
]

works = {}
for label, model, text in tests:
    audio, error = voice.elevenlabs_try(text, voice_en, model, timeout=45)
    ok = audio is not None
    works[label] = ok
    print(f"   {'OK  ' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"          -> {error}")

# ---- 3. verdict ----
print("\n  " + "-" * 60)
if works.get("eleven_v3 + URDU"):
    print("  Best case: v3 works for BOTH Urdu and English, with emotions.")
    print("  Nothing to change - ORBIT will use it automatically.")
elif works.get("eleven_v3 + English + emotion"):
    print("  v3 works for English but not Urdu on this key.")
    print("  ORBIT will use v3 for English and the free Microsoft voice for Urdu.")
elif works.get("eleven_multilingual_v2 + English"):
    print("  Your plan does not include v3, only multilingual_v2.")
    print("  v2 has NO Urdu and NO emotion tags - so v3 needs a paid plan ($6/mo Starter).")
    print("  Set ELEVENLABS_MODEL=eleven_multilingual_v2 in .env for better English,")
    print("  or leave everything as is and keep the free Microsoft voices.")
else:
    print("  No ElevenLabs model worked. ORBIT will keep using the free voices.")
    print("  Check your credits above - you may have run out this month.")
print()
