"""CLI entrypoint for Step 12 Telegram reaction feedback capture."""

import json

try:
    from adas.telegram.feedback_capture import ReactionFeedbackCapture
    from adas.config import DELIVERY_LOG, FEEDBACK_FILE
except ModuleNotFoundError:
    from telegram.feedback_capture import ReactionFeedbackCapture  # type: ignore
    from config import DELIVERY_LOG, FEEDBACK_FILE  # type: ignore


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Poll Telegram for reactions on digest messages and write matching "
            "feedback entries to feedback.json."
        )
    )
    parser.add_argument(
        "--delivery-log",
        default=DELIVERY_LOG,
        help="Path to delivery_log.json produced by telegram_digest.py",
    )
    parser.add_argument(
        "--feedback",
        default=FEEDBACK_FILE,
        help="Path to feedback.json to append results into",
    )
    parser.add_argument(
        "--offset-file",
        default=None,
        help="Path to persist the last processed Telegram update_id (default: next to delivery log)",
    )
    args = parser.parse_args()

    from adas.telegram.delivery_log import DeliveryLogStore

    capture = ReactionFeedbackCapture(
        delivery_log_store=DeliveryLogStore(args.delivery_log),
    )
    result = capture.capture(
        offset_path=args.offset_file,
        feedback_path=args.feedback,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
