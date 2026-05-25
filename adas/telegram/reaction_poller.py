"""Poll Telegram getUpdates for message_reaction events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests

from adas.config import TELEGRAM_BOT_TOKEN
from adas.utils.retry import RETRYABLE_HTTP_STATUSES, call_with_retry


@dataclass(slots=True)
class ReactionUpdate:
    """One message_reaction update from Telegram."""

    update_id: int
    message_id: int
    chat_id: str
    new_reactions: list[str]
    old_reactions: list[str]
    date: int


@dataclass(slots=True)
class TelegramReactionPoller:
    """Thin wrapper over Telegram getUpdates for reaction events."""

    bot_token: str = TELEGRAM_BOT_TOKEN
    timeout_seconds: int = 30
    session: requests.sessions.Session | None = None

    def __post_init__(self) -> None:
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required.")
        if self.session is None:
            self.session = requests.Session()

    def poll(self, offset: int | None = None, limit: int = 100) -> list[ReactionUpdate]:
        """Return new reaction updates since offset, or all recent if offset is None."""
        params: dict[str, Any] = {
            "allowed_updates": ["message_reaction"],
            "limit": limit,
        }
        if offset is not None:
            params["offset"] = offset

        def _attempt() -> requests.Response:
            try:
                resp = self.session.get(
                    f"https://api.telegram.org/bot{self.bot_token}/getUpdates",
                    params=params,
                    timeout=self.timeout_seconds,
                )
            except requests.RequestException as exc:
                raise RuntimeError(f"getUpdates request failed: {exc}") from exc
            if resp.status_code in RETRYABLE_HTTP_STATUSES:
                raise RuntimeError(
                    f"getUpdates returned HTTP {resp.status_code}: {resp.text}"
                )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"getUpdates returned HTTP {resp.status_code}: {resp.text}"
                )
            return resp

        response = call_with_retry(_attempt, retryable_exceptions=(RuntimeError,))

        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(
                "getUpdates failed: " + str(payload.get("description", "unknown error"))
            )

        updates: list[ReactionUpdate] = []
        for raw in payload.get("result", []):
            reaction = raw.get("message_reaction")
            if not reaction:
                continue
            updates.append(ReactionUpdate(
                update_id=int(raw["update_id"]),
                message_id=int(reaction["message_id"]),
                chat_id=str(reaction["chat"]["id"]),
                new_reactions=[
                    r["emoji"]
                    for r in reaction.get("new_reaction", [])
                    if r.get("type") == "emoji"
                ],
                old_reactions=[
                    r["emoji"]
                    for r in reaction.get("old_reaction", [])
                    if r.get("type") == "emoji"
                ],
                date=int(reaction.get("date", 0)),
            ))
        return updates
