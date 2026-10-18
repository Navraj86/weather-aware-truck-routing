from datetime import datetime, timedelta, timezone

from rest_framework import serializers

from .domain.checkpoints import ALLOWED_INTERVALS_MI

MAX_DEPARTURE_AHEAD = timedelta(days=7)
MAX_DEPARTURE_PAST = timedelta(hours=1)
MAX_LOAD_LB = 150_000


class PointSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    label = serializers.CharField(required=False, allow_blank=True, max_length=200)


def _validate_departure(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if value < now - MAX_DEPARTURE_PAST:
        raise serializers.ValidationError("Departure cannot be in the past.")
    if value > now + MAX_DEPARTURE_AHEAD:
        raise serializers.ValidationError("Departure must be within the next 7 days (forecast range).")
    return value.astimezone(timezone.utc)


class PlanRequestSerializer(serializers.Serializer):
    origin = PointSerializer()
    destination = PointSerializer()
    departure = serializers.DateTimeField()
    load_lb = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LB)
    interval_mi = serializers.ChoiceField(choices=ALLOWED_INTERVALS_MI, default=25)
    hos = serializers.BooleanField(default=False)

    def validate_departure(self, value):
        return _validate_departure(value)

    def validate(self, attrs):
        o, d = attrs["origin"], attrs["destination"]
        if abs(o["lat"] - d["lat"]) < 1e-4 and abs(o["lon"] - d["lon"]) < 1e-4:
            raise serializers.ValidationError("Origin and destination must be different places.")
        return attrs


class HeatmapRequestSerializer(serializers.Serializer):
    corridors = serializers.ListField(
        child=serializers.ListField(
            child=serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2),
            min_length=2,
            max_length=2000,
        ),
        min_length=1,
        max_length=3,
    )
    departure = serializers.DateTimeField()
    load_lb = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LB)

    def validate_departure(self, value):
        return _validate_departure(value)

    def validate_corridors(self, value):
        for line in value:
            for lat, lon in line:
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise serializers.ValidationError("Corridor coordinates must be [lat, lon] pairs.")
        return value
