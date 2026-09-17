"""Set one KEY=value in .env without touching anything else.

Usage:  python set_env_value.py NAME value
"""

import pathlib
import sys

if len(sys.argv) < 3:
    print("   usage: set_env_value.py NAME value")
    raise SystemExit(1)

name = sys.argv[1].strip()
value = " ".join(sys.argv[2:]).strip().strip('"').strip("'")
if not value:
    print("   no value given")
    raise SystemExit(1)

env = pathlib.Path(".env")
lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []

out, replaced = [], False
for line in lines:
    if line.strip().startswith(f"{name}="):
        out.append(f"{name}={value}")
        replaced = True
    else:
        out.append(line)
if not replaced:
    out.append(f"{name}={value}")

env.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"   saved {name} (length {len(value)})")
