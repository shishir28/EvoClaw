"""CLI entrypoint and compatibility wrapper for Step 11 Telegram digest delivery."""

try:
    from adas.telegram.service import main, send_digest
except ModuleNotFoundError:
    from telegram.service import main, send_digest  # type: ignore


if __name__ == "__main__":
    main()
