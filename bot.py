"""
A Reddit poker bot, written by Andrew H. Pometta, for Texas Holdem equity analysis.  See README.md or USAGE.md for details.  A python port of OMPEval is used for the evaluation, and PRAW for the Reddit interfacing.

This is the main module, with the main method.  Mostly responsible for handling comment/message aggregation and parsing.
"""

import logging
from bisect import bisect_right
import re
from dataclasses import dataclass
from math import isfinite
from typing import Callable
from errors import ErrorCode, RangeInputError, shorten
from poker import get_equity
from percentage_strings import range_percentages

LOGGER = logging.getLogger(__name__)
MAX_PLAYERS = 6
MAX_RANGE_CHARS = 1024
MAX_REQUEST_SECTIONS = 32
# These expressions describe the accepted *text*, not the possible deals.
EXACT_HAND = re.compile(r"[2-9TJQKA][shdc][2-9TJQKA][shdc]", re.I)
PAIR = re.compile(r"([2-9TJQKA])\1o?\+?", re.I)
OTHER_HAND = re.compile(r"([2-9TJQKA])([2-9TJQKA])([so])?\+?", re.I)
SECTION = re.compile(r"\s*([bd])\s*:\s*(.*?)\s*\Z", re.I | re.S)
PERCENT = re.compile(r"(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)%\Z")


def _cumulative_combos(ranking) -> tuple[int, ...]:
    # Use exact combo counts: the stored percentages are rounded for display.
    total = 0
    counts = []
    for hand, _percentage, _range in ranking:
        if hand.upper() == "ATC":
            total = 1326
        else:
            total += 6 if len(hand) == 2 else (4 if hand.lower().endswith("s") else 12)
        counts.append(total)
    return tuple(counts)


CUTOFFS = _cumulative_combos(range_percentages)

# A class representing an individual request for the bot.
@dataclass(frozen=True)
class EquityRequest:
    ranges: tuple[str, ...]
    board: str = ""
    dead: str = ""


# Remove all whitespace.
def _compact(text: str) -> str:
    return "".join(text.split())


# Remove excess commas and whitespace. Redundant commas are allowed.
def _clean_range(text: str) -> str:
    return ",".join(token for token in _compact(text).split(",") if token)


# Validate range notation only; physical card conflicts are left to OMPEval.
def _validate_range(value: str) -> None:
    if not value or len(value) > MAX_RANGE_CHARS:
        raise RangeInputError(ErrorCode.INVALID_RANGE, value)
    if value.lower() in ("random", "atc"):
        return
    if PERCENT.fullmatch(value):
        if 0 < float(value[:-1]) <= 100:
            return
        raise RangeInputError(ErrorCode.INVALID_RANGE, value)
    for token in value.split(","):
        if EXACT_HAND.fullmatch(token) or PAIR.fullmatch(token):
            continue
        match = OTHER_HAND.fullmatch(token)
        if match and match.group(1).lower() != match.group(2).lower():
            continue
        raise RangeInputError(ErrorCode.INVALID_RANGE, value)


