from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

import apps.tools.storage as tools_storage
from . import services
from .models import Attachment


class ImageUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"detail": "未提供文件"}, status=400)
        if not services.is_allowed(file):
            return Response(
                {"detail": f"不支持的文件类型: {file.content_type}"},
                status=400,
            )
        if file.size > services.MAX_SIZE:
            return Response(
                {"detail": "文件大小超过限制 (20MB)"},
                status=400,
            )

        # 内容去重: 同用户上传同 bytes → 复用已有 Attachment, 不再写 MinIO,
        # 也避免 LLM 之后看到两份同图。dedup 限于同 uploaded_by, 避免跨用户权限泄漏。
        content_hash = services.sha256_of_uploaded(file)
        existing = Attachment.objects.filter(
            uploaded_by=request.user,
            content_hash=content_hash,
        ).first()
        if existing is not None:
            return Response({
                "url": existing.file_url,
                "filename": existing.file_name,
                "id": str(existing.id),
                "deduped": True,
            })

        url, key = tools_storage.upload_image(file)

        attachment = Attachment.objects.create(
            uploaded_by=request.user,
            file_name=file.name,
            file_key=key,
            file_url=url,
            file_size=file.size,
            mime_type=file.content_type,
            content_hash=content_hash,
        )

        return Response({"url": url, "filename": file.name, "id": str(attachment.id)})


class AttachmentDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        attachment = Attachment.objects.filter(pk=pk).first()
        if not attachment:
            return Response({"detail": "附件不存在"}, status=404)
        if attachment.uploaded_by != request.user and not request.user.is_staff:
            return Response({"detail": "无权限删除此附件"}, status=403)
        tools_storage.delete_object(attachment.file_key)
        attachment.delete()
        return Response(status=204)
