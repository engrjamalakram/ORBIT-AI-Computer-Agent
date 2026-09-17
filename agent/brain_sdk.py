"""Subscription brain: runs ORBIT on your Claude Code login instead of a paid API key.

Uses the official Claude Agent SDK, which authenticates through the Claude Code CLI you're already
signed into. Same models as the API (Opus etc.) - no quality loss - but billed to your Claude
subscription rather than per-token API credits.

Our laptop tools are exposed to the SDK as an in-process MCP server, so screenshots, shell,
WhatsApp control and everything else work exactly the same. Screenshots are handed to the model as
vision AND pushed to Discord, via a contextvar that carries the active channel into each tool call
(verified to propagate correctly).
"""

import asyncio
import base64
import contextvars
import traceback
from pathlib import Path

import claude_agent_sdk as sdk

from .brain import SYSTEM_PROMPT
from .config import CONFIG
from .security import execute as execute_tool
from .tools import load_all

SCHEMAS, HANDLERS = load_all()

# Where tool output (screenshots, files) gets sent.
#
# A contextvar alone is NOT enough: the SDK captures a context snapshot when the session
# connects and runs tool handlers under it. Because we pre-warm the session before any
# message arrives, that snapshot has no channel - so tools saw None and silently dropped
# every screenshot. _ACTIVE is the authoritative current channel, updated per turn.
_CHAN = contextvars.ContextVar("lappilot_channel", default=None)
_ACTIVE = None


def _current_channel():
    return _ACTIVE if _ACTIVE is not None else _CHAN.get()


def _clip(text, limit):
    text = text or ""
    return text if len(text) <= limit else text[:limit] + f"\n... [truncated, {len(text)} chars total]"


def _encode(path):
    return base64.standard_b64encode(Path(path).read_bytes()).decode("ascii")


def _build_tool(schema):
    name = schema["name"]
    handler = HANDLERS[name]

    @sdk.tool(name, schema["description"], schema["input_schema"])
    async def _run(args, _handler=handler, _name=name):
        chan = _current_channel()
        # Every Discord message costs a round trip and counts against rate limits. Announcing
        # every click/wait/screenshot made long jobs crawl, so this is opt-in only.
        if chan is not None and CONFIG.show_tool_calls:
            try:
                await chan.note(f"`{_name}`")
            except Exception:  # noqa: BLE001
                pass

        async def confirm(tool_name, reason, detail):
            if not CONFIG.confirm_risky:
                return True
            if chan is None:
                return False
            return await chan.confirm(tool_name, reason, detail)

        try:
            result, approved = await execute_tool(_name, args or {}, _handler, confirm)
            if not approved:
                return {
                    "content": [{"type": "text", "text": result.get("text", "DENIED")}],
                    "isError": True,
                }
        except TypeError as exc:
            return {"content": [{"type": "text", "text": f"Bad arguments for {_name}: {exc}"}], "isError": True}
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return {"content": [{"type": "text", "text": f"{_name} raised {type(exc).__name__}: {exc}"}], "isError": True}

        content = [{"type": "text", "text": _clip(result.get("text") or "(no output)", CONFIG.max_tool_output)}]
        captions = result.get("captions") or []
        # Images always go to the model so it can see the screen. They only go to Discord
        # when the tool says so - uploading every intermediate screenshot was the single
        # biggest slowdown on long jobs.
        show = bool(result.get("show"))

        for index, image_path in enumerate(result.get("images") or []):
            try:
                content.append({"type": "image", "data": _encode(image_path), "mimeType": "image/jpeg"})
            except Exception as exc:  # noqa: BLE001
                content.append({"type": "text", "text": f"(image attach failed: {exc})"})
            if chan is not None and show:
                await chan.send_file(image_path, captions[index] if index < len(captions) else None)

        for index, file_path in enumerate(result.get("files") or []):
            if chan is not None:
                await chan.send_file(file_path, captions[index] if index < len(captions) else None)

        if _name == "speak" and chan is not None:
            chan.spoke = True  # tell main not to auto-speak a duplicate
            try:
                from .voice import SPOKE_CHANNELS

                SPOKE_CHANNELS.add(chan.channel.id)
            except Exception:  # noqa: BLE001
                pass

        return {"content": content}

    return _run


_TOOLS = [_build_tool(schema) for schema in SCHEMAS]
_SERVER = sdk.create_sdk_mcp_server("laptop", "1.0.0", _TOOLS)
_ALLOWED = [f"mcp__laptop__{schema['name']}" for schema in SCHEMAS]


