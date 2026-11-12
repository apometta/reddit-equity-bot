"""
Error codes:
  INVALID_RANGE: Unsupported range syntax (e.g. {banana}, {AsKdJc}, {JJ+ AdJd}).
  INVALID_BOARD / INVALID_DEAD: Reserved; currently not raised. Board/dead card
      interpretation is delegated to OMPEval.
  TOO_MANY_PLAYERS: More than 6 ranges.
  TOO_FEW_PLAYERS: Exactly 1 range. Zero ranges cause the bot to ignore the request.
  CARD_CONFLICT: OMPEval returned all-zero equities, interpreted as no legal deal.
      For example: {AhKh} {QcQd} {b: Ah2s3c}.
  MALFORMED_REQUEST: Request exceeds the maximum number of brace sections.
      Common brace typos are recovered when the content can be parsed.
"""
from enum import Enum, auto


class ErrorCode(Enum):
    INVALID_RANGE = auto()
    INVALID_BOARD = auto()
    INVALID_DEAD = auto()
    TOO_MANY_PLAYERS = auto()
    TOO_FEW_PLAYERS = auto()
    CARD_CONFLICT = auto()
    MALFORMED_REQUEST = auto()

MAX_DISPLAY_LENGTH = 150

# Shortens a range string to a maximum limit for ease of output.
def shorten(value: str, length: int = MAX_DISPLAY_LENGTH) -> str:
    return value if len(value) <= length else value[:length] + "..."

# This wrapper class also generates the error reply sent to the user.
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
            ErrorCode.CARD_CONFLICT: "Card conflict: no non-overlapping deal is possible.",
            ErrorCode.MALFORMED_REQUEST: "Malformed request: too many brace sections.",
        }
        super().__init__(messages[code])
