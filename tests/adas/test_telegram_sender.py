"""Tests for the Telegram Bot API sender."""

from __future__ import annotations

import pytest

from adas.telegram.sender import TelegramSender


class _StubResponse:
    def __init__(self, status_code: int, payload: dict[str, object] | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict[str, object]:
        return self._payload


class _StubSession:
    def __init__(self, response: _StubResponse):
        self.response = response
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, json: dict[str, object], timeout: int):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return self.response


def test_send_message_returns_message_metadata():
    session = _StubSession(
        _StubResponse(
            200,
            payload={"ok": True, "result": {"message_id": 321}},
        )
    )
    sender = TelegramSender(bot_token="token", chat_id="chat-1", session=session)

    receipt = sender.send_message("hello")

    assert receipt.chat_id == "chat-1"
    assert receipt.message_id == 321
    assert session.calls[0]["json"]["chat_id"] == "chat-1"


def test_missing_bot_token_raises():
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        TelegramSender(bot_token="", chat_id="chat-1")


def test_http_error_raises_runtime_error():
    session = _StubSession(_StubResponse(500, text="boom"))
    sender = TelegramSender(bot_token="token", chat_id="chat-1", session=session)

    with pytest.raises(RuntimeError, match="HTTP 500"):
        sender.send_message("hello")