def _options():
    kwargs = dict(
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"laptop": _SERVER},
        allowed_tools=_ALLOWED,
        permission_mode="bypassPermissions",
        max_turns=CONFIG.max_iterations,
        # keep ORBIT on our tools, not Claude Code's own file/bash tools
        setting_sources=[],
    )
    if CONFIG.subscription_model:
        kwargs["model"] = CONFIG.subscription_model
    return sdk.ClaudeAgentOptions(**kwargs)


class SdkBrain:
    """Same surface as brain.Brain, backed by the Claude subscription."""

    def __init__(self):
        self.clients = {}   # channel id -> connected ClaudeSDKClient (keeps conversation memory)
        self.busy = set()
        self._spare = None  # pre-connected client, so the first message doesn't pay startup cost

    async def prewarm(self):
        """Connect a session in advance. First reply drops from ~17s to ~3s."""
        if self._spare is not None or self.clients:
            return
        try:
            client = sdk.ClaudeSDKClient(options=_options())
            await client.connect()
            self._spare = client
            print("[brain] Claude session pre-warmed")
        except Exception as exc:  # noqa: BLE001
            print(f"[brain] prewarm skipped: {exc}")

    def reset(self, key):
        client = self.clients.pop(key, None)
        if client is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no loop (interpreter shutting down) - nothing to schedule
        loop.create_task(self._disconnect(client))

    async def aclose(self):
        """Disconnect every live session - call on shutdown."""
        clients = list(self.clients.values())
        self.clients.clear()
        for client in clients:
            await self._disconnect(client)

    @staticmethod
    async def _disconnect(client):
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    async def _client(self, key):
        client = self.clients.get(key)
        if client is None:
            if self._spare is not None:      # use the pre-warmed session
                client, self._spare = self._spare, None
            else:
                client = sdk.ClaudeSDKClient(options=_options())
                await client.connect()
            self.clients[key] = client
        return client

    async def handle(self, key, user_text, chan):
        if key in self.busy:
            await chan.send_text("I'm still working on the previous instruction. Send `/stop` to cancel it.")
            return
        global _ACTIVE

        self.busy.add(key)
        token = _CHAN.set(chan)
        _ACTIVE = chan          # authoritative: survives the SDK's context snapshot
        try:
            client = await self._client(key)
            prompt = user_text
            rounds_left = max(0, CONFIG.auto_continue)

            while True:
                await client.query(prompt)

                spoke = False
                hit_limit = False
                async for message in client.receive_response():
                    if isinstance(message, sdk.AssistantMessage):
                        for block in message.content:
                            if isinstance(block, sdk.TextBlock) and block.text.strip():
                                spoke = True
                                await chan.send_text(block.text)
                    elif isinstance(message, sdk.ResultMessage):
                        subtype = str(getattr(message, "subtype", "") or "")
                        # The SDK stops silently once max_turns is reached. Long jobs used to
                        # die here with no message at all, hours into the work.
                        hit_limit = "max_turns" in subtype
                        if getattr(message, "is_error", False) and not hit_limit and not spoke:
                            await chan.send_text(
                                "I hit an error and couldn't finish that one. Try `/new` and rephrase."
                            )
                        break

                if not hit_limit:
                    return

                if rounds_left <= 0:
                    await chan.send_text(
                        f"I've done {CONFIG.max_iterations} steps and paused so this doesn't run "
                        f"forever. Say **continue** and I'll pick up where I left off."
                    )
                    return

                rounds_left -= 1
                await chan.send_text("-# still working, continuing…")
                prompt = ("Continue exactly where you stopped. Do not start over and do not "
                          "repeat work you have already finished.")
        except asyncio.CancelledError:
            self.reset(key)   # a half-consumed stream would corrupt the session
            await chan.send_text("Cancelled.")
            raise
        except sdk.CLINotFoundError:
            await chan.send_text(
                "The Claude Code CLI isn't available, so subscription mode can't run. Install it with "
                "`npm i -g @anthropic-ai/claude-code` and sign in, or add an ANTHROPIC_API_KEY to .env."
            )
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self.reset(key)
            await chan.send_text(f"Agent error: `{type(exc).__name__}: {exc}`")
        finally:
            self.busy.discard(key)
            _CHAN.reset(token)
            if _ACTIVE is chan:      # don't clobber a turn that started meanwhile
                _ACTIVE = None