# Extract the ranges and optional board/dead cards. Recover unambiguous missing
# closing braces and ignore stray closing braces outside a section.
def parse_request(body: str) -> EquityRequest | None:
    if "{" not in body:
        return None

    ranges: list[str] = []
    board: list[str] = []
    dead: list[str] = []
    cursor = 0
    sections = 0
    while (opening := body.find("{", cursor)) != -1:
        closing = body.find("}", opening + 1)
        next_opening = body.find("{", opening + 1)

        # A new opening brace or end-of-text can act as a missing closing brace.
        # Still validate the resulting section below rather than guessing content.
        if closing == -1:
            end = next_opening if next_opening != -1 else len(body)
        elif next_opening != -1 and next_opening < closing:
            end = next_opening
        else:
            end = closing

        sections += 1
        if sections > MAX_REQUEST_SECTIONS:
            raise RangeInputError(ErrorCode.MALFORMED_REQUEST)

        content = body[opening + 1:end]
        if not content.strip() and end == next_opening:
            # Tolerate a duplicated opening brace, e.g. {{AA}}.
            cursor = end
            continue

        section = SECTION.fullmatch(content)
        if section:
            (board if section.group(1).lower() == "b" else dead).append(_compact(section.group(2)))
        else:
            value = _clean_range(content)
            _validate_range(value)
            ranges.append(value)
            if len(ranges) > MAX_PLAYERS:
                raise RangeInputError(ErrorCode.TOO_MANY_PLAYERS)

        cursor = end + 1 if end == closing else end

    if not ranges:
        return None
    if len(ranges) < 2:
        raise RangeInputError(ErrorCode.TOO_FEW_PLAYERS)
    return EquityRequest(tuple(ranges), "".join(board), "".join(dead))


def format_reply(request: EquityRequest, equities: list[float]) -> str:
    if any(not isfinite(value) or not 0 <= value <= 1 for value in equities):
        raise ValueError("Unexpected equity results from OMPEval")
    # OMPEval returns all-zero equities when no valid deal is available.
    # This is treated as a card conflict, not checked manually here.
    if max(equities) == 0:
        raise RangeInputError(ErrorCode.CARD_CONFLICT)
    winner = max(equities)
    lines = ["| Range | Equity |", "|:--|--:|"]
    for hand_range, equity in zip(request.ranges, equities):
        label, percentage = shorten(hand_range), f"{equity:.2%}"
        if PERCENT.fullmatch(hand_range):
            # Display the selected range, shortened to 150 characters when needed.
            # This changes only the reply, not the input sent to OMPEval.
            index = bisect_right(CUTOFFS, float(hand_range[:-1]) * 1326 / 100) - 1
            if index < 0:
                raise RangeInputError(ErrorCode.INVALID_RANGE, hand_range)
            label = f"{hand_range} ({shorten(range_percentages[index][2])})"
        if equity == winner:
            label, percentage = f"**{label}**", f"**{percentage}**"
        lines.append(f"| {label} | {percentage} |")
    return "\n".join(lines)


# Convert percentage and random/ATC aliases to OMPEval range notation.
def _expand_range(value: str) -> str:
    if value.lower() in ("random", "atc"):
        return "random"
    if not PERCENT.fullmatch(value):
        return value
    index = bisect_right(CUTOFFS, float(value[:-1]) * 1326 / 100) - 1
    if index < 0:  # Too small to contain even the first ranked hand.
        raise RangeInputError(ErrorCode.INVALID_RANGE, value)
    selected = range_percentages[index][2]
    return "random" if selected.lower() in ("random", "atc") else selected


# Calculate a reply without connecting to Reddit; ignores nonrequests.
def make_reply(body: str, evaluator: Callable = get_equity) -> str | None:
    request = parse_request(body)
    if request is None:
        return None
    evaluator_ranges = tuple(_expand_range(value) for value in request.ranges)
    equities, _finished, _stdev = evaluator(evaluator_ranges, request.board, request.dead)
    return format_reply(request, equities)


# Handle an individual Reddit inbox item.
def process_item(item, evaluator: Callable = get_equity) -> None:
    try:
        reply = make_reply(item.body, evaluator)
    except RangeInputError as exc:
        reply = str(exc)

    if reply is not None:
        item.reply(reply)
    item.mark_read()


# Connect to Reddit and process only new inbox items, not past unread items.
def main() -> None:
    import praw

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    reddit = praw.Reddit("equity_bot")
    LOGGER.info("Connected to Reddit as u/%s", reddit.user.me())
    for item in reddit.inbox.stream(skip_existing=True):
        try:
            process_item(item)
        except Exception:
            LOGGER.exception("Could not process inbox item %s", getattr(item, "id", "unknown"))


if __name__ == "__main__":
    main()
