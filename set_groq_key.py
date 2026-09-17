"""Write GROQ_API_KEY into .env safely (called by SET_GROQ_KEY.bat)."""

import pathlib
import sys

key = (sys.argv[1] if len(sys.argv) > 1 else "").strip().strip('"').strip("'")
if not key:
    print("   no key given")
    raise SystemExit(1)

env = pathlib.Path(".env")
lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []

replaced = False
out = []
for line in lines:
    if line.strip().startswith("GROQ_API_KEY="):
        out.append(f"GROQ_API_KEY={key}")
        replaced = True
    else:
        out.append(line)

if not replaced:
    out.append(f"GROQ_API_KEY={key}")

env.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"   saved to .env (key length {len(key)}, starts with {key[:4]})")
