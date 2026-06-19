import hashlib

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.tools.models import Attachment
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestUploadToStorageService:
    """共享的 校验+上传 服务: API 视图与 admin 上传共用一条代码路径。"""

    def test_returns_attachment_field_values(self):
        from unittest.mock import patch
        from apps.tools import services

        body = b"\x89PNGservice-bytes"
        with patch("apps.tools.storage.upload_image") as mock_upload:
            mock_upload.return_value = (
                "http://minio/devtrack-uploads/2026/06/19/abc.png",
                "2026/06/19/abc.png",
            )
            f = SimpleUploadedFile("pic.png", body, content_type="image/png")
            data = services.upload_to_storage(f)

        assert data["file_url"] == "http://minio/devtrack-uploads/2026/06/19/abc.png"
        assert data["file_key"] == "2026/06/19/abc.png"
        assert data["file_name"] == "pic.png"
        assert data["file_size"] == len(body)
        assert data["mime_type"] == "image/png"
        assert data["content_hash"] == hashlib.sha256(body).hexdigest()

    def test_validate_rejects_disallowed_type(self):
        from apps.tools import services

        f = SimpleUploadedFile("x.exe", b"MZ", content_type="application/x-msdownload")
        with pytest.raises(ValidationError):
            services.validate_upload(f)

    def test_validate_rejects_oversized(self):
        from apps.tools import services

        f = SimpleUploadedFile("big.png", b"x" * (21 * 1024 * 1024), content_type="image/png")
        with pytest.raises(ValidationError):
            services.validate_upload(f)


class TestAttachmentAdminUpload:
    ADD_URL = "/api/admin/tools/attachment/add/"

    @pytest.fixture(autouse=True)
    def _plain_static_storage(self, settings):
        # admin 页面渲染要解析 {% static %}; 测试环境没 collectstatic 的 manifest,
        # 换成不依赖 manifest 的存储, 否则渲染抛 "Missing staticfiles manifest entry"。
        settings.STORAGES = {
            **settings.STORAGES,
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
            },
        }

    def _admin_client(self):
        admin = UserFactory(is_staff=True, is_superuser=True)
        client = Client()
        client.force_login(admin)
        return client, admin

    def test_admin_can_upload_a_file(self):
        from unittest.mock import patch

        client, admin = self._admin_client()
        body = b"%PDF-1.4 admin upload"
        with patch("apps.tools.storage.upload_image") as mock_upload:
            mock_upload.return_value = (
                "http://minio/devtrack-uploads/2026/06/19/admin.pdf",
                "2026/06/19/admin.pdf",
            )
            f = SimpleUploadedFile("report.pdf", body, content_type="application/pdf")
            resp = client.post(self.ADD_URL, {"upload": f}, follow=True)

        assert resp.status_code == 200
        att = Attachment.objects.get()
        assert att.file_name == "report.pdf"
        assert att.file_url == "http://minio/devtrack-uploads/2026/06/19/admin.pdf"
        assert att.file_key == "2026/06/19/admin.pdf"
        assert att.file_size == len(body)
        assert att.mime_type == "application/pdf"
        # uploaded_by 未填时默认归到当前登录的管理员
        assert att.uploaded_by == admin
        assert att.content_hash == hashlib.sha256(body).hexdigest()
        mock_upload.assert_called_once()

    def test_admin_rejects_disallowed_type(self):
        from unittest.mock import patch

        client, _ = self._admin_client()
        with patch("apps.tools.storage.upload_image") as mock_upload:
            f = SimpleUploadedFile("malware.exe", b"MZ", content_type="application/x-msdownload")
            resp = client.post(self.ADD_URL, {"upload": f})

        # 校验失败 → 表单带错误重渲染, 不创建记录, 不写 storage
        assert resp.status_code == 200
        assert Attachment.objects.count() == 0
        mock_upload.assert_not_called()
