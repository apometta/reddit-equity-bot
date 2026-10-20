import praw
from enum import Enum, auto

class ErrorCode(enum):
    INVALID_RANGE = auto()
    INVALID_BOARD = auto()
    INVALID_DEAD = auto()
    TOO_MANY_PLAYERS = auto()
    TOO_FEW_PLAYERS = auto()

class RangeInputError(InputError):
    def __init__(self, code, offending_range):
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

        super().__init__(message)

#Takes string and returns list consisting of all substrings within curly braces {}
#Does NOT check for the validity of said substrings
def get_ranges(comment_body):
    ranges = []
    comment_len = len(comment_body)
    i = 0

    while i < comment_len and len(ranges) < 7:
        while i < comment_len and comment_body[i] != '{':
            i += 1
        if i == comment_len: break
        start = i + 1
        
        current_range = [] #we reconstruct the range we were provided but remove whitespace
        while i < comment_len and comment_body[i] != '}':
            if not comment_body[i].isspace():
                current_range.append(comment_body[i])
            i += 1

        if i < comment_len:
            ranges.append("".join(current_range).lower())



reddit = praw.Reddit("equity_bot")
print("Logged in.")

for item in reddit.inbox.stream(skip_existing=True):
    print(f"Received: {item}")

    item.reply("Hello!")
    item.mark_read()