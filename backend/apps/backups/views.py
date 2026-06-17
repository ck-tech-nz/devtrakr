import os

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.generics import (
    ListAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView, DestroyAPIView,
)
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.backups.models import BackupTarget, DatabaseBackup
from apps.backups.serializers import BackupTargetSerializer, DatabaseBackupSerializer
from apps.backups.services import get_backup_dir
from apps.backups.tasks import run_backup


class BackupTargetListCreateView(ListCreateAPIView):
    serializer_class = BackupTargetSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = BackupTarget.objects.select_related("project").all()
        project = self.request.query_params.get("project")
        if project:
            qs = qs.filter(project_id=project)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class BackupTargetDetailView(RetrieveUpdateDestroyAPIView):
    queryset = BackupTarget.objects.all()
    serializer_class = BackupTargetSerializer
    permission_classes = [IsAdminUser]


class BackupTargetRunView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        target = get_object_or_404(BackupTarget, pk=pk, is_active=True)
        if DatabaseBackup.objects.filter(target=target, status="running").exists():
            return Response({"detail": "已有备份任务正在运行"}, status=status.HTTP_409_CONFLICT)
        run_backup.delay(target.id, trigger="manual", created_by_id=request.user.id)
        return Response({"detail": "已开始备份"}, status=status.HTTP_202_ACCEPTED)


class BackupListView(ListAPIView):
    serializer_class = DatabaseBackupSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = DatabaseBackup.objects.select_related("target", "created_by").all()
        target = self.request.query_params.get("target")
        project = self.request.query_params.get("project")
        if target:
            qs = qs.filter(target_id=target)
        if project:
            qs = qs.filter(target__project_id=project)
        return qs


class BackupDownloadView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        backup = get_object_or_404(DatabaseBackup, pk=pk)
        filepath = os.path.join(get_backup_dir(), backup.filename)
        if not os.path.exists(filepath):
            return Response({"detail": "备份文件不存在"}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(
            open(filepath, "rb"),
            content_type="application/octet-stream",
            as_attachment=True,
            filename=backup.filename,
        )


class BackupDeleteView(DestroyAPIView):
    queryset = DatabaseBackup.objects.all()
    serializer_class = DatabaseBackupSerializer
    permission_classes = [IsAdminUser]

    def perform_destroy(self, instance):
        filepath = os.path.join(get_backup_dir(), instance.filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        instance.delete()
