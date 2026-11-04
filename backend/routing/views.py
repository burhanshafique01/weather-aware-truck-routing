import logging

from rest_framework import status
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from .serializers import PlanRequestSerializer
from .services import geo, geocoding
from .services.http import ProviderError
from .services.planner import TripRequest, plan_trip

log = logging.getLogger(__name__)


class GeocodeThrottle(AnonRateThrottle):
    rate = "120/min"


@api_view(["GET"])
@throttle_classes([])
def health(request):
    return Response({"status": "ok"})


@api_view(["GET"])
@throttle_classes([GeocodeThrottle])
def geocode(request):
    try:
        return Response({"results": geocoding.search(request.query_params.get("q", ""))})
    except ProviderError as exc:
        return Response({"detail": exc.user_message}, status=exc.status)


@api_view(["POST"])
def plan(request):
    serializer = PlanRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        origin = _resolve(data["origin"], "origin")
        destination = _resolve(data["destination"], "destination")
        if geo.haversine_mi((origin["lat"], origin["lon"]), (destination["lat"], destination["lon"])) < 1:
            return Response(
                {"detail": "Origin and destination are the same place."}, status=status.HTTP_400_BAD_REQUEST
            )
        result = plan_trip(
            TripRequest(
                origin=(origin["lat"], origin["lon"]),
                destination=(destination["lat"], destination["lon"]),
                origin_label=origin["label"],
                destination_label=destination["label"],
                departure=data["departure"],
                load_lb=data["load_lb"],
                interval_mi=int(data["interval_mi"]),
            )
        )
    except ProviderError as exc:
        log.warning("plan failed: %s", exc.user_message)
        return Response({"detail": exc.user_message}, status=exc.status)
    return Response(result)


def _resolve(location: dict, which: str) -> dict:
    if "lat" in location:
        return location
    match = geocoding.first(location["label"])
    if match is None:
        raise ProviderError(f"Could not find the {which} “{location['label']}”.", status=422)
    return match
