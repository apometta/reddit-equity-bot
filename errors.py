from enum import Enum, auto

class ErrorCode(enum):
    INVALID_RANGE = auto()
    INVALID_BOARD = auto()
    INVALID_DEAD = auto()
    TOO_MANY_PLAYERS = auto()
    TOO_FEW_PLAYERS = auto()
    CARD_CONFLICT = auto()

class RangeInputError(InputError):
    def __init__(self, code, offending_range = ""):
        self.code = code
        self.offending_range = offending_range
        if len(self.offending_range) > 150:
            self.offending_range = self.offending_range[:150] + "..."

        match code:
            case ErrorCode.INVALID_RANGE:
                message = f"Range {self.offending_range} is invalid: please check formatting."
            case ErrorCode.INVALID_BOARD:
                message = f"Board {self.offending_range} is invalid: please check formatting."
            case ErrorCode.INVALID_DEAD:
                message = f"Dead cards {self.offending_range} is invalid: please check formatting."
            case ErrorCode.TOO_MANY_PLAYERS:
                message = "Too many ranges.  Maximum supported ranges: 6."
            case ErrorCode.TOO_FEW_PLAYERS:
                message = "Too few ranges.  Minimum supported ranges: 2."
            case ErrorCode.CARD_CONFLICT:
                message = "Card conflict: at least one card is necessarily in two separate ranges and/or dead/board cards."

        super().__init__(message)