import praw, poker
from errors import ErrorCode, RangeInputError
from poker import get_equity

CARDS = set(['2', '3', '4', '5', '6', '7', '8', '9', 't', 'j', 'q', 'k', 'a'])
SUITS = set(['s', 'd', 'h', 'c'])

#Takes string and returns list consisting of all substrings within curly braces {}
#Does NOT check for the validity of said substrings
def get_ranges(comment_body):
    ranges = []
    board = ""
    dead = ""
    comment_len = len(comment_body)
    i = 0

    while i < comment_len and len(ranges) < 7:
        while i < comment_len and comment_body[i] != '{':
            i += 1
        if i >= comment_len - 1: break #stop if we are at or after last character
        i += 1 #element after '{'

        parsing_board = parsing_dead = False
        if comment_body[i] in ('b', 'd'):
            if comment_body[i] == 'b':
                parsing_board = True
            else:
                parsing_dead = True

            while i < comment_len and comment_body[i] not in (':', ' ', '\t'):
                i += 1
            while i < comment_len and comment_body[i] in (':', ' ', '\t'):
                i += 1

        start = i #start of board, dead, or range string not including {}, 'b', 'd', or any whitespace or colons
        while i < comment_len and comment_body[i] != '}':
            i += 1
        final_string = comment_body[start:i]
        if parsing_board:
            board += final_string
        elif parsing_dead:
            dead += final_string
        else:
            ranges.append(final_string)

    if len(ranges) >= 7:
        raise RangeInputError(ErrorCode.TOO_MANY_PLAYERS)
    elif len(ranges) == 1:
        raise RangeInputError(ErrorCode.TOO_FEW_PLAYERS)
    return (ranges, board, dead)

#Returns True if range is valid, False if not.  Assumes whitespace is removed and all text lowercase.
#- notation is NOT supported by the library.  Does NOT work for board or dead cards.
def check_range(range):
    i, n = 0, len(range)
    while i < n:
        if range[i] not in CARDS or i == n - 1: return False
        i += 1 #guaranteed < n

        if range[i] == range[i - 1]: #POCKET PAIR LOGIC HERE
            i += 1
            if i < n and range[i] == 'o': i += 1
            if i < n and range[i] == '+': i += 1
        elif range[i] in SUITS: #specific card combination
            if i > n - 3 or range[i + 1] not in CARDS or range[i + 2] not in SUITS: return False
            i += 3
        elif range[i] in CARDS: #card combination
            i += 1
            if i < n and range[i] in ('o', 's'): i += 1
            if i < n and range[i] == '+': i += 1
        else: return False #unrecognized symbol

        if i < n and range[i] != ',': return False
        i += 1

    return True

#Returns the set of all cards (as length-2 strings) found IF the operation is successful, 
#throws error if not.
def check_board_dead(range, board = True, used = set()):
    i, n = 0, len(range)
    curr = set()

    while i < n:
        if i >= n - 1 or range[i] not in CARDS or range[i + 1] not in SUITS: return False
        card = range[i:i + 2]
        i += 2

        if card in used: raise RangeInputError(ErrorCode.CARD_CONFLICT)
        curr.add(card)
        if board and len(curr) > 5: raise RangeInputError(ErrorCode.INVALID_BOARD)

    return curr

def check_ranges(ranges, board, dead):
    pass #implement manually, no regex


reddit = praw.Reddit("equity_bot")
print("Logged in.")

for item in reddit.inbox.stream(skip_existing=True):
    try:
        ranges, board, dead = get_ranges(item.body.lower())
        if len(ranges) == 0: continue

        check_ranges(ranges, board, dead)
        results, finished, stdev = get_equity(ranges, board, dead)
        best_equity = max(results)

        reply_message_lines = ["|**Range**|**Equity**|", "|-|-|"]
        for i in range(len(ranges)):
            range_str, equity_result = ranges[i], results[i]
            if len(range_str) > 150: range_str = range_str[:150] + "..."

            if equity_result == best_equity:
                range_str = "**" + range_str + "**" #bold the winner
                equity_result = "**" + str(equity_result) + "**"
            else:
                equity_result = str(equity_result)
            reply_message_lines.append(range_str + " | " + equity_result)

        item.reply("\n".join(reply_message_lines))
        print("Processed message ")
    except RangeInputError as e:
        item.reply(str(e))
    finally:
        item.mark_read() #this happens even if continue is used above