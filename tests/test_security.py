import asyncio

from agent.security import classify, describe, execute


def test_powershell_always_requires_confirmation():
    assert classify("run_powershell", {"command": "Get-Process"})[0] is True


def test_sensitive_previews_redact_secrets():
    text = describe("wifi_add_network", {"ssid": "Home", "password": "super-secret"})
    assert "super-secret" not in text
    assert "REDACTED" in text


def test_denied_action_never_calls_handler():
    called = False

    def handler(**kwargs):
        nonlocal called
        called = True
        return {"text": "executed"}

    async def deny(*_args):
        return False

    result, approved = asyncio.run(execute("delete_path", {"path": "x"}, handler, deny))
    assert approved is False
    assert called is False
    assert result["text"].startswith("DENIED")


def test_approved_action_reaches_handler():
    called = False

    def handler(**kwargs):
        nonlocal called
        called = True
        return {"text": "executed"}

    async def approve(*_args):
        return True

    result, approved = asyncio.run(execute("delete_path", {"path": "x"}, handler, approve))
    assert approved is True
    assert called is True
    assert result["text"] == "executed"
