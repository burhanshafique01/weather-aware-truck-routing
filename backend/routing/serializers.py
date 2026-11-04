from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

MAX_LOAD_LB = 80_000
MAX_DAYS_AHEAD = 7
CHECKPOINT_INTERVALS = (10, 25, 50)


class LocationSerializer(serializers.Serializer):
    """A place. Coordinates are optional: without them the label is geocoded."""

    label = serializers.CharField(max_length=200, trim_whitespace=True)
    lat = serializers.FloatField(min_value=-90, max_value=90, required=False)
    lon = serializers.FloatField(min_value=-180, max_value=180, required=False)

    def validate(self, attrs):
        if ("lat" in attrs) != ("lon" in attrs):
            raise serializers.ValidationError("Provide both lat and lon, or neither.")
        return attrs


class PlanRequestSerializer(serializers.Serializer):
    origin = LocationSerializer()
    destination = LocationSerializer()
    departure = serializers.DateTimeField()
    load_lb = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LB)
    interval_mi = serializers.ChoiceField(choices=CHECKPOINT_INTERVALS, default=25)

    def validate_departure(self, value):
        now = timezone.now()
        if value < now - timedelta(hours=1):
            raise serializers.ValidationError("Departure must not be in the past.")
        if value > now + timedelta(days=MAX_DAYS_AHEAD):
            raise serializers.ValidationError(
                f"Departure must be within {MAX_DAYS_AHEAD} days so the forecast covers the whole trip."
            )
        return value
