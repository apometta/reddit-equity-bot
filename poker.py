from errors import ErrorCode, RangeInputError
import ompeval as omp

#A basic equity calculation capped at 5 seconds 
#with a 95% confidence of the answer being within 0.5%
def get_equity(ranges, board, dead):
	eq = omp.EquityCalculator()
	eq.set_hand_limit(0)
	eq.set_time_limit(5)

	eq.start(
		hand_ranges = [omp.CardRange(range) for range in ranges],
		board_cards = omp.CardRange.getCardMask(board),
		dead_cards = omp.CardRange.getCardMask(dead),
		enumerate_all = False,
		stdev_target = 0.0025
	)

	eq.wait()
	results = eq.get_results()

	return (results.equity.tolist(), results.finished, results.stdev)
