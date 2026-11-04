from django.test import SimpleTestCase

from routing.services.recommend import compute_metrics, explain, rank_routes


def metrics(low=0.0, moderate=0.0, high=0.0, severe=0.0, no_travel=0.0, hours=10.0):
    """Build metrics from miles per level, one checkpoint per level."""
    levels, coverage = [], []
    for level, miles in enumerate((low, moderate, high, severe, no_travel)):
        if miles:
            levels.append(level)
            coverage.append(miles)
    return compute_metrics(levels, coverage, duration_s=hours * 3600)


class ComputeMetricsTests(SimpleTestCase):
    def test_distance_weighted_average(self):
        m = compute_metrics([0, 2, 4], [50, 25, 25], duration_s=3600)
        self.assertAlmostEqual(m.average_risk, (0 * 50 + 2 * 25 + 4 * 25) / 100)
        self.assertEqual(m.high_miles, 25)
        self.assertEqual(m.no_travel_miles, 25)

    def test_empty_route(self):
        self.assertEqual(compute_metrics([], [], 0).average_risk, 0)


class RankingTests(SimpleTestCase):
    def test_fewest_severe_miles_wins_over_faster_route(self):
        fast_but_severe = metrics(low=90, severe=10, hours=8)
        slow_but_safe = metrics(low=60, high=40, hours=12)
        self.assertEqual(rank_routes([fast_but_severe, slow_but_safe])[0], 1)

    def test_high_miles_break_severe_ties(self):
        a = metrics(low=70, high=30)
        b = metrics(low=80, high=20)
        self.assertEqual(rank_routes([a, b])[0], 1)

    def test_average_risk_breaks_high_and_severe_ties(self):
        a = metrics(low=50, moderate=50)
        b = metrics(low=80, moderate=20)
        self.assertEqual(rank_routes([a, b])[0], 1)

    def test_negligible_average_risk_difference_lets_time_decide(self):
        # Same 25 Moderate miles; the longer route only *looks* safer on average.
        short_fast = metrics(low=991, moderate=25, hours=15.7)
        long_slow = metrics(low=1054, moderate=25, hours=17.0)
        self.assertLess(long_slow.average_risk, short_fast.average_risk)
        self.assertEqual(rank_routes([long_slow, short_fast])[0], 1)

    def test_travel_time_breaks_full_weather_ties(self):
        a = metrics(low=100, hours=11)
        b = metrics(low=100, hours=9)
        c = metrics(low=100, hours=10)
        self.assertEqual(rank_routes([a, b, c]), [1, 2, 0])

    def test_no_travel_miles_rank_worse_than_severe_miles(self):
        blocked = metrics(low=95, no_travel=5)
        severe = metrics(low=50, severe=50)
        self.assertEqual(rank_routes([blocked, severe])[0], 1)

    def test_float_noise_does_not_decide_the_winner(self):
        a = compute_metrics([0, 3], [90.0, 10.00000001], duration_s=3600)
        b = compute_metrics([0, 3], [90.0, 10.0], duration_s=7200)
        self.assertEqual(rank_routes([a, b])[0], 0)


class ExplainTests(SimpleTestCase):
    def test_mentions_the_deciding_criterion(self):
        self.assertIn("Severe", explain(metrics(low=100), metrics(low=90, severe=10)))
        self.assertIn("faster", explain(metrics(low=100, hours=9), metrics(low=100, hours=10)))
        self.assertIn("average risk", explain(metrics(low=90, moderate=10), metrics(low=50, moderate=50)))

    def test_single_route(self):
        self.assertEqual(explain(metrics(low=1), None), "Only one route was available.")
