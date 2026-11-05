"""Thin adapter around OMPEval, with no Reddit-specific behavior."""

from math import isfinite


# These match the original repository's OMPEval settings.
TIME_LIMIT_SECONDS = 5.0
STANDARD_ERROR_TARGET = 0.0025


def get_equity(ranges: list[str] | tuple[str, ...], board: str = "", dead: str = "") -> tuple[list[float], bool, float]:
    """Return equity fractions, OMPEval's finished flag, and estimated standard error.

    OMPEval is imported only when needed, so parsing/tests run without its
    compiled extension. A timeout is a ceiling, not an accuracy guarantee.
    """
    import ompeval as omp

    calculator = omp.EquityCalculator()
    calculator.set_hand_limit(0)
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

    # A broken or empty calculation must never be presented as a real result.
    if any(not isfinite(value) or value < 0 or value > 1 for value in equities):
        raise RuntimeError("OMPEval returned an invalid equity value")

    return equities, result.finished, float(result.stdev)
