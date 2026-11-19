"""This file handles comment parsing and sending the equity analysis request.  It also handles conversion of percentage ranges into a proper range string and formatting the reply for output."""

from bisect import bisect_right
from dataclasses import dataclass
from math import isfinite
import re
from typing import Callable

from errors import ErrorCode, RangeInputError, shorten
from poker import get_equity
from percentage_strings import range_percentages

#These can be adjusted for different comment acceptance settings.
MAX_PLAYERS = 6
MAX_RANGE_CHARS = 1024
MAX_REQUEST_SECTIONS = 32

#Regular expressions for various range input types.
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


# Validate range notation only, NOT logical coherence.
def _validate_range(value: str) -> None:
    if not value or len(value) > MAX_RANGE_CHARS:
        raise RangeInputError(ErrorCode.INVALID_RANGE, value)
    if value.lower() in ("random", "atc"):
        return

    if PERCENT.fullmatch(value):
        if 0 < float(value[:-1]) <= 100:
            return
        raise RangeInputError(ErrorCode.INVALID_RANGE, value) #percentage outside of range [0, 100]
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

        #If a missing ending brace is detected, it is considered to be before the next 
        #opening brace, or the end of the comment if no further opening braces are found
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
            #Skips over empty sections
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

    if not ranges: #If no ranges detected, the comment is simply ignored
        return None
    if len(ranges) < 2:
        raise RangeInputError(ErrorCode.TOO_FEW_PLAYERS)
    return EquityRequest(tuple(ranges), "".join(board), "".join(dead))

#Responsible for formatting the output.  request is the initial request object, and 
#equities is the results in order.
def format_reply(request: EquityRequest, equities: list[float]) -> str:
    if any(not isfinite(value) or not 0 <= value <= 1 for value in equities):
        raise ValueError("Unexpected equity results from OMPEval")
    # OMPEval returns all-zero equities when no valid deal is available.
    # This is treated as a card conflict.
    if max(equities) == 0:
        raise RangeInputError(ErrorCode.CARD_CONFLICT)

    winner = max(equities)
    lines = ["| Range | Equity |", "|:--|--:|"]

    for hand_range, equity in zip(request.ranges, equities):
        label, percentage = shorten(hand_range), f"{equity:.2%}"

        #For percentage range inputs, this shows both the percentage and its 
        #appropriate range string in the results.
        if PERCENT.fullmatch(hand_range):
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


# Returns string for reply to a given comment body.
def make_reply(body: str, evaluator: Callable = get_equity) -> str | None:
    request = parse_request(body)
    if request is None:
        return None
    evaluator_ranges = tuple(_expand_range(value) for value in request.ranges)
    equities, _finished, _stdev = evaluator(evaluator_ranges, request.board, request.dead)
    return format_reply(request, equities)


