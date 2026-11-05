"""Reddit poker equity bot.

Examples: {AA,AKs} {kk} {b: As Kd Qc} {d: 2h}
Only checks the syntax of range strings; OMPEval handles the cards.
"""

import logging
import re
from dataclasses import dataclass
from math import isfinite
from typing import Callable

from errors import ErrorCode, RangeInputError, shorten
from poker import get_equity

LOGGER = logging.getLogger(__name__)
MAX_PLAYERS = 6
MAX_RANGE_CHARS = 1024
MAX_REQUEST_SECTIONS = 32

# These expressions describe the accepted *text*, not the possible deals.
EXACT_HAND = re.compile(r"[2-9TJQKA][shdc][2-9TJQKA][shdc]", re.I)
PAIR = re.compile(r"([2-9TJQKA])\1o?\+?", re.I)
OTHER_HAND = re.compile(r"([2-9TJQKA])([2-9TJQKA])([so])?\+?", re.I)
SECTION = re.compile(r"\s*([bd])\s*:\s*(.*?)\s*\Z", re.I | re.S)


@dataclass(frozen=True)
class EquityRequest:
    ranges: tuple[str, ...]
    board: str = ""
    dead: str = ""


def _compact(text: str) -> str:
    return "".join(text.split())


def _clean_range(text: str) -> str:
    # Remove irrelevant commas and whitespace, but preserve the author's case.
    return ",".join(token for token in _compact(text).split(",") if token)


def _validate_range(value: str) -> None:
    """Check notation only. No card overlap, blocker, or deal checking."""
    if not value or len(value) > MAX_RANGE_CHARS:
        raise RangeInputError(ErrorCode.INVALID_RANGE, value)

    for token in value.split(","):
        if EXACT_HAND.fullmatch(token) or PAIR.fullmatch(token):
            continue
        match = OTHER_HAND.fullmatch(token)
        if match and match.group(1).lower() != match.group(2).lower():
            continue
        raise RangeInputError(ErrorCode.INVALID_RANGE, value)


def parse_request(body: str) -> EquityRequest | None:
    """Extract range/board/dead sections without validating physical cards."""
    if "{" not in body:
        return None

    ranges: list[str] = []
    board: list[str] = []
    dead: list[str] = []
    cursor = 0
    sections = 0

    while (opening := body.find("{", cursor)) != -1:
        closing = body.find("}", opening + 1)
        if closing == -1 or "{" in body[opening + 1:closing]:
            raise RangeInputError(ErrorCode.MALFORMED_REQUEST)
        sections += 1
        if sections > MAX_REQUEST_SECTIONS:
            raise RangeInputError(ErrorCode.MALFORMED_REQUEST)

        content = body[opening + 1:closing]
        section = SECTION.fullmatch(content)
        if section:
            (board if section.group(1).lower() == "b" else dead).append(_compact(section.group(2)))
        else:
            value = _clean_range(content)
            _validate_range(value)
            ranges.append(value)
            if len(ranges) > MAX_PLAYERS:
                raise RangeInputError(ErrorCode.TOO_MANY_PLAYERS)
        cursor = closing + 1

    if not ranges:
        return None
    if len(ranges) < 2:
        raise RangeInputError(ErrorCode.TOO_FEW_PLAYERS)
    return EquityRequest(tuple(ranges), "".join(board), "".join(dead))


def format_reply(request: EquityRequest, equities: list[float]) -> str:
    if any(not isfinite(value) or not 0 <= value <= 1 for value in equities):
        raise ValueError("Unexpected equity results from OMPEval")
    # OMPEval reports all zeroes when no valid hands can be evaluated.
    if max(equities) == 0:
        raise RangeInputError(ErrorCode.CARD_CONFLICT)

    winner = max(equities)
    lines = ["| Range | Equity |", "|:--|--:|"]
    for hand_range, equity in zip(request.ranges, equities):
        label, percentage = shorten(hand_range), f"{equity:.2%}"
        if equity == winner:
            label, percentage = f"**{label}**", f"**{percentage}**"
        lines.append(f"| {label} | {percentage} |")
    return "\n".join(lines)


def make_reply(body: str, evaluator: Callable = get_equity) -> str | None:
    """Process text locally without importing PRAW or connecting to Reddit."""
    request = parse_request(body)
    if request is None:
        return None
    equities, _finished, _stdev = evaluator(request.ranges, request.board, request.dead)
    return format_reply(request, equities)


def process_item(item, evaluator: Callable = get_equity) -> None:
    try:
        reply = make_reply(item.body, evaluator)
    except RangeInputError as exc:
        reply = str(exc)

    if reply is not None:
        item.reply(reply)
    item.mark_read()


def main() -> None:
    import praw

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    reddit = praw.Reddit("equity_bot")
    LOGGER.info("Connected to Reddit as u/%s", reddit.user.me())

    #do not process queries made while bot was offline
    # for item in reddit.inbox.unread(limit=None):
    #     try:
    #         process_item(item)
    #     except Exception:
    #         LOGGER.exception("Could not process inbox item %s", getattr(item, "id", "unknown"))
    for item in reddit.inbox.stream(skip_existing=True):
        try:
            process_item(item)
        except Exception:
            LOGGER.exception("Could not process inbox item %s", getattr(item, "id", "unknown"))


if __name__ == "__main__":
    main()
