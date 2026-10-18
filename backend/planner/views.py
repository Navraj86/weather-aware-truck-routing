import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import HeatmapRequestSerializer, PlanRequestSerializer
from .services import geocoding
from .services.heatmap import build_heatmap
from .services.http import UpstreamError
from .services.planner import TripRequest, plan_trip

log = logging.getLogger(__name__)


def health(request):
    return JsonResponse({"status": "ok"})


def spa_index(request):
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        return HttpResponse("Frontend not built. Run `npm run build` in frontend/.", status=404, content_type="text/plain")
    return HttpResponse(index.read_bytes(), content_type="text/html")


def upstream_error(exc: UpstreamError) -> Response:
    log.warning("Upstream failure: %s", exc)
    return Response({"error": exc.message, "service": exc.service}, status=exc.status)


class GeocodeView(APIView):
    throttle_scope = "geocode"

    def get(self, request):
        q = request.query_params.get("q", "").strip()
        if len(q) < 2:
            return Response({"results": []})
        try:
            return Response({"results": geocoding.search(q[:200])})
        except UpstreamError as exc:
            return upstream_error(exc)


class PlanView(APIView):
    throttle_scope = "plan"

    def post(self, request):
        s = PlanRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        trip = TripRequest(
            origin=(v["origin"]["lat"], v["origin"]["lon"]),
            destination=(v["destination"]["lat"], v["destination"]["lon"]),
            departure=v["departure"],
            load_lb=v["load_lb"],
            interval_mi=int(v["interval_mi"]),
            hos=v["hos"],
        )
        try:
            return Response(plan_trip(trip))
        except UpstreamError as exc:
            return upstream_error(exc)


class HeatmapView(APIView):
    throttle_scope = "plan"

    def post(self, request):
        s = HeatmapRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        corridors = [[(p[0], p[1]) for p in line] for line in v["corridors"]]
        try:
            return Response(build_heatmap(corridors, v["departure"], v["load_lb"]))
        except UpstreamError as exc:
            return upstream_error(exc)
