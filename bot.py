import praw
from errors import ErrorCode, RangeInputError

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
        if comment_body[i].lower() in ('b', 'd'):
            if comment_body[i].lower() == 'b':
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
    elif len(ranges) < 2:
        raise RangeInputError(ErrorCode.TOO_FEW_PLAYERS)
    return (ranges, board, dead)


reddit = praw.Reddit("equity_bot")
print("Logged in.")

for item in reddit.inbox.stream(skip_existing=True):
    print(f"Received: {item}")

    item.reply("Hello!")
    item.mark_read()