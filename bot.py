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
    if value.lower() in ("random", "atc"):
        return

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


