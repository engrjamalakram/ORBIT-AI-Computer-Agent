"""Voice in and out.

  - Speech to text: Groq whisper-large-v3 when GROQ_API_KEY is set (~1-2s, best Urdu accuracy),
    falling back automatically to local faster-whisper if the key is missing or the call fails.
  - Text to speech: edge-tts, free Microsoft neural voices, picks a female Urdu or English voice.

The local model is lazy-loaded, so the bot starts instantly.
"""

import re
import time
from pathlib import Path

from .config import CONFIG

_URDU = re.compile(r"[؀-ۿݐ-ݿ]")
_whisper = None
_whisper_error = None

# Discord channel IDs where the `speak` tool already sent audio this turn.
# Keyed by ID (not by object) because the Agent SDK invokes tool handlers in a context
# captured at connect() time, so the Channel instance a tool sees can be a stale one.
SPOKE_CHANNELS = set()


def available():
    """True if the speech-to-text stack imported cleanly."""
    return _load_whisper() is not None


def warmup():
    """Load the local speech model ahead of time so the first voice note isn't slow.

    Skipped when Groq is configured - the local model is only the offline fallback there,
    and loading it would waste ~300MB of RAM on a machine that hasn't much to spare.
    Safe to call from a background thread at startup.
    """
    if CONFIG.groq_api_key:
        print(f"[voice] speech-to-text: Groq {CONFIG.groq_stt_model} (local model kept as fallback)")
        return
    try:
        _load_whisper()
        print(f"[voice] speech model '{CONFIG.whisper_model}' ready")
    except Exception as exc:  # noqa: BLE001
        print(f"[voice] warmup failed: {exc}")


def _load_whisper():
    global _whisper, _whisper_error
    if _whisper is not None or _whisper_error is not None:
        return _whisper
    try:
        from faster_whisper import WhisperModel

        # int8 on CPU is the fast, low-memory path and is plenty for command dictation.
        # cpu_threads matches this machine's 4 hardware threads - measurably faster than the default.
        _whisper = WhisperModel(
            CONFIG.whisper_model, device="cpu", compute_type="int8", cpu_threads=4
        )
    except Exception as exc:  # noqa: BLE001
        _whisper_error = exc
        print(f"[voice] speech-to-text unavailable: {exc}")
    return _whisper


# Groq's verbose_json returns language names, not codes.
_LANG_NAMES = {
    "english": "en", "urdu": "ur", "hindi": "ur", "punjabi": "ur",
    "arabic": "ar", "persian": "fa",
}


def _normalise_lang(language):
    language = (language or "").strip().lower()
    language = _LANG_NAMES.get(language, language)
    # Whisper very often tags Urdu speech as Hindi; this owner speaks Urdu.
    if language.startswith("hi"):
        language = "ur"
    return language


def _transcribe_groq(audio_path):
    """Cloud transcription. Returns (text, lang) or None to fall back to local."""
    if not CONFIG.groq_api_key:
        return None
    try:
        import requests

        with open(audio_path, "rb") as handle:
            response = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {CONFIG.groq_api_key}"},
                files={"file": (Path(audio_path).name, handle, "application/octet-stream")},

                data={
                    "model": CONFIG.groq_stt_model,
                    "response_format": "verbose_json",
                    "temperature": "0",
                    "language": "ur",
                },


                timeout=CONFIG.groq_timeout,
            )
        if response.status_code != 200:
            print(f"[voice] Groq {response.status_code}: {response.text[:200]} - using local model")
            return None
        payload = response.json()
        text = (payload.get("text") or "").strip()
        if not text:
            return None
        return text, _normalise_lang(payload.get("language"))
    except Exception as exc:  # noqa: BLE001 - any failure just falls back
        print(f"[voice] Groq failed ({exc}) - using local model")
        return None


def transcribe(audio_path):
    """Return (text, language_code). Tries Groq (fast, accurate), falls back to local."""
    got = _transcribe_groq(audio_path)
    if got:
        return got

    model = _load_whisper()
    if model is None:
        return "", ""
    try:
        segments, info = model.transcribe(
            str(audio_path),
            beam_size=1,                     # greedy: ~3x faster on this CPU, same text on short commands
            vad_filter=True,                 # skip silence - big win on phone recordings
            condition_on_previous_text=False,
            without_timestamps=True,         # we only need the words
            temperature=0.0,
        )
        text = " ".join(seg.text for seg in segments).strip()
        return text, _normalise_lang(getattr(info, "language", ""))
    except Exception as exc:  # noqa: BLE001
        print(f"[voice] transcription failed: {exc}")
        return "", ""


