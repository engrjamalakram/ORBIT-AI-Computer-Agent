import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _int(name, default):
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _float(name, default):
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _ids(raw):
    out = set()
    for part in (raw or "").replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


class Config:
    discord_token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    allowed_users = _ids(os.getenv("DISCORD_ALLOWED_USER_IDS"))

    model = os.getenv("AGENT_MODEL", "claude-opus-5").strip() or "claude-opus-5"

    # Which brain to use:
    #   auto         -> subscription if no API key is set, else API
    #   subscription -> always use your Claude Code login (no per-token API cost)
    #   api          -> always use ANTHROPIC_API_KEY
    brain = os.getenv("BRAIN", "auto").strip().lower() or "auto"
    # Model for subscription mode. 'opus' = best quality. Blank = your Claude Code default.
    subscription_model = os.getenv("SUBSCRIPTION_MODEL", "opus").strip()

    # Long jobs (e.g. "generate images for 5 products") need hundreds of steps - every
    # click, wait and screenshot is one step. 30 was far too low and caused silent stalls.
    max_iterations = _int("MAX_ITERATIONS", 400)
    # If the step limit is still hit, carry on automatically this many times instead of
    # stopping dead while the owner is away.
    auto_continue = _int("AUTO_CONTINUE", 3)
    # Post a "gear" line to Discord for every single tool call. Noisy and slow - off by default.
    show_tool_calls = os.getenv("SHOW_TOOL_CALLS", "false").strip().lower() in ("true", "1", "yes")
    shell_timeout = _int("SHELL_TIMEOUT", 180)
    history_turns = _int("HISTORY_TURNS", 30)
    confirm_risky = os.getenv("CONFIRM_RISKY", "true").strip().lower() in ("true", "1", "yes")

    # ---- identity + voice ----
    agent_name = os.getenv("AGENT_NAME", "ORBIT").strip() or "ORBIT"
    # voice replies: auto (mirror the user), always, or never
    voice_replies = os.getenv("VOICE_REPLIES", "auto").strip().lower()
    # faster-whisper model: tiny / base / small / medium. bigger = better Urdu, slower.
    # 'base' measured fastest-with-best-Urdu on this CPU: 3.7x quicker than 'small'
    # AND it returns proper Urdu script where 'small' returned Devanagari.
    whisper_model = os.getenv("WHISPER_MODEL", "base").strip() or "base"

    # Groq cloud speech-to-text: ~1-2s instead of ~13s locally, and whisper-large-v3 is
    # far more accurate (especially Urdu) than anything this CPU can run.
    # Falls back to the local model automatically if the key is missing or the call fails.
    groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
    groq_stt_model = os.getenv("GROQ_STT_MODEL", "whisper-large-v3").strip() or "whisper-large-v3"
    groq_timeout = _int("GROQ_TIMEOUT", 25)
    # Ava = one of the most natural/human female voices Microsoft ships. Uzma = best Urdu female.
    voice_english = os.getenv("VOICE_ENGLISH", "en-US-AvaMultilingualNeural").strip() or "en-US-AvaMultilingualNeural"
    voice_urdu = os.getenv("VOICE_URDU", "ur-PK-UzmaNeural").strip() or "ur-PK-UzmaNeural"

    # ---- realistic voice (ElevenLabs) ----
    # auto = use ElevenLabs when a key is set, otherwise the free edge-tts voices.
    tts_provider = os.getenv("TTS_PROVIDER", "auto").strip().lower() or "auto"
    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    # eleven_v3 is the only model that speaks Urdu AND understands emotion tags like [sighs].
    elevenlabs_model = os.getenv("ELEVENLABS_MODEL", "eleven_v3").strip() or "eleven_v3"
    elevenlabs_voice_en = os.getenv("ELEVENLABS_VOICE_EN", "9BWtsMINqrJLrRacOk9x").strip()
    elevenlabs_voice_ur = os.getenv("ELEVENLABS_VOICE_UR", "").strip()   # blank = same voice as English
    # lower stability = more emotional swing; 0.5 natural, 0.3 very expressive
    elevenlabs_stability = _float("ELEVENLABS_STABILITY", 0.45)
    elevenlabs_similarity = _float("ELEVENLABS_SIMILARITY", 0.75)
    tts_max_chars = _int("TTS_MAX_CHARS", 1400)
    # Slight speed-up + gentle pitch lift reads as more natural/conversational than the flat default.
    voice_rate = os.getenv("VOICE_RATE", "+8%").strip() or "+0%"
    voice_pitch = os.getenv("VOICE_PITCH", "+2Hz").strip() or "+0Hz"

    max_tool_output = 6000          # chars of tool output handed back to Claude
    discord_msg_limit = 1900        # Discord hard limit is 2000
    runtime_dir = ROOT / ".runtime"
    shots_dir = ROOT / ".runtime" / "shots"
    voice_dir = ROOT / ".runtime" / "voice"


CONFIG = Config()
CONFIG.runtime_dir.mkdir(parents=True, exist_ok=True)
CONFIG.shots_dir.mkdir(parents=True, exist_ok=True)
CONFIG.voice_dir.mkdir(parents=True, exist_ok=True)


def effective_brain():
    """Return 'subscription' or 'api' based on config and what's available."""
    if CONFIG.brain == "api":
        return "api"
    if CONFIG.brain == "subscription":
        return "subscription"
    # auto
    return "api" if CONFIG.anthropic_key else "subscription"


def _claude_cli_present():
    import shutil

    if shutil.which("claude"):
        return True
    # global npm install location on Windows
    candidate = Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd"
    return candidate.exists()


def validate():
    """Return a list of human-readable setup problems (empty list = good to go)."""
    problems = []
    if not CONFIG.discord_token:
        problems.append("DISCORD_BOT_TOKEN is empty in .env")
    if not CONFIG.allowed_users:
        problems.append(
            "DISCORD_ALLOWED_USER_IDS is empty in .env - without it the agent "
            "would refuse everyone (or, worse, obey anyone). Put your own Discord user ID there."
        )

    mode = effective_brain()
    if mode == "api" and not CONFIG.anthropic_key:
        problems.append(
            "BRAIN=api but ANTHROPIC_API_KEY is empty. Either add the key, or set BRAIN=subscription "
            "to run on your Claude Code login instead."
        )
    if mode == "subscription" and not _claude_cli_present():
        problems.append(
            "Subscription mode needs the Claude Code CLI, which wasn't found. Install it with "
            "`npm i -g @anthropic-ai/claude-code` and run `claude` once to sign in - or add an "
            "ANTHROPIC_API_KEY to .env to use the API instead."
        )
    return problems
