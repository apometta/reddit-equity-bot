from math import isfinite


TIME_LIMIT_SECONDS = 5.0
STANDARD_ERROR_TARGET = 0.0025

#Primary equity calculation function.  Takes in ranges, board and dead, returns appropriate equity calculation.
def get_equity(ranges: list[str] | tuple[str, ...], board: str = "", dead: str = "") -> tuple[list[float], bool, float]:
    import ompeval as omp

    calculator = omp.EquityCalculator()
    calculator.set_hand_limit(0) #no hand limit
    calculator.set_time_limit(TIME_LIMIT_SECONDS)
    calculator.start(
        hand_ranges=[omp.CardRange(value) for value in ranges],
        board_cards=omp.CardRange.getCardMask(board),
        dead_cards=omp.CardRange.getCardMask(dead),
        enumerate_all=False,
        stdev_target=STANDARD_ERROR_TARGET,
    )
    calculator.wait()
    result = calculator.get_results()
    equities = [float(x) for x in result.equity]

    if any(not isfinite(value) or value < 0 or value > 1 for value in equities):
        raise RuntimeError("OMPEval returned an invalid equity value")

    return equities, result.finished, float(result.stdev)