def _pick_voice(text, language):
    is_urdu = language.startswith("ur") or bool(_URDU.search(text or ""))
    return CONFIG.voice_urdu if is_urdu else CONFIG.voice_english


# Emotion cues like [sighs] or [warmly]. ElevenLabs v3 performs them; every other
# engine would literally read the brackets out loud, so we strip them there.
_TAG = re.compile(r"\[[a-zA-Z][a-zA-Z ,'-]{0,28}\]")


def _clean_for_speech(text, keep_tags=False):
    """Strip markdown / code so the voice sounds natural and short."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"[*_#>]+", "", text)
    text = re.sub(r"-# ", "", text)
    if not keep_tags:
        text = _TAG.sub(" ", text)
    text = re.sub(r"\n{2,}", ". ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > CONFIG.tts_max_chars:
        text = text[: CONFIG.tts_max_chars].rsplit(" ", 1)[0] + " ..."
    return text


def _use_elevenlabs():
    if CONFIG.tts_provider == "edge":
        return False
    if CONFIG.tts_provider == "elevenlabs":
        return bool(CONFIG.elevenlabs_key)
    return bool(CONFIG.elevenlabs_key)      # auto


def elevenlabs_try(text, voice, model, timeout=60):
    """One ElevenLabs request. Returns (audio_bytes, error_text)."""
    import requests

    try:
        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
            headers={"xi-api-key": CONFIG.elevenlabs_key, "Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": model,
                "voice_settings": {
                    "stability": CONFIG.elevenlabs_stability,
                    "similarity_boost": CONFIG.elevenlabs_similarity,
                },
            },
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"unreachable: {exc}"

    if response.status_code == 200:
        return response.content, ""
    return None, f"{response.status_code}: {response.text[:200]}"


def _elevenlabs_speak(text, language, out_path):
    """Realistic, emotional speech. Returns True on success, False to fall back.

    If the account cannot use v3 (plan limits), we retry with multilingual_v2 - but only
    for non-Urdu, because v2 does not speak Urdu at all and would produce nonsense.
    """
    is_urdu = language.startswith("ur") or bool(_URDU.search(text))
    voice = (CONFIG.elevenlabs_voice_ur if is_urdu else "") or CONFIG.elevenlabs_voice_en
    if not voice:
        return False

    audio, error = elevenlabs_try(text, voice, CONFIG.elevenlabs_model)
    if audio is None and not is_urdu and CONFIG.elevenlabs_model != "eleven_multilingual_v2":
        print(f"[voice] {CONFIG.elevenlabs_model} unavailable ({error}) - trying multilingual_v2")
        # v2 cannot perform emotion tags, so strip them rather than read them aloud
        audio, error = elevenlabs_try(_TAG.sub(" ", text), voice, "eleven_multilingual_v2")

    if audio is None:
        print(f"[voice] ElevenLabs failed ({error}) - using free Microsoft voice")
        return False

    out_path.write_bytes(audio)
    return True


async def synthesize(text, language=""):
    """Speak `text` to an mp3 file and return its Path, or None on failure.

    Tries ElevenLabs first when a key is configured - it is the only engine that both
    speaks Urdu and acts on emotion cues. Falls back to the free Microsoft voices.
    """
    import asyncio

    import edge_tts

    out = CONFIG.voice_dir / f"reply-{int(time.time() * 1000)}.mp3"

    if _use_elevenlabs():
        rich = _clean_for_speech(text, keep_tags=True)
        if rich:
            ok = await asyncio.to_thread(_elevenlabs_speak, rich, language, out)
            if ok:
                _prune()
                return out

    # free fallback - tags must go, or it reads "[sighs]" out loud
    speech = _clean_for_speech(text)
    if not speech:
        return None

    voice = _pick_voice(speech, language)
    try:
        await edge_tts.Communicate(
            speech, voice, rate=CONFIG.voice_rate, pitch=CONFIG.voice_pitch
        ).save(str(out))
    except Exception as exc:  # noqa: BLE001
        print(f"[voice] text-to-speech failed ({voice}): {exc}")
        # retry once with a safe fallback voice before giving up
        try:
            fallback = CONFIG.voice_urdu if voice == CONFIG.voice_english else CONFIG.voice_english
            await edge_tts.Communicate(speech, fallback).save(str(out))
        except Exception as exc2:  # noqa: BLE001
            print(f"[voice] fallback also failed: {exc2}")
            return None

    _prune()
    return out


def synthesize_sync(text, language=""):
    """Blocking wrapper around synthesize(), for calling from a sync tool handler."""
    import asyncio

    try:
        return asyncio.run(synthesize(text, language))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(synthesize(text, language))
        finally:
            loop.close()


def _prune(keep=40):
    files = sorted(CONFIG.voice_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            pass
