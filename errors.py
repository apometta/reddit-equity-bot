"""User-facing errors for malformed equity requests."""

from enum import Enum, auto


class ErrorCode(Enum):
    INVALID_RANGE = auto()
    INVALID_BOARD = auto()
    INVALID_DEAD = auto()
    TOO_MANY_PLAYERS = auto()
    TOO_FEW_PLAYERS = auto()
    CARD_CONFLICT = auto()
    MALFORMED_REQUEST = auto()
    NO_VALID_DEALS = auto()


MAX_DISPLAY_LENGTH = 150


def shorten(value: str, length: int = MAX_DISPLAY_LENGTH) -> str:
    """Limit potentially lengthy user-provided text in Reddit replies."""
    return value if len(value) <= length else value[:length] + "..."


class RangeInputError(ValueError):
    def __init__(self, code: ErrorCode, offending_range: str = "") -> None:
        self.code = code
        self.offending_range = shorten(offending_range)

        messages = {
            ErrorCode.INVALID_RANGE: f"Invalid hand range: `{self.offending_range}`.",
            ErrorCode.INVALID_BOARD: f"Invalid board cards: `{self.offending_range}`.",
            ErrorCode.INVALID_DEAD: f"Invalid dead cards: `{self.offending_range}`.",
            ErrorCode.TOO_MANY_PLAYERS: "Too many hand ranges. The maximum is 6 players.",
            ErrorCode.TOO_FEW_PLAYERS: "Too few hand ranges. Supply 2 to 6 players.",
            ErrorCode.CARD_CONFLICT: "Card conflict: the same physical card is required more than once.",
            ErrorCode.MALFORMED_REQUEST: "Malformed request: check the curly braces and `b:` / `d:` sections.",
            ErrorCode.NO_VALID_DEALS: (
                "No valid equity result was produced. Check whether the ranges, board, "
                "and dead cards permit any non-overlapping hands."
            ),
        }
        super().__init__(messages[code])
