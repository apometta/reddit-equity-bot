"""Reddit equity bot: parse requests, validate them, calculate, and reply.

    {AA,KK} {QQ} {b: As Kd Qc} {d: 2h 3s}

Supported hand tokens: AA, QQ+, AK, AKo, ATs+, AsKh, and comma-separated
unions of these. Neither percentage ranges nor dash ranges are supported.
"""

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from math import isfinite
from typing import Callable

from errors import ErrorCode, RangeInputError, shorten
from poker import get_equity

LOGGER = logging.getLogger(__name__)
RANKS = "23456789TJQKA"
SUITS = "shdc"
MAX_PLAYERS = 6
MAX_RANGE_CHARS = 1024
MAX_REQUEST_SECTIONS = 32

SPECIFIC_HAND = re.compile(r"[2-9TJQKA][shdc][2-9TJQKA][shdc]\Z")
PAIR = re.compile(r"([2-9TJQKA])\1\+?\Z")
NONPAIR = re.compile(r"([2-9TJQKA])([2-9TJQKA])([so])?\+?\Z")
SECTION = re.compile(r"\s*([bd])\s*:\s*(.*?)\s*\Z", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class EquityRequest:
    ranges: tuple[str, ...]
    board: str = ""
    dead: str = ""


def _compact(text: str) -> str:
    return "".join(ch for ch in text if not ch.isspace())


def _normalize_range(text: str) -> str:
    # Ranks uppercase, suits / suitedness lowercase, e.g. "ahkh" -> "AhKh".
    return "".join(ch.upper() if ch.lower() in "tjqka" else ch.lower()
                   for ch in _compact(text))


def _validate_range(value: str) -> frozenset[str]:
    """Validate a range; return cards that *every* explicitly named hand uses.

    Broad ranges like AA don't force any particular physical card, whereas
    {AsAh,AsAd} forces As. The latter is useful for early conflict checks.
    """
    if not value or len(value) > MAX_RANGE_CHARS:
        raise RangeInputError(ErrorCode.INVALID_RANGE, value)

    forced_cards: set[str] | None = None
    for token in value.split(","):
        if not token:
            raise RangeInputError(ErrorCode.INVALID_RANGE, value)

        if SPECIFIC_HAND.fullmatch(token):
            cards = {token[:2].lower(), token[2:].lower()}
            if len(cards) != 2:
                raise RangeInputError(ErrorCode.CARD_CONFLICT)
            forced_cards = cards if forced_cards is None else forced_cards & cards
            continue

        if PAIR.fullmatch(token):
            forced_cards = set()
            continue

        match = NONPAIR.fullmatch(token)
        if match:
            high, low = match.group(1), match.group(2)
            if RANKS.index(high) > RANKS.index(low):
                forced_cards = set()
                continue

        raise RangeInputError(ErrorCode.INVALID_RANGE, value)

    return frozenset(forced_cards or ())


def _parse_cards(value: str, *, is_board: bool) -> set[str]:
    """Validate a concatenated sequence of cards and return unique cards."""
    code = ErrorCode.INVALID_BOARD if is_board else ErrorCode.INVALID_DEAD
    maximum = 5 if is_board else 52
    if len(value) % 2 or len(value) // 2 > maximum:
        raise RangeInputError(code, value)

    result: set[str] = set()
    for offset in range(0, len(value), 2):
        card = value[offset:offset + 2]
        if card[0] not in RANKS.lower() or card[1] not in SUITS:
            raise RangeInputError(code, value)
        if card in result:
            raise RangeInputError(ErrorCode.CARD_CONFLICT)
        result.add(card)
    return result



def _hand_masks(hand_range: str) -> set[int]:
    """Expand validated stove notation into two-card masks for a sanity check.

    This deliberately mirrors OMPEval's rank / suited / offsuit / plus rules.
    It is not used to calculate equity, only to reject impossible deals.
    """
    def card_mask(rank: str, suit: str) -> int:
        return 1 << (4 * RANKS.index(rank) + SUITS.index(suit))

    combinations: set[int] = set()
    for token in hand_range.split(","):
        if SPECIFIC_HAND.fullmatch(token):
            combinations.add(card_mask(token[0], token[1]) | card_mask(token[2], token[3]))
            continue

        pair = PAIR.fullmatch(token)
        if pair:
            first = RANKS.index(pair.group(1))
            ranks = RANKS[first:] if token.endswith("+") else token[0]
            for rank in ranks:
                for i in range(4):
                    for j in range(i + 1, 4):
                        combinations.add(card_mask(rank, SUITS[i]) | card_mask(rank, SUITS[j]))
            continue

        match = NONPAIR.fullmatch(token)
        assert match is not None  # _validate_range() already checked syntax.
        high, low, suitedness = match.groups()
        low_ranks = RANKS[RANKS.index(low):RANKS.index(high)] if token.endswith("+") else low
        for second_rank in low_ranks:
            for first_suit in SUITS:
                for second_suit in SUITS:
                    if suitedness == "s" and first_suit != second_suit:
                        continue
                    if suitedness == "o" and first_suit == second_suit:
                        continue
                    combinations.add(card_mask(high, first_suit) | card_mask(second_rank, second_suit))
    return combinations


def _check_possible_deal(request: EquityRequest, blocked: set[str]) -> None:
    """Ensure at least one assignment exists without any duplicated cards."""
    blocked_mask = 0
    for card in blocked:
        blocked_mask |= 1 << (4 * RANKS.index(card[0].upper()) + SUITS.index(card[1]))

    choices = []
    for hand_range in request.ranges:
        hands = tuple(mask for mask in _hand_masks(hand_range) if not mask & blocked_mask)
        if not hands:
            raise RangeInputError(ErrorCode.NO_VALID_DEALS)
        choices.append(hands)
    choices.sort(key=len)

    @lru_cache(maxsize=50_000)
    def feasible(player: int, used: int) -> bool:
        if player == len(choices):
            return True
        return any(not (hand & used) and feasible(player + 1, used | hand)
                   for hand in choices[player])

    if not feasible(0, blocked_mask):
        raise RangeInputError(ErrorCode.NO_VALID_DEALS)


def _validate_request(request: EquityRequest) -> None:
    if len(request.ranges) < 2:
        raise RangeInputError(ErrorCode.TOO_FEW_PLAYERS)
    if len(request.ranges) > MAX_PLAYERS:
        raise RangeInputError(ErrorCode.TOO_MANY_PLAYERS)

    forced = [_validate_range(value) for value in request.ranges]
    board = _parse_cards(request.board, is_board=True)
    dead = _parse_cards(request.dead, is_board=False)
    if board & dead:
        raise RangeInputError(ErrorCode.CARD_CONFLICT)

    used = board | dead
    for cards in forced:
        if used & cards:
            raise RangeInputError(ErrorCode.CARD_CONFLICT)
        used.update(cards)

    _check_possible_deal(request, board | dead)


def parse_request(body: str) -> EquityRequest | None:
    """Extract and validate bracketed items; return None for non-requests.

    Whitespace in braces is ignored; multiple b:/d: sections are combined.
    Unbalanced or nested braces are errors rather than silently truncated.
    """
    if "{" not in body:
        return None

    ranges: list[str] = []
    board_parts: list[str] = []
    dead_parts: list[str] = []
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
            value = _compact(section.group(2)).lower()
            if section.group(1).lower() == "b":
                board_parts.append(value)
            else:
                dead_parts.append(value)
        else:
            ranges.append(_normalize_range(content))
            if len(ranges) > MAX_PLAYERS:
                raise RangeInputError(ErrorCode.TOO_MANY_PLAYERS)
        cursor = closing + 1

    # A board-only/dead-only comment is not an equity request.
    if not ranges:
        return None

    request = EquityRequest(tuple(ranges), "".join(board_parts), "".join(dead_parts))
    _validate_request(request)
    return request


def format_reply(request: EquityRequest, equities: list[float]) -> str:
    """Produce a complete and consistently escaped Reddit Markdown table."""
    if len(equities) != len(request.ranges):
        raise ValueError("Wrong number of equity results")
    if not equities or any(not isfinite(value) or not (0 <= value <= 1) for value in equities):
        raise ValueError("Invalid equity results")
    if sum(equities) <= 0:
        raise RangeInputError(ErrorCode.NO_VALID_DEALS)

    # Compare displayed values; tiny simulation differences that round to
    # the same percentage should not produce inconsistent visual highlighting.
    percentages = [f"{value * 100:.2f}" for value in equities]
    best_display = max(float(value) for value in percentages)
    lines = ["| Range | Equity |", "|:--|--:|"]
    for hand_range, percentage in zip(request.ranges, percentages):
        display_range = shorten(hand_range)
        display_equity = f"{percentage}%"
        if float(percentage) == best_display:
            display_range = f"**{display_range}**"
            display_equity = f"**{display_equity}**"
        lines.append(f"| {display_range} | {display_equity} |")
    return "\n".join(lines)


def make_reply(body: str, evaluator: Callable = get_equity) -> str | None:
    """Pure processing entrypoint, useful for local testing without PRAW."""
    request = parse_request(body)
    if request is None:
        return None
    equities, _finished, _stdev = evaluator(request.ranges, request.board, request.dead)
    return format_reply(request, equities)


def process_item(item, evaluator: Callable = get_equity) -> None:
    """Acknowledge only requests that were successfully handled.

    Expected input errors get a Reddit reply. Unexpected/API errors propagate,
    leaving the message unread and making the failure visible to the caller.
    """
    try:
        reply = make_reply(item.body, evaluator=evaluator)
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

    # Handle unprocessed requests from earlier runs before listening for new ones.
    for item in reddit.inbox.unread(limit=None):
        try:
            process_item(item)
        except Exception:
            LOGGER.exception("Could not process unread inbox item %s", getattr(item, "id", "unknown"))

    for item in reddit.inbox.stream(skip_existing=True):
        try:
            process_item(item)
        except Exception:
            LOGGER.exception("Could not process streamed inbox item %s", getattr(item, "id", "unknown"))


if __name__ == "__main__":
    main()
