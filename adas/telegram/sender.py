"""Telegram Bot API sender used by the production digest flow."""

from __future__ import annotations

from dataclasses import dataclass

import requests

from adas.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from adas.telegram.models import TelegramSendReceipt
from adas.utils.retry import RETRYABLE_HTTP_STATUSES, call_with_retry

_TELEGRAM_API_HOST = "api.telegram.org"


@dataclass(slots=True)
class TelegramSender:
    """Thin wrapper over Telegram's sendMessage endpoint."""

    bot_token: str = TELEGRAM_BOT_TOKEN
    chat_id: str = TELEGRAM_CHAT_ID
    timeout_seconds: int = 30
    session: requests.sessions.Session | None = None

    def __post_init__(self) -> None:
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required to send Telegram messages.")
        if not self.chat_id:
            raise ValueError("TELEGRAM_CHAT_ID is required to send Telegram messages.")
        if self.session is None:
            self.session = requests.Session()

    @property
    def endpoint(self) -> str:
        return f"https://{_TELEGRAM_API_HOST}/bot{self.bot_token}/sendMessage"

    def send_message(self, text: str) -> TelegramSendReceipt:
        response = self._post(text)
        payload = self._parse_json(response)
        if not payload.get("ok"):
            raise RuntimeError(
                "Telegram sendMessage failed: "
                + str(payload.get("description", "unknown Telegram API error"))
            )
        result = payload.get("result")
        if not isinstance(result, dict) or result.get("message_id") is None:
            raise RuntimeError("Telegram sendMessage response did not include message metadata.")
        return TelegramSendReceipt(
            chat_id=self.chat_id,
            message_id=int(result["message_id"]),
        )

    def _post(self, text: str) -> requests.Response:
        def _attempt() -> requests.Response:
            try:
                response = self.session.post(
                    self.endpoint,
                    json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "disable_web_page_preview": False,
                    },
                    timeout=self.timeout_seconds,
                )
            except requests.RequestException as exc:
                raise RuntimeError(f"Telegram sendMessage request failed: {exc}") from exc
            if response.status_code in RETRYABLE_HTTP_STATUSES:
                raise RuntimeError(
                    f"Telegram sendMessage returned HTTP {response.status_code}: {response.text}"
                )
            if response.status_code != 200:
                raise RuntimeError(
                    f"Telegram sendMessage returned HTTP {response.status_code}: {response.text}"
                )
            return response

        return call_with_retry(
            _attempt,
            retryable_exceptions=(RuntimeError,),
        )

    @staticmethod
    def _parse_json(response: requests.Response) -> dict[str, object]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Telegram sendMessage returned non-JSON output.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Telegram sendMessage returned an unexpected payload shape.")
        return payload
