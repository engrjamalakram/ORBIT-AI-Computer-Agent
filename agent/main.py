"""Discord front end: you type from your phone, the laptop does the work."""

import asyncio
import os
import sys
import time
from pathlib import Path

import discord

from . import netrecover, voice
from .config import CONFIG, effective_brain, validate


def _make_brain():
    if effective_brain() == "subscription":
        from .brain_sdk import SdkBrain

        return SdkBrain(), "subscription (Claude Code login)"
    from .brain import Brain

    return Brain(), "API key"

AUDIO_EXTS = (".ogg", ".oga", ".mp3", ".wav", ".m4a", ".webm", ".opus", ".flac", ".aac")

HELP = """**{name} - your laptop, from your phone**

Talk to me in plain English - by text OR by voice (hold the mic in Discord to send a voice note).
I understand English and Urdu, and I'll reply by voice when you talk to me by voice.

> what's on my screen right now?
> is the laptop plugged in and how much battery is left?
> open chrome and go to gmail, then screenshot it
> WhatsApp par Ali ko bhejo: main 10 min mein aa raha hoon
> find every invoice PDF in Documents from this year and send me the biggest one
> what's using all my RAM? close the worst offender

**Commands**
`/new` - forget this conversation and start fresh
`/stop` - cancel whatever I'm doing right now
`/shot` - instant screenshot, no thinking
`/status` - instant system health
`/voice on` / `/voice off` / `/voice auto` - control voice replies
`/help` - this message"""

