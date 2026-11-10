from enum import Enum, auto

"""
Error codes are as follows:
  INVALID_RANGE: A range string was formatted in an invalid manner.  Unsupported characters, dash notation, etc.  Examples: {banana}, {AsKdJc}, {JJ+ AdJd}}
  INVALID_BOARD: Incorrectly formatted board cards.  Board does not support the same range strings ranges do.
  INVALID_DEAD: Incorrectly formatted dead cards.  Dead does not support the same range strings ranges do.
  TOO_MANY_PLAYERS: More than 6 ranges inputted.
  TOO_FEW_PLAYERS: Exactly 1 range inputted.  0 ranges inputted does not give this error; the bot simply ignores the request.
  CARD_CONFLICT: A logical error, in which a card is required to be in more than one place for the given situation.  Example: {10%} {AQs+,88+} {AdJh} {b: AsJc9h}
  MALFORMED_REQUEST: Used for when the user gets something wrong related to brackets {}.
  NO_VALID_DEALS: Currently unused.
"""
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

#Shortens a range string to a maximum limit for ease of output.
def shorten(value: str, length: int = MAX_DISPLAY_LENGTH) -> str:
    return value if len(value) <= length else value[:length] + "..."

#This wrapper class around ValueError also generates the reply the bot uses to the user who made the error-generating request.
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
