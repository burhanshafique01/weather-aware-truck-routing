"""End-to-end planner and API tests with the third-party providers stubbed."""

from datetime import UTC, datetime, timedelta
from unittest import mock

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework.test import APIClient

from routing.services import geo, planner, valhalla, weather
from routing.services.planner import TripRequest

DEPARTURE = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


def straight_route(lon_end: float, lat: float, hours: float, source: str = "primary") -> valhalla.RawRoute:
    """A due-east route at constant speed: easy to reason about in tests."""
    coords = [(lat, -100.0 + (lon_end + 100.0) * i / 100) for i in range(101)]
    cum_mi = geo.cumulative_miles(coords)
    cum_s = [hours * 3600 * d / cum_mi[-1] for d in cum_mi]
    return valhalla.RawRoute(
        coords=coords,
        cum_mi=cum_mi,
        cum_s=cum_s,
        distance_mi=cum_mi[-1],
        duration_s=hours * 3600,
        major_roads=["I 80"],
        source=source,
    )


def calm(hours: int = 200) -> weather.HourlySeries:
    zeros = tuple(0.0 for _ in range(hours))
    return weather.HourlySeries(start=DEPARTURE, wind=zeros, gust=zeros, rain=zeros, snow=zeros)


def windy(mph: float, hours: int = 200) -> weather.HourlySeries:
    zeros = tuple(0.0 for _ in range(hours))
    return weather.HourlySeries(
        start=DEPARTURE, wind=tuple(mph for _ in range(hours)), gust=zeros, rain=zeros, snow=zeros
    )


class FakeWeather:
    """Calm everywhere except north of ``storm_lat``."""

    def __init__(self, storm_lat: float | None = None, mph: float = 50):
        self.storm_lat = storm_lat
        self.mph = mph
        self.calls = []

    def __call__(self, points, start, end):
        self.calls.append((start, end))
        return {
            weather.key_for(p): windy(self.mph) if self.storm_lat is not None and p[0] >= self.storm_lat else calm()
            for p in points
        }


def request(load_lb=20_000, interval=25):
    return TripRequest(
        origin=(40.0, -100.0),
        destination=(40.0, -97.0),
        origin_label="A",
        destination_label="B",
        departure=DEPARTURE,
        load_lb=load_lb,
        interval_mi=interval,
    )


class PlannerTests(SimpleTestCase):
    def setUp(self):
        # Fast route through a windstorm in the north, slower safe route in the south.
        self.routes = [
            straight_route(-97.0, lat=41.0, hours=3),
            straight_route(-97.0, lat=39.0, hours=4, source="alternate"),
            straight_route(-97.0, lat=40.0, hours=5, source="detour"),
        ]

    def plan(self, fake_weather, **kwargs):
        with (
            mock.patch.object(valhalla, "fetch_routes", return_value=self.routes),
            mock.patch.object(weather, "fetch_series", side_effect=fake_weather),
        ):
            return planner.plan_trip(request(**kwargs))

    def test_calm_weather_recommends_fastest(self):
        result = self.plan(FakeWeather())
        self.assertEqual(result["recommended_route_id"], "A")
        self.assertEqual([r["rank"] for r in result["routes"]], [1, 2, 3])
        self.assertIn("faster", result["routes"][0]["reason"])

    def test_storm_on_fast_route_recommends_safe_route(self):
        result = self.plan(FakeWeather(storm_lat=40.5, mph=50))
        a = result["routes"][0]
        self.assertGreater(a["metrics"]["miles_by_level"]["severe"], 0)
        self.assertEqual(result["recommended_route_id"], "B")

    def test_heavy_load_turns_severe_wind_into_no_travel(self):
        result = self.plan(FakeWeather(storm_lat=40.5, mph=50), load_lb=35_000)
        a = result["routes"][0]
        self.assertEqual(a["metrics"]["miles_by_level"]["severe"], 0)
        self.assertGreater(a["metrics"]["miles_by_level"]["no_travel"], 0)
        self.assertEqual(a["metrics"]["max_level"], 4)

    def test_checkpoint_spacing_and_etas(self):
        result = self.plan(FakeWeather(), interval=50)
        cps = result["routes"][0]["checkpoints"]
        miles = [cp["mile"] for cp in cps]
        self.assertEqual(miles[:3], [0.0, 50.0, 100.0])
        self.assertAlmostEqual(miles[-1], result["routes"][0]["distance_mi"], places=0)
        # Constant speed: ETA grows linearly with distance.
        total_mi = result["routes"][0]["distance_mi"]
        eta = datetime.fromisoformat(cps[1]["eta"].replace("Z", "+00:00"))
        self.assertAlmostEqual((eta - DEPARTURE).total_seconds(), 3 * 3600 * 50 / total_mi, delta=2)

    def test_per_level_miles_add_up_to_route_distance(self):
        result = self.plan(FakeWeather(storm_lat=40.5))
        for route in result["routes"]:
            self.assertAlmostEqual(sum(route["metrics"]["miles_by_level"].values()), route["distance_mi"], delta=0.5)

    def test_weather_window_covers_trip_and_slider(self):
        fake = FakeWeather()
        self.plan(fake)
        start, end = fake.calls[0]
        self.assertEqual(start, DEPARTURE)
        self.assertGreaterEqual(end, DEPARTURE + timedelta(hours=48))

    def test_heatmap_has_49_hourly_levels_per_cell(self):
        result = self.plan(FakeWeather(storm_lat=40.5))
        cells = result["heatmap"]["cells"]
        self.assertTrue(cells)
        self.assertTrue(all(len(c["levels"]) == 49 for c in cells))
        self.assertTrue(any("3" in c["levels"] for c in cells))


class PlanApiTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("plan")
        self.departure = (datetime.now(UTC) + timedelta(hours=2)).isoformat()

    def body(self, **overrides):
        body = {
            "origin": {"label": "Chicago, IL", "lat": 41.88, "lon": -87.63},
            "destination": {"label": "Denver, CO", "lat": 39.74, "lon": -104.99},
            "departure": self.departure,
            "load_lb": 25_000,
            "interval_mi": 25,
        }
        body.update(overrides)
        return body

    def test_rejects_unsupported_interval(self):
        resp = self.client.post(self.url, self.body(interval_mi=15), format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("interval_mi", resp.json())

    def test_rejects_past_departure(self):
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        resp = self.client.post(self.url, self.body(departure=past), format="json")
        self.assertEqual(resp.status_code, 400)

    def test_rejects_overweight_load(self):
        resp = self.client.post(self.url, self.body(load_lb=120_000), format="json")
        self.assertEqual(resp.status_code, 400)

    def test_rejects_identical_endpoints(self):
        same = {"label": "Chicago", "lat": 41.88, "lon": -87.63}
        resp = self.client.post(self.url, self.body(origin=same, destination=same), format="json")
        self.assertEqual(resp.status_code, 400)

    def test_successful_plan(self):
        with mock.patch("routing.views.plan_trip", return_value={"routes": []}) as plan_trip:
            resp = self.client.post(self.url, self.body(), format="json")
        self.assertEqual(resp.status_code, 200)
        trip = plan_trip.call_args.args[0]
        self.assertEqual(trip.interval_mi, 25)
        self.assertEqual(trip.origin, (41.88, -87.63))

    def test_provider_errors_are_reported_cleanly(self):
        from routing.services.http import ProviderError

        with mock.patch("routing.views.plan_trip", side_effect=ProviderError("No truck route found.", status=422)):
            resp = self.client.post(self.url, self.body(), format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json(), {"detail": "No truck route found."})