def _normalize_urdu_for_display(text, language):
    """Clean Urdu STT text for the Discord 'heard' display only.

    The original transcription is never modified and is still sent to
    the agent. If normalization fails, return the original text.
    """
    if not text or not str(language).startswith("ur"):
        return text

    api_key = CONFIG.groq_api_key
    if not api_key:
        return text

    model = os.getenv(
        "GROQ_NORMALIZER_MODEL",
        "llama-3.3-70b-versatile",
    )

    prompt = """You are an Urdu speech-transcription editor.

Correct ONLY obvious speech-to-text errors in the following Urdu
transcription.

Rules:
- Output ONLY the corrected transcription.
- Keep the original meaning exactly.
- Do NOT translate it.
- Do NOT summarize it.
- Do NOT add information.
- Write natural Pakistani Urdu in Urdu script.
- Correct obvious Urdu spelling, spacing, and punctuation errors.
- Keep English names, product names, app names, and technical terms
  when they are naturally spoken in English.
- Keep the name ORBIT as "ORBIT".
- Do not convert Urdu into Hindi/Devanagari.
- Do not invent words that were not reasonably present in the
  transcription.

Raw transcription:
""" + str(text).strip()

    try:
        import requests

        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You correct Urdu speech-to-text transcripts. "
                            "Preserve meaning exactly and output only the "
                            "corrected Urdu transcription."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                "temperature": 0,
                "max_tokens": 300,
            },
            timeout=10,
        )

        if response.status_code != 200:
            print(
                f"[voice] Urdu normalizer {response.status_code}: "
                f"{response.text[:200]}"
            )
            return text

        payload = response.json()
        cleaned = (
            payload.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

        return cleaned or text

    except Exception as exc:  # noqa: BLE001
        print(f"[voice] Urdu normalizer failed ({exc})")
        return text

def chunks(text, size):
    """Split text for Discord's 2000-character limit, preferring line breaks."""
    text = text.rstrip()
    while text:
        if len(text) <= size:
            yield text
            return
        cut = text.rfind("\n", 0, size)
        if cut < size // 3:
            cut = size
        yield text[:cut]
        text = text[cut:].lstrip("\n")


class Channel:
    """What the Brain is allowed to do to a Discord channel."""

    def __init__(self, channel, user_id):
        self.channel = channel
        self.user_id = user_id
        self.last_spoken = ""      # last substantive text, used for the voice reply
        self.spoke = False         # set True if the `speak` tool already sent a voice message

    async def send_text(self, text):
        text = str(text)
        if text.strip():
            self.last_spoken = text
        for part in chunks(text, CONFIG.discord_msg_limit):
            try:
                await self.channel.send(part)
            except discord.HTTPException as exc:
                print(f"[discord] send failed: {exc}", file=sys.stderr)

    async def note(self, text):
        try:
            await self.channel.send(f"-# ⚙️ {str(text)[:400]}")
        except discord.HTTPException:
            pass

    async def send_file(self, path, caption=None):
        target = Path(path)
        if not target.exists():
            return
        try:
            await self.channel.send(
                content=(caption or None),
                file=discord.File(str(target), filename=target.name),
            )
        except discord.HTTPException as exc:
            await self.send_text(f"Couldn't upload `{target.name}`: {exc}")

    async def confirm(self, tool_name, reason, detail):
        view = ConfirmView(self.user_id)
        embed = discord.Embed(
            title="Confirm before I run this",
            description=f"**{tool_name}** — {reason}",
            colour=discord.Colour.orange(),
        )
        embed.add_field(name="What will run", value=f"```\n{detail[:1000]}\n```", inline=False)
        embed.set_footer(text="Auto-cancels in 3 minutes if you don't answer.")
        try:
            message = await self.channel.send(embed=embed, view=view)
        except discord.HTTPException:
            return False

        approved = await view.wait_for_answer()
        try:
            await message.edit(
                embed=embed.set_footer(text="✅ Approved" if approved else "❌ Cancelled"),
                view=None,
            )
        except discord.HTTPException:
            pass
        return approved


class ConfirmView(discord.ui.View):
    def __init__(self, user_id, timeout=180):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.answer = None
        self._done = asyncio.Event()

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Not your agent.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Run it", style=discord.ButtonStyle.danger)
    async def approve(self, interaction, button):
        self.answer = True
        await interaction.response.defer()
        self._done.set()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def reject(self, interaction, button):
        self.answer = False
        await interaction.response.defer()
        self._done.set()
        self.stop()

    async def on_timeout(self):
        self._done.set()

    async def wait_for_answer(self):
        await self._done.wait()
        return bool(self.answer)


class LapPilot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.brain, self.brain_label = _make_brain()
        self.jobs = {}
        self.voice_mode = {}   # per-channel override of CONFIG.voice_replies
        self._net_monitor_started = False   # on_ready fires again on every reconnect

    async def on_ready(self):
        try:
            (CONFIG.runtime_dir / "status.txt").write_text(
                f"ONLINE as {self.user} (id {self.user.id})\n"
                f"allowed_users={sorted(CONFIG.allowed_users)}\n"
                f"guilds={[g.name for g in self.guilds]}\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001
            pass
        print(f"\n  {CONFIG.agent_name} is online as {self.user}")
        print(f"  brain: {self.brain_label}")
        print(f"  model: {CONFIG.subscription_model or 'default'}" if effective_brain() == "subscription" else f"  model: {CONFIG.model}")
        print(f"  confirmations: {'ON' if CONFIG.confirm_risky else 'OFF - full autonomy'}")
        print(f"  voice replies: {CONFIG.voice_replies}")
        print(f"  authorised user IDs: {', '.join(str(i) for i in CONFIG.allowed_users)}")
        print("  DM the bot from your phone to start.\n")

        # Warm both slow paths in the background so your FIRST message is fast.
        asyncio.create_task(asyncio.to_thread(voice.warmup))
        if hasattr(self.brain, "prewarm"):
            asyncio.create_task(self.brain.prewarm())
        asyncio.create_task(self._announce_back())
        if not self._net_monitor_started:
            self._net_monitor_started = True
            asyncio.create_task(self._watch_network())

    async def _watch_network(self):
        """Keep the laptop online without anyone touching it.

        Discord's own reconnect handles brief blips. This handles the real problem:
        the router died in a power cut and Windows never rejoins the Wi-Fi. We watch the
        charger - when it starts charging again, the electricity (and router) are back,
        so that's the moment to push hard on reconnecting.
        """
        # A profile set to "connect manually" is never rejoined by Windows on its own -
        # the single most common reason a laptop sits offline after a router reboot.
        try:
            await asyncio.to_thread(netrecover.ensure_auto_connect, print)
        except Exception as exc:  # noqa: BLE001
            print(f"[net] auto-connect check failed: {exc}")

        was_plugged = netrecover.power_plugged()
        while not self.is_closed():
            try:
                await asyncio.sleep(30)
                plugged = netrecover.power_plugged()
                power_returned = bool(plugged) and was_plugged is False
                was_plugged = plugged

                if power_returned:
                    print("[net] charger reconnected - checking the network")

                online = await asyncio.to_thread(netrecover.internet_up)
                if online and not power_returned:
                    continue
                if online:
                    continue

                # Offline: actively rejoin Wi-Fi (runs in a thread, netsh is blocking).
                await asyncio.to_thread(netrecover.repair)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - never let the monitor die
                print(f"[net] monitor error: {exc}")

    async def _announce_back(self):
        """Tell the owner she's live again after a reboot or outage.

        Throttled so a crash-loop can't spam, and silent on the very first install.
        """
        stamp = CONFIG.runtime_dir / "last_online.txt"
        now = time.time()
        try:
            last = float(stamp.read_text(encoding="utf-8").strip())
        except Exception:  # noqa: BLE001
            last = 0.0
        try:
            stamp.write_text(str(now), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

        # Only speak up if she'd been gone a while (a real outage/reboot, not a quick restart).
        if last and (now - last) < 300:
            return

        gap = ""
        if last:
            minutes = int((now - last) // 60)
            gap = f" (was offline about {minutes // 60}h {minutes % 60}m)" if minutes >= 60 else f" (was offline about {minutes} min)"

        try:
            _, ssid = await asyncio.to_thread(netrecover.wlan_state)
        except Exception:  # noqa: BLE001
            ssid = ""
        via = f" via **{ssid}**" if ssid else ""

        for guild in self.guilds:
            for channel in guild.text_channels:
                try:
                    await channel.send(
                        f"✅ {CONFIG.agent_name} is back online{gap}{via} — ready when you are."
                    )
                    return
                except discord.HTTPException:
                    continue

    async def on_message(self, message):
        if message.author.bot:
            return
        # diagnostic breadcrumb: record who last messaged, so a wrong allowlist is easy to spot
        try:
            allowed = message.author.id in CONFIG.allowed_users
            (CONFIG.runtime_dir / "last_sender.txt").write_text(
                f"id={message.author.id}\nname={message.author}\nallowed={allowed}\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001
            pass
        if message.author.id not in CONFIG.allowed_users:
            if isinstance(message.channel, discord.DMChannel):
                await message.channel.send("You are not authorised to control this machine.")
            print(f"[blocked] {message.author} ({message.author.id}): {message.content[:80]}")
            return

        text = (message.content or "").strip()
        key = message.channel.id
        chan = Channel(message.channel, message.author.id)

        if text.startswith("/"):
            if await self._command(text, key, chan, message):
                return

        # Separate voice notes from other attachments.
        audio = [a for a in message.attachments if self._is_audio(a)]
        other = [a for a in message.attachments if not self._is_audio(a)]

        came_by_voice = False
        if audio:
            async with message.channel.typing():
                heard, lang = await self._listen(audio[0], chan)

            if heard:
                # Tell the model it arrived as speech, so it replies by voice
                # in the same language.
                spoken_lang = "Urdu" if str(lang).startswith("ur") else (
                    "Hindi/Urdu" if str(lang).startswith("hi") else "English"
                )

                # IMPORTANT:
                # Send the original transcription to Claude unchanged.
                text = (
                    f"{text}\n{heard}".strip()
                    + f"\n\n[This came in as a VOICE NOTE spoken in {spoken_lang}. "
                    f"Reply using the `speak` tool in the same language, plus a short text line.]"
                )

                came_by_voice = True

                # Clean Urdu only for the Discord "heard" display.
                # The raw transcription above is still sent to Claude.
                display_heard = await asyncio.to_thread(
                    _normalize_urdu_for_display,
                    heard,
                    lang,
                )

                await chan.send_text(
                    f"-# 🎙️ heard: {display_heard[:300]}"
                )

            elif not text:
                await chan.send_text(
                    "I got your voice note but couldn't make out any words. "
                    "Try speaking a bit longer, or type it."
                )
                return

        if not text and not other:
            return

        if other:
            names = ", ".join(a.filename for a in other)
            text = f"{text}\n\n(The user attached: {names} - these are on their phone, not the laptop.)"

        voice.SPOKE_CHANNELS.discard(key)   # fresh turn: no voice sent yet

        async with message.channel.typing():
            job = asyncio.create_task(self.brain.handle(key, text, chan))
            self.jobs[key] = job
            try:
                await job
            except asyncio.CancelledError:
                pass
            finally:
                self.jobs.pop(key, None)

        await self._maybe_speak(key, came_by_voice, chan)

    @staticmethod
    def _is_audio(attachment):
        ctype = (attachment.content_type or "").lower()
        if ctype.startswith("audio") or "ogg" in ctype or "opus" in ctype or "webm" in ctype:
            return True
        name = (attachment.filename or "").lower()
        if name.endswith(AUDIO_EXTS):
            return True
        # Discord voice messages are named voice-message.ogg and carry a waveform
        if getattr(attachment, "waveform", None):
            return True
        return "voice-message" in name

    async def _listen(self, attachment, chan):
        """Download a voice note and transcribe it. Returns (text, language)."""
        if not voice.available():
            await chan.send_text(
                "Voice recognition isn't installed. Run `install.bat` again to add it, "
                "or just type your command."
            )
            return "", ""
        path = CONFIG.voice_dir / f"in-{int(time.time() * 1000)}-{attachment.filename}"
        try:
            await attachment.save(str(path))
        except Exception as exc:  # noqa: BLE001
            await chan.send_text(f"Couldn't download the voice note: {exc}")
            return "", ""
        try:
            return await asyncio.to_thread(voice.transcribe, path)
        finally:
            try:
                path.unlink()
            except OSError:
                pass

    async def _maybe_speak(self, key, came_by_voice, chan):
        # The `speak` tool already sent audio this turn -> never send a second clip.
        # Checked by channel ID because the SDK may hand tools a stale Channel object.
        spoke_via_tool = key in voice.SPOKE_CHANNELS
        voice.SPOKE_CHANNELS.discard(key)
        if spoke_via_tool or getattr(chan, "spoke", False):
            return
        mode = self.voice_mode.get(key, CONFIG.voice_replies)
        if mode == "never" or mode == "off":
            return
        if mode in ("auto", "") and not came_by_voice:
            return
        # mode == 'always'/'on', or 'auto' with a voice input
        spoken = chan.last_spoken.strip()
        if not spoken:
            return
        clip = await voice.synthesize(spoken)
        if clip:
            await chan.send_file(clip, None)

    async def _command(self, text, key, chan, message):
        command = text.split()[0].lower()

        if command in ("/help", "/start"):
            await chan.send_text(HELP.format(name=CONFIG.agent_name))
            return True

        if command == "/voice":
            arg = (text.split() + [""])[1].lower()
            if arg in ("on", "always"):
                self.voice_mode[key] = "always"
                await chan.send_text("Voice replies: ON - I'll speak every reply.")
            elif arg in ("off", "never"):
                self.voice_mode[key] = "never"
                await chan.send_text("Voice replies: OFF - text only.")
            elif arg in ("auto", ""):
                self.voice_mode[key] = "auto"
                await chan.send_text("Voice replies: AUTO - I'll speak when you talk to me by voice.")
            else:
                await chan.send_text("Use `/voice on`, `/voice off`, or `/voice auto`.")
            return True

        if command == "/new":
            self.brain.reset(key)
            await chan.send_text("Fresh start - I've forgotten the previous conversation.")
            return True

        if command == "/stop":
            job = self.jobs.get(key)
            if job and not job.done():
                job.cancel()
                await chan.send_text("Stopping.")
            else:
                await chan.send_text("Nothing running.")
            return True

        if command == "/shot":
            from .tools.screen import screenshot

            result = await asyncio.to_thread(screenshot)
            for path in result.get("images", []):
                await chan.send_file(path)
            return True

        if command == "/status":
            from .tools.system import system_status

            result = await asyncio.to_thread(system_status)
            await chan.send_text(f"```\n{result['text']}\n```")
            return True

        return False


def _sleep(seconds):
    import time as _time

    _time.sleep(seconds)


def _internet_up(timeout=4):
    return netrecover.internet_up(timeout)


def _wait_for_network():
    """Block until online, actively rejoining Wi-Fi rather than just waiting."""
    netrecover.wait_until_online()


_INSTANCE_GUARD = None


def _single_instance():
    """Windows named mutex so only ONE ORBIT ever runs (two would fight over Discord)."""
    global _INSTANCE_GUARD
    try:
        import ctypes

        handle = ctypes.windll.kernel32.CreateMutexW(None, False, "LapPilotORBITSingleton")
        already = ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
        _INSTANCE_GUARD = handle  # keep the handle alive for the process lifetime
        return not already
    except Exception:  # noqa: BLE001 - non-Windows or ctypes missing: don't block startup
        return True


def run():
    if not _single_instance():
        print("\n  ORBIT is already running - this extra copy will exit.\n")
        sys.exit(3)  # run.bat treats 3 as 'do not restart'

    problems = validate()
    if problems:
        print("\n  Setup incomplete:\n")
        for item in problems:
            print(f"   - {item}")
        print(f"\n  Edit {CONFIG.runtime_dir.parent / '.env'} and run again.\n")
        sys.exit(1)

    import logging

    handler = logging.FileHandler(CONFIG.runtime_dir / "discord.log", mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    _wait_for_network()

    # Never give up on a network problem. The laptop may boot before the router does, or the
    # line may drop for hours during a power cut - she just keeps retrying until it returns.
    delay = 5
    while True:
        client = LapPilot()
        try:
            client.run(CONFIG.discord_token, log_handler=handler, log_level=logging.INFO)
            return  # clean shutdown (Ctrl+C / window closed)
        except discord.LoginFailure:
            print("\n  Discord rejected the token. Check DISCORD_BOT_TOKEN in .env.\n")
            sys.exit(1)
        except discord.PrivilegedIntentsRequired:
            print(
                "\n  Discord needs the MESSAGE CONTENT INTENT.\n"
                "  Go to https://discord.com/developers/applications -> your app -> Bot\n"
                "  -> Privileged Gateway Intents -> turn ON 'Message Content Intent' -> Save.\n"
            )
            sys.exit(1)
        except KeyboardInterrupt:
            return
        except Exception as exc:  # noqa: BLE001 - network/gateway trouble
            print(f"  Connection lost ({type(exc).__name__}: {exc}). Retrying in {delay}s...")
            _sleep(delay)
            _wait_for_network()
            delay = min(delay * 2, 60)   # back off, but never longer than a minute


if __name__ == "__main__":
    run()
