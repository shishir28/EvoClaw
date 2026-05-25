"""CLI entrypoint and compatibility wrapper for Step 11 Telegram digest delivery."""

from adas.telegram.service import main, send_digest


if __name__ == "__main__":
    main()
