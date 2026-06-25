import pytest
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile


@pytest.mark.django_db
class TestImageUpload:
    URL = "/api/tools/upload/image/"

    def test_unauthenticated_rejected(self, api_client):
        response = api_client.post(self.URL)
        assert response.status_code == 401

    def test_no_file_returns_400(self, auth_client):
        response = auth_client.post(self.URL)
        assert response.status_code == 400

    def test_invalid_type_returns_400(self, auth_client):
        f = SimpleUploadedFile("malware.exe", b"MZ", content_type="application/x-msdownload")
        response = auth_client.post(self.URL, {"file": f}, format="multipart")
        assert response.status_code == 400
        assert "类型" in response.data["detail"]

    def test_oversized_file_returns_400(self, auth_client):
        f = SimpleUploadedFile("big.png", b"x" * (21 * 1024 * 1024), content_type="image/png")
        response = auth_client.post(self.URL, {"file": f}, format="multipart")
        assert response.status_code == 400
        assert "大小" in response.data["detail"]

    @patch("apps.tools.storage.upload_image")
    def test_valid_upload_returns_id_url_filename(self, mock_upload, auth_client):
        from apps.tools.models import Attachment
        mock_upload.return_value = (
            "http://minio:9000/devtrack-uploads/2026/03/24/abc.png",
            "2026/03/24/abc.png",
        )
        f = SimpleUploadedFile("screenshot.png", b"\x89PNG" + b"\x00" * 100, content_type="image/png")
        response = auth_client.post(self.URL, {"file": f}, format="multipart")
        assert response.status_code == 200
        assert response.data["url"] == "http://minio:9000/devtrack-uploads/2026/03/24/abc.png"
        assert response.data["filename"] == "screenshot.png"
        assert "id" in response.data
        assert Attachment.objects.filter(file_url=response.data["url"]).exists()

    @patch("apps.tools.storage.upload_image")
    def test_pdf_upload_succeeds(self, mock_upload, auth_client):
        mock_upload.return_value = (
            "http://minio:9000/devtrack-uploads/2026/04/29/abc.pdf",
            "2026/04/29/abc.pdf",
        )
        f = SimpleUploadedFile("report.pdf", b"%PDF-1.4\n%test", content_type="application/pdf")
        response = auth_client.post(self.URL, {"file": f}, format="multipart")
        assert response.status_code == 200
        assert response.data["filename"] == "report.pdf"

    @patch("apps.tools.storage.upload_image")
    def test_docx_upload_succeeds(self, mock_upload, auth_client):
        mock_upload.return_value = (
            "http://minio:9000/devtrack-uploads/2026/04/29/abc.docx",
            "2026/04/29/abc.docx",
        )
        f = SimpleUploadedFile(
            "spec.docx",
            b"PK\x03\x04",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response = auth_client.post(self.URL, {"file": f}, format="multipart")
        assert response.status_code == 200

    @patch("apps.tools.storage.upload_image")
    def test_zip_upload_succeeds(self, mock_upload, auth_client):
        mock_upload.return_value = (
            "http://minio:9000/devtrack-uploads/2026/04/29/abc.zip",
            "2026/04/29/abc.zip",
        )
        f = SimpleUploadedFile("bundle.zip", b"PK\x03\x04", content_type="application/zip")
        response = auth_client.post(self.URL, {"file": f}, format="multipart")
        assert response.status_code == 200

    @patch("apps.tools.storage.upload_image")
    def test_markdown_with_textplain_succeeds(self, mock_upload, auth_client):
        """Some browsers report .md files as text/plain — allow if extension matches."""
        mock_upload.return_value = (
            "http://minio:9000/devtrack-uploads/2026/04/29/abc.md",
            "2026/04/29/abc.md",
        )
        f = SimpleUploadedFile("notes.md", b"# Hello", content_type="text/plain")
        response = auth_client.post(self.URL, {"file": f}, format="multipart")
        assert response.status_code == 200

    @patch("apps.tools.storage.upload_image")
    def test_plain_txt_succeeds(self, mock_upload, auth_client):
        mock_upload.return_value = (
            "http://minio:9000/devtrack-uploads/2026/04/29/abc.txt",
            "2026/04/29/abc.txt",
        )
        f = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
        response = auth_client.post(self.URL, {"file": f}, format="multipart")
        assert response.status_code == 200

    @patch("apps.tools.storage.upload_image")
    def test_html_upload_succeeds(self, mock_upload, auth_client):
        from apps.tools.models import Attachment
        mock_upload.return_value = (
            "http://minio:9000/devtrack-uploads/2026/06/25/abc.html",
            "2026/06/25/abc.html",
        )
        f = SimpleUploadedFile(
            "root-cause.html",
            b"<!doctype html><h1>hi</h1>",
            content_type="text/html",
        )
        response = auth_client.post(self.URL, {"file": f}, format="multipart")
        assert response.status_code == 200
        assert response.data["filename"] == "root-cause.html"
        att = Attachment.objects.get(id=response.data["id"])
        assert att.mime_type == "text/html"

    @patch("apps.tools.storage.upload_image")
    def test_htm_with_empty_type_succeeds_via_extension(self, mock_upload, auth_client):
        """个别浏览器对 .htm 上报空 content_type — 靠扩展名兜底放行。"""
        mock_upload.return_value = (
            "http://minio:9000/devtrack-uploads/2026/06/25/abc.htm",
            "2026/06/25/abc.htm",
        )
        f = SimpleUploadedFile("page.htm", b"<html></html>", content_type="")
        response = auth_client.post(self.URL, {"file": f}, format="multipart")
        assert response.status_code == 200


@pytest.mark.django_db
class TestImageUploadDedup:
    """同 user 上传相同 bytes 时复用已有 Attachment, 节省存储 + 让 LLM 不会看到两份同图。"""
    URL = "/api/tools/upload/image/"

    @patch("apps.tools.storage.upload_image")
    def test_same_bytes_returns_same_attachment_id(self, mock_upload, auth_client):
        """同 user 第二次上传相同 bytes 应返回首次的 id, 不写 storage, DB 不新增行。"""
        from apps.tools.models import Attachment
        mock_upload.return_value = ("http://minio/x.png", "2026/05/x.png")

        f1 = SimpleUploadedFile("a.png", b"\x89PNG\r\n\x1a\nidentical", content_type="image/png")
        r1 = auth_client.post(self.URL, {"file": f1}, format="multipart")
        assert r1.status_code == 200
        id1 = r1.data["id"]
        assert r1.data.get("deduped") is not True
        assert mock_upload.call_count == 1
        assert Attachment.objects.count() == 1

        # 第二次上传相同 bytes (文件名不同也无所谓 — hash 一样)
        f2 = SimpleUploadedFile("b.png", b"\x89PNG\r\n\x1a\nidentical", content_type="image/png")
        r2 = auth_client.post(self.URL, {"file": f2}, format="multipart")
        assert r2.status_code == 200
        assert r2.data["id"] == id1, "同 bytes 应复用 attachment id"
        assert r2.data["deduped"] is True
        assert mock_upload.call_count == 1, "dedup 时不应再写 storage"
        assert Attachment.objects.count() == 1, "DB 不应新增行"

    @patch("apps.tools.storage.upload_image")
    def test_different_bytes_returns_different_ids(self, mock_upload, auth_client):
        from apps.tools.models import Attachment
        mock_upload.side_effect = [
            ("http://minio/a.png", "2026/05/a.png"),
            ("http://minio/b.png", "2026/05/b.png"),
        ]

        r1 = auth_client.post(
            self.URL,
            {"file": SimpleUploadedFile("a.png", b"\x89PNGcontent-a", content_type="image/png")},
            format="multipart",
        )
        r2 = auth_client.post(
            self.URL,
            {"file": SimpleUploadedFile("b.png", b"\x89PNGcontent-b", content_type="image/png")},
            format="multipart",
        )
        assert r1.data["id"] != r2.data["id"]
        assert Attachment.objects.count() == 2

    @patch("apps.tools.storage.upload_image")
    def test_dedup_scoped_to_uploader(self, mock_upload, api_client):
        """不同 user 上传相同 bytes 各自得到独立 attachment - 避免跨用户权限混淆。"""
        from apps.tools.models import Attachment
        from tests.factories import UserFactory
        mock_upload.side_effect = [
            ("http://minio/x1.png", "2026/05/x1.png"),
            ("http://minio/x2.png", "2026/05/x2.png"),
        ]

        user_a = UserFactory()
        user_b = UserFactory()
        same_bytes = b"\x89PNGshared-bytes"

        api_client.force_authenticate(user_a)
        r_a = api_client.post(
            self.URL,
            {"file": SimpleUploadedFile("x.png", same_bytes, content_type="image/png")},
            format="multipart",
        )
        api_client.force_authenticate(user_b)
        r_b = api_client.post(
            self.URL,
            {"file": SimpleUploadedFile("x.png", same_bytes, content_type="image/png")},
            format="multipart",
        )
        assert r_a.data["id"] != r_b.data["id"]
        assert Attachment.objects.count() == 2

    @patch("apps.tools.storage.upload_image")
    def test_content_hash_stored_for_new_uploads(self, mock_upload, auth_client):
        """新上传 attachment 必须落 content_hash, 否则下次重复上传 dedup 不工作。"""
        import hashlib
        from apps.tools.models import Attachment
        mock_upload.return_value = ("http://minio/x.png", "2026/05/x.png")

        body = b"\x89PNGbytes-for-hash-check"
        expected = hashlib.sha256(body).hexdigest()
        r = auth_client.post(
            self.URL,
            {"file": SimpleUploadedFile("x.png", body, content_type="image/png")},
            format="multipart",
        )
        att = Attachment.objects.get(id=r.data["id"])
        assert att.content_hash == expected


class TestStorageMimeSafety:
    """安全约定: HTML 绝不能以 text/html 从公网 URL 下发, 否则公网链接 = 存储型 XSS。
    storage 按扩展名推导 Content-Type; html/htm 必须落到 octet-stream(走默认兜底)。"""

    def test_html_never_served_as_text_html(self):
        from apps.tools import storage
        assert storage.EXT_TO_MIME.get("html", "application/octet-stream") == "application/octet-stream"
        assert storage.EXT_TO_MIME.get("htm", "application/octet-stream") == "application/octet-stream"
