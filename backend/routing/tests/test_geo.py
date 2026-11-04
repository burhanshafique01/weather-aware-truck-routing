from django.test import SimpleTestCase

from routing.services import geo
from routing.services.valhalla import normalize_road


class GeoTests(SimpleTestCase):
    def test_haversine_known_distance(self):
        # Chicago to Denver is ~920 mi as the crow flies.
        self.assertAlmostEqual(geo.haversine_mi((41.8781, -87.6298), (39.7392, -104.9903)), 920, delta=5)

    def test_decode_polyline(self):
        # The reference example from Google's polyline algorithm documentation.
        encoded = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
        coords = geo.decode_polyline(encoded, precision=5)
        expected = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
        for (lat, lon), (elat, elon) in zip(coords, expected, strict=False):
            self.assertAlmostEqual(lat, elat, places=5)
            self.assertAlmostEqual(lon, elon, places=5)

    def test_sample_distances_includes_both_ends(self):
        self.assertEqual(geo.sample_distances(60, 25), [0, 25, 50, 60])
        self.assertEqual(geo.sample_distances(50, 25), [0, 25, 50])

    def test_midpoint_coverage_sums_to_length(self):
        marks = geo.sample_distances(60, 25)
        coverage = geo.midpoint_coverage(marks)
        self.assertAlmostEqual(sum(coverage), 60)
        self.assertEqual(coverage, [12.5, 25, 17.5, 5])

    def test_interpolate_along(self):
        coords = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
        cum = geo.cumulative_miles(coords)
        point, index, frac = geo.interpolate_along(coords, cum, cum[-1] * 0.75)
        self.assertAlmostEqual(point[1], 1.5, places=6)
        self.assertEqual(index, 1)
        self.assertAlmostEqual(frac, 0.5, places=6)

    def test_road_names_are_normalized(self):
        self.assertEqual(normalize_road("South Interstate 45"), "I-45")
        self.assertEqual(normalize_road("I 45 South"), "I-45")
        self.assertEqual(normalize_road("US 20"), "US-20")
        self.assertEqual(normalize_road("TX 36"), "TX-36")
        self.assertEqual(normalize_road("Main Street"), "Main Street")

    def test_offset_point_round_trip(self):
        start = (40.0, -100.0)
        end = geo.offset_point(start, 90, 50)
        self.assertAlmostEqual(geo.haversine_mi(start, end), 50, places=3)
        self.assertAlmostEqual(geo.initial_bearing(start, end), 90, delta=0.5)
