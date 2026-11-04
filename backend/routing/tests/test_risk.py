from django.test import SimpleTestCase

from routing.services.risk import Risk, assess, classify_level, rain_risk, snow_risk, wind_risk

L, M, H, S, NT = Risk.LOW, Risk.MODERATE, Risk.HIGH, Risk.SEVERE, Risk.NO_TRAVEL


class WindThresholdTests(SimpleTestCase):
    def test_bands_and_boundaries(self):
        cases = [
            (0, L),
            (24.9, L),
            (25, M),
            (34.9, M),
            (35, H),
            (44.9, H),
            (45, S),
            (54.9, S),
            (55, NT),
            (80, NT),
        ]
        for mph, expected in cases:
            with self.subTest(mph=mph):
                self.assertEqual(wind_risk(mph), expected)


class RainThresholdTests(SimpleTestCase):
    def test_bands_and_boundaries(self):
        cases = [
            (0, L),
            (0.099, L),
            (0.10, M),
            (0.249, M),
            (0.25, H),
            (0.499, H),  # 0.25 appears in two bands; it belongs to the higher one
            (0.50, S),
            (1.00, S),  # "0.50–1.00" is Severe, inclusive of 1.00
            (1.001, NT),
            (2.0, NT),  # "> 1.00"
        ]
        for rate, expected in cases:
            with self.subTest(rate=rate):
                self.assertEqual(rain_risk(rate), expected)


class SnowThresholdTests(SimpleTestCase):
    def test_bands_and_boundaries(self):
        cases = [
            (0, L),
            (0.49, L),
            (0.5, M),
            (0.99, M),
            (1.0, H),
            (1.99, H),
            (2.0, S),
            (3.0, S),
            (3.01, NT),
        ]
        for rate, expected in cases:
            with self.subTest(rate=rate):
                self.assertEqual(snow_risk(rate), expected)


class LoadRuleTests(SimpleTestCase):
    def test_55_mph_is_no_travel_for_any_load(self):
        self.assertEqual(assess(55, 0, 0, load_lb=0).level, NT)

    def test_severe_wind_with_heavy_load_is_no_travel(self):
        self.assertEqual(assess(45, 0, 0, load_lb=30_001).level, NT)
        self.assertEqual(assess(54.9, 0, 0, load_lb=45_000).level, NT)

    def test_severe_wind_at_exactly_30000_lb_stays_severe(self):
        self.assertEqual(assess(50, 0, 0, load_lb=30_000).level, S)

    def test_high_wind_with_very_heavy_load_is_severe(self):
        self.assertEqual(assess(35, 0, 0, load_lb=40_001).level, S)
        self.assertEqual(assess(44.9, 0, 0, load_lb=40_001).level, S)

    def test_high_wind_at_exactly_40000_lb_stays_high(self):
        self.assertEqual(assess(40, 0, 0, load_lb=40_000).level, H)

    def test_load_rules_do_not_touch_lower_wind(self):
        self.assertEqual(assess(30, 0, 0, load_lb=80_000).level, M)

    def test_load_rule_reason_is_reported(self):
        result = assess(48, 0, 0, load_lb=36_000)
        self.assertEqual(result.level, NT)
        self.assertTrue(any("30,000 lb" in r for r in result.reasons))


class CombinedAssessmentTests(SimpleTestCase):
    def test_overall_level_is_the_worst_component(self):
        result = assess(wind_mph=10, rain_in_hr=0.3, snow_in_hr=0.6, load_lb=20_000)
        self.assertEqual(result.level, H)
        self.assertEqual((result.wind, result.rain, result.snow), (L, H, M))
        self.assertEqual(result.reasons, ["Rain 0.30 in/hr → High"])

    def test_calm_weather_has_no_reasons(self):
        self.assertEqual(assess(5, 0, 0, 10_000).reasons, [])

    def test_fast_path_matches_full_assessment(self):
        for wind in (0, 26, 36, 41, 46, 56):
            for rain in (0, 0.12, 0.3, 0.6, 1.2):
                for snow in (0, 0.7, 1.5, 2.5, 3.5):
                    for load in (10_000, 35_000, 45_000):
                        self.assertEqual(
                            classify_level(wind, rain, snow, load), int(assess(wind, rain, snow, load).level)
                        )
