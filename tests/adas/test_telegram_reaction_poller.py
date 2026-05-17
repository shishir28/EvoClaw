"""Tests for TelegramReactionPoller."""

from __future__ import annotations

import pytest
import requests

from adas.telegram.reaction_poller import ReactionUpdate, TelegramReactionPoller


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

class _Response:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


class _Session:
    def __init__(self, response: _Response):
        self.response = response
        self.calls: list[dict] = []

    def get(self, url: str, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.response


def _ok_payload(*reactions: dict) -> dict:
    """Build a successful getUpdates payload containing the given reaction updates."""
    return {"ok": True, "result": list(reactions)}


def _reaction_update(
    update_id: int = 1001,
    message_id: int = 42,
    chat_id: int = 12345,
    new_emojis: list[str] | None = None,
    old_emojis: list[str] | None = None,
) -> dict:
    return {
        "update_id": update_id,
        "message_reaction": {
            "message_id": message_id,
            "chat": {"id": chat_id},
            "user": {"id": 999},
            "date": 1700000000,
            "new_reaction": [{"type": "emoji", "emoji": e} for e in (new_emojis or [])],
            "old_reaction": [{"type": "emoji", "emoji": e} for e in (old_emojis or [])],
        },
    }


def _poller(response: _Response) -> TelegramReactionPoller:
    return TelegramReactionPoller(bot_token="test-token", session=_Session(response))


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_missing_token_raises(self):
        with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
            TelegramReactionPoller(bot_token="")

    def test_default_session_created_when_not_injected(self):
        poller = TelegramReactionPoller(bot_token="tok")
        assert poller.session is not None


# ---------------------------------------------------------------------------
# Successful polls
# ---------------------------------------------------------------------------

class TestPollSuccess:
    def test_returns_empty_list_when_no_updates(self):
        poller = _poller(_Response(200, {"ok": True, "result": []}))
        assert poller.poll() == []

    def test_parses_single_reaction_update(self):
        raw = _reaction_update(update_id=1001, message_id=42, chat_id=12345,
                               new_emojis=["👍"])
        poller = _poller(_Response(200, _ok_payload(raw)))

        updates = poller.poll()

        assert len(updates) == 1
        u = updates[0]
        assert u.update_id == 1001
        assert u.message_id == 42
        assert u.chat_id == "12345"
        assert u.new_reactions == ["👍"]
        assert u.old_reactions == []

    def test_parses_old_and_new_reactions(self):
        raw = _reaction_update(new_emojis=["👍"], old_emojis=["👎"])
        poller = _poller(_Response(200, _ok_payload(raw)))

        u = poller.poll()[0]

        assert u.new_reactions == ["👍"]
        assert u.old_reactions == ["👎"]

    def test_skips_non_emoji_reaction_types(self):
        raw = {
            "update_id": 1002,
            "message_reaction": {
                "message_id": 7,
                "chat": {"id": 1},
                "date": 0,
                "new_reaction": [
                    {"type": "custom_emoji", "custom_emoji_id": "abc"},
                    {"type": "emoji", "emoji": "🔥"},
                ],
                "old_reaction": [],
            },
        }
        poller = _poller(_Response(200, _ok_payload(raw)))

        u = poller.poll()[0]

        assert u.new_reactions == ["🔥"]

    def test_skips_non_reaction_update_types(self):
        message_update = {"update_id": 1, "message": {"text": "hello"}}
        reaction_update = _reaction_update(update_id=2, new_emojis=["👍"])
        poller = _poller(_Response(200, _ok_payload(message_update, reaction_update)))

        updates = poller.poll()

        assert len(updates) == 1
        assert updates[0].update_id == 2

    def test_multiple_reaction_updates_returned_in_order(self):
        raw1 = _reaction_update(update_id=10, message_id=1, new_emojis=["👍"])
        raw2 = _reaction_update(update_id=11, message_id=2, new_emojis=["👎"])
        poller = _poller(_Response(200, _ok_payload(raw1, raw2)))

        updates = poller.poll()

        assert [u.update_id for u in updates] == [10, 11]

    def test_offset_passed_in_params(self):
        session = _Session(_Response(200, {"ok": True, "result": []}))
        poller = TelegramReactionPoller(bot_token="tok", session=session)

        poller.poll(offset=500)

        assert session.calls[0]["params"]["offset"] == 500

    def test_no_offset_when_none(self):
        session = _Session(_Response(200, {"ok": True, "result": []}))
        poller = TelegramReactionPoller(bot_token="tok", session=session)

        poller.poll(offset=None)

        assert "offset" not in session.calls[0]["params"]

    def test_correct_endpoint_called(self):
        session = _Session(_Response(200, {"ok": True, "result": []}))
        poller = TelegramReactionPoller(bot_token="mytoken", session=session)

        poller.poll()

        assert "mytoken" in session.calls[0]["url"]
        assert "getUpdates" in session.calls[0]["url"]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestPollErrors:
    def test_http_error_raises(self):
        poller = _poller(_Response(403, text="Forbidden"))
        with pytest.raises(RuntimeError, match="HTTP 403"):
            poller.poll()

    def test_non_ok_telegram_response_raises(self):
        poller = _poller(_Response(200, {"ok": False, "description": "Unauthorized"}))
        with pytest.raises(RuntimeError, match="Unauthorized"):
            poller.poll()

    def test_request_exception_wrapped_as_runtime_error(self):
        class _FailSession:
            def get(self, *args, **kwargs):
                raise requests.ConnectionError("network down")

        poller = TelegramReactionPoller(bot_token="tok", session=_FailSession())
        with pytest.raises(RuntimeError, match="getUpdates request failed"):
            poller.poll()
