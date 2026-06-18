import pytest
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestProfileUpdate:
    def test_update_name_and_email(self, api_client):
        user = UserFactory()
        api_client.force_authenticate(user=user)
        response = api_client.patch("/api/auth/me/", {
            "name": "新昵称",
            "email": "newemail@example.com",
        }, format="json")
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.name == "新昵称"
        assert user.email == "newemail@example.com"

    def test_update_avatar(self, api_client):
        user = UserFactory()
        api_client.force_authenticate(user=user)
        response = api_client.patch("/api/auth/me/", {
            "avatar": "docker-whale",
        }, format="json")
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.avatar == "docker-whale"

    def test_update_avatar_uploaded_url(self, api_client, settings):
        # 上传头像存的是本站 MinIO 公网 URL,应被接受
        settings.MINIO_PUBLIC_URL = "/uploads"
        user = UserFactory()
        api_client.force_authenticate(user=user)
        url = "/uploads/2026/06/19/abc123def456.png"
        response = api_client.patch("/api/auth/me/", {"avatar": url}, format="json")
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.avatar == url

    def test_update_avatar_rejects_external_url(self, api_client, settings):
        # 非本站地址应被拒绝(防止指向任意外部 URL)
        settings.MINIO_PUBLIC_URL = "/uploads"
        user = UserFactory()
        api_client.force_authenticate(user=user)
        response = api_client.patch(
            "/api/auth/me/",
            {"avatar": "https://evil.example.com/x.png"},
            format="json",
        )
        assert response.status_code == 400
        assert "avatar" in response.data

    def test_update_avatar_rejects_non_image_upload(self, api_client, settings):
        # 本站上传但非图片(如 PDF)应被拒绝
        settings.MINIO_PUBLIC_URL = "/uploads"
        user = UserFactory()
        api_client.force_authenticate(user=user)
        response = api_client.patch(
            "/api/auth/me/",
            {"avatar": "/uploads/2026/06/19/doc.pdf"},
            format="json",
        )
        assert response.status_code == 400
        assert "avatar" in response.data

    def test_update_settings(self, api_client):
        user = UserFactory()
        api_client.force_authenticate(user=user)
        response = api_client.patch("/api/auth/me/", {
            "settings": {"theme": "dark", "sidebar_auto_collapse": True},
        }, format="json")
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.settings["theme"] == "dark"


class TestChangePassword:
    URL = "/api/auth/me/change-password/"

    def test_change_password_success(self, api_client):
        user = UserFactory()
        api_client.force_authenticate(user=user)
        response = api_client.post(self.URL, {
            "current_password": "testpass123",
            "new_password": "NewStrongPass456!",
            "new_password_confirm": "NewStrongPass456!",
        })
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.check_password("NewStrongPass456!")

    def test_change_password_wrong_current(self, api_client):
        user = UserFactory()
        api_client.force_authenticate(user=user)
        response = api_client.post(self.URL, {
            "current_password": "wrongpassword",
            "new_password": "NewStrongPass456!",
            "new_password_confirm": "NewStrongPass456!",
        })
        assert response.status_code == 400
        assert "current_password" in response.data

    def test_change_password_mismatch(self, api_client):
        user = UserFactory()
        api_client.force_authenticate(user=user)
        response = api_client.post(self.URL, {
            "current_password": "testpass123",
            "new_password": "NewStrongPass456!",
            "new_password_confirm": "DifferentPass789!",
        })
        assert response.status_code == 400

    def test_change_password_unauthenticated(self, api_client):
        response = api_client.post(self.URL, {
            "current_password": "x",
            "new_password": "y",
            "new_password_confirm": "y",
        })
        assert response.status_code == 401
