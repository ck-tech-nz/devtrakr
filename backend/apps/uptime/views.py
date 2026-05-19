from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.uptime.models import UptimeMonitor, UptimeCheck
from apps.uptime.permissions import IsSuperUserOrReadOnly
from apps.uptime.serializers import UptimeMonitorSerializer, UptimeCheckSerializer


class UptimeMonitorListView(generics.ListAPIView):
    """Flat listing of all monitors across projects (read-only, used by home page widget)."""
    queryset = UptimeMonitor.objects.select_related("project").all()
    serializer_class = UptimeMonitorSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class UptimeMonitorDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = UptimeMonitor.objects.all()
    serializer_class = UptimeMonitorSerializer
    permission_classes = [IsAuthenticated, IsSuperUserOrReadOnly]


class UptimeMonitorChecksView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            limit = int(request.query_params.get("limit", 60))
        except ValueError:
            limit = 60
        limit = max(1, min(limit, 500))
        checks = (
            UptimeCheck.objects
            .filter(monitor_id=pk)
            .order_by("-checked_at")[:limit]
        )
        return Response(UptimeCheckSerializer(checks, many=True).data)
