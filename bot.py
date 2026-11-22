"""This file is responsible for handling the connection to Reddit and maintenance of the bot itself.  All comment bodies are piped to parser.py."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable

from errors import RangeInputError
from parser import make_reply
from poker import get_equity

LOGGER = logging.getLogger(__name__)

# Size-based log rotation
LOG_FILE_NAME = "bot.log"
LOG_FILE_MAX_BYTES = 5 * 1024 * 1024  # 5 MiB per file
LOG_FILE_BACKUP_COUNT = 5


# Handle an individual Reddit inbox item.
def process_item(item, evaluator: Callable = get_equity) -> None:
    item_id = getattr(item, "id", "unknown")
    stage = "generating reply"
    try:
        input_error = None
        try:
            reply = make_reply(item.body, evaluator)
        except RangeInputError as exc:
            reply = str(exc)
            input_error = exc.code.name

        if reply is not None:
            stage = "posting reply"
            item.reply(reply)
            if input_error is None:
                LOGGER.info("Replied to inbox item %s (equity result)", item_id)
            else:
                LOGGER.info("Replied to inbox item %s (input error: %s)", item_id, input_error)

        stage = "marking item read"
        item.mark_read()
    except Exception:
        LOGGER.exception("Failed to process inbox item %s during %s", item_id, stage)
        raise


def configure_logging() -> None:
    """Log to the console and to a size-based rotating file."""
    log_path = Path(__file__).resolve().with_name(LOG_FILE_NAME)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(
                log_path,
                maxBytes=LOG_FILE_MAX_BYTES,
                backupCount=LOG_FILE_BACKUP_COUNT,
                encoding="utf-8",
            ),
        ],
        force=True,
    )


# Connect to Reddit and process only new inbox items.  Does not process items from when the bot was offline.
def main() -> None:
    configure_logging()
    try:
        import praw
        reddit = praw.Reddit("equity_bot")
        LOGGER.info("Connected to Reddit as u/%s", reddit.user.me())
        for item in reddit.inbox.stream(skip_existing=True):
            try:
                process_item(item)
            except Exception:
                # process_item already logged the failure with its traceback.
                continue
    except Exception:
        LOGGER.exception("Reddit login or inbox stream failed")
        raise


if __name__ == "__main__":
    main()
