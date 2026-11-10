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

#A class representing an individual request for the bot.
@dataclass(frozen=True)
class EquityRequest:
    ranges: tuple[str, ...]
    board: str = ""
    dead: str = ""

#Remove all whitespace
def _compact(text: str) -> str:
    return "".join(text.split())

#Removes excess commas and whitespace.  Redundant commas are allowed in equity requests.
def _clean_range(text: str) -> str:
    return ",".join(token for token in _compact(text).split(",") if token)

#This function ensures a range request is of valid syntax, and raises the appropriate error 
#if not.  It does not do any sort of logical checking, e.g. ensuring that a card on the board 
#is not also a dead card.  Only syntax is checked.
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

#Primary parsing function: forms an EquityRequest from the comment body by finding ranges, board and dead cards.  This function also raises errors related to number of players.
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

#
def format_reply(request: EquityRequest, equities: list[float]) -> str:
    if any(not isfinite(value) or not 0 <= value <= 1 for value in equities):
        raise ValueError("Unexpected equity results from OMPEval")
    #If all equities are 0, it means OMPEval could not complete the equity calculation, which 
    #this program assumes means that there is some conflict within the ranges (e.g. one range 
    #is "AsKh" but then the board is "b: AsJd2c").
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

#Handles keyword exceptions and percentage range inputs by converting them to traditional range strings.
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

#A function for replying to an item, but disregards nonrequests.  Can be tested locally without connecting to Reddit.
def make_reply(body: str, evaluator: Callable = get_equity) -> str | None:
    request = parse_request(body)
    if request is None:
        return None
    evaluator_ranges = tuple(_expand_range(value) for value in request.ranges)
    equities, _finished, _stdev = evaluator(evaluator_ranges, request.board, request.dead)
    return format_reply(request, equities)

#A function for handling an individual reply, requires connection to Reddit.
def process_item(item, evaluator: Callable = get_equity) -> None:
    try:
        reply = make_reply(item.body, evaluator)
    except RangeInputError as exc:
        reply = str(exc)

    if reply is not None:
        item.reply(reply)
    item.mark_read()

#Connects to Reddit and sets up continuous stream of inbox items to reply to.
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
