import pytest
from tests.factories import AttachmentFactory


@pytest.mark.django_db
class TestAttachmentModel:
    def test_attachment_str(self):
        a = AttachmentFactory(file_name="screenshot.png")
        assert str(a) == "screenshot.png"

    def test_is_image_true(self):
        a = AttachmentFactory(mime_type="image/png")
        assert a.is_image is True

    def test_is_image_false(self):
        a = AttachmentFactory(mime_type="application/pdf")
        assert a.is_image is False

    def test_attachment_survives_user_deletion(self):
        """uploaded_by SET_NULL: deleting user keeps attachment"""
        from tests.factories import UserFactory
        user = UserFactory()
        a = AttachmentFactory(uploaded_by=user)
        user.delete()
        a.refresh_from_db()
        assert a.uploaded_by is None

    def test_attachment_linked_to_issue_via_m2m(self):
        """M2M: attachment linked to issue, auto-removed when attachment deleted"""
        from tests.factories import IssueFactory
        issue = IssueFactory()
        att = AttachmentFactory()
        issue.attachments.add(att)
        assert issue.attachments.filter(id=att.id).exists()
        att.delete()
        assert not issue.attachments.filter(id=att.id).exists()


@pytest.mark.django_db
class TestAttachmentSync:
    def test_create_issue_links_matching_attachments(self, auth_client, auth_user, site_settings, settings):
        from apps.issues.models import Issue
        from tests.factories import ProjectFactory
        project = ProjectFactory()
        att = AttachmentFactory(
            uploaded_by=auth_user,
            file_url="http://minio:9000/devtrack-uploads/2026/03/27/abc.png",
        )
        response = auth_client.post("/api/issues/", {
            "project": project.id,
            "title": "测试问题",
            "description": "截图: ![img](http://minio:9000/devtrack-uploads/2026/03/27/abc.png)",
            "priority": "P1",
            "status": "待分配",
            "labels": [],
            "attachment_ids": [str(att.id)],
        }, format="json")
        assert response.status_code == 201
        issue = Issue.objects.get(id=response.data["id"])
        assert issue.attachments.filter(id=att.id).exists()

    def test_create_issue_links_attachments_by_id(self, auth_client, auth_user, site_settings):
        from apps.issues.models import Issue
        from tests.factories import ProjectFactory
        project = ProjectFactory()
        att1 = AttachmentFactory(uploaded_by=auth_user, file_url="/uploads/2026/04/02/a.png")
        att2 = AttachmentFactory(uploaded_by=auth_user, file_url="/uploads/2026/04/02/b.png")
        other_user_att = AttachmentFactory(file_url="/uploads/2026/04/02/c.png")
        response = auth_client.post("/api/issues/", {
            "project": project.id,
            "title": "附件测试",
            "description": "![a](/uploads/2026/04/02/a.png)",
            "priority": "P1",
            "status": "待分配",
            "labels": [],
            "attachment_ids": [str(att1.id), str(att2.id), str(other_user_att.id)],
        }, format="json")
        assert response.status_code == 201
        issue = Issue.objects.get(id=response.data["id"])
        linked = set(issue.attachments.values_list("id", flat=True))
        # Only att1 and att2 linked (owned by auth_user), other_user_att filtered out
        assert att1.id in linked
        assert att2.id in linked
        assert other_user_att.id not in linked

    def test_detail_response_includes_attachments(self, auth_client, site_settings):
        from tests.factories import IssueFactory
        issue = IssueFactory()
        att1 = AttachmentFactory()
        att2 = AttachmentFactory()
        issue.attachments.add(att1, att2)
        response = auth_client.get(f"/api/issues/{issue.id}/")
        assert response.status_code == 200
        assert len(response.data["attachments"]) == 2

    def test_update_issue_links_new_attachments(self, auth_client, auth_user, site_settings, settings):
        from tests.factories import IssueFactory
        settings.MINIO_PUBLIC_URL = "http://minio:9000"
        issue = IssueFactory()
        att = AttachmentFactory(
            uploaded_by=auth_user,
            file_url="http://minio:9000/devtrack-uploads/2026/03/27/xyz.png",
        )
        response = auth_client.patch(f"/api/issues/{issue.id}/", {
            "description": "更新: ![img](http://minio:9000/devtrack-uploads/2026/03/27/xyz.png)",
        }, format="json")
        assert response.status_code == 200
        issue.refresh_from_db()
        assert issue.attachments.filter(id=att.id).exists()


@pytest.mark.django_db
class TestIssueAttachmentsAPI:
    def test_link_attachment_to_issue(self, auth_client):
        from tests.factories import IssueFactory
        issue = IssueFactory()
        att = AttachmentFactory()
        response = auth_client.post(
            f"/api/issues/{issue.id}/attachments/",
            {"attachment_id": str(att.id)},
            format="json",
        )
        assert response.status_code == 204
        assert issue.attachments.filter(id=att.id).exists()

    def test_unlink_attachment_from_issue(self, auth_client):
        from tests.factories import IssueFactory
        issue = IssueFactory()
        att = AttachmentFactory()
        issue.attachments.add(att)
        response = auth_client.delete(
            f"/api/issues/{issue.id}/attachments/",
            {"attachment_id": str(att.id)},
            format="json",
        )
        assert response.status_code == 204
        assert not issue.attachments.filter(id=att.id).exists()

    def test_unlink_does_not_delete_attachment(self, auth_client):
        from tests.factories import IssueFactory
        from apps.tools.models import Attachment
        issue = IssueFactory()
        att = AttachmentFactory()
        issue.attachments.add(att)
        auth_client.delete(
            f"/api/issues/{issue.id}/attachments/",
            {"attachment_id": str(att.id)},
            format="json",
        )
        assert Attachment.objects.filter(id=att.id).exists()


@pytest.mark.django_db
class TestAttachmentDeleteAPI:
    def test_delete_attachment_removes_from_db_and_calls_minio(self, auth_client, auth_user):
        from unittest.mock import patch
        from apps.tools.models import Attachment
        att = AttachmentFactory(uploaded_by=auth_user, file_key="2026/03/27/test.png")

        with patch("apps.tools.storage.delete_object") as mock_del:
            response = auth_client.delete(f"/api/tools/attachments/{att.id}/")
        assert response.status_code == 204
        mock_del.assert_called_once_with("2026/03/27/test.png")
        assert not Attachment.objects.filter(id=att.id).exists()

    def test_delete_forbidden_for_other_user(self, auth_client):
        from tests.factories import UserFactory
        other_user = UserFactory()
        att = AttachmentFactory(uploaded_by=other_user)
        response = auth_client.delete(f"/api/tools/attachments/{att.id}/")
        assert response.status_code == 403

    def test_delete_nonexistent_returns_404(self, auth_client):
        import uuid
        response = auth_client.delete(f"/api/tools/attachments/{uuid.uuid4()}/")
        assert response.status_code == 404

    def test_staff_can_delete_others_attachment(self, superuser_client):
        from unittest.mock import patch
        from tests.factories import UserFactory
        from apps.tools.models import Attachment
        owner = UserFactory()
        att = AttachmentFactory(uploaded_by=owner, file_key="2026/03/27/staff.png")

        with patch("apps.tools.storage.delete_object") as mock_del:
            response = superuser_client.delete(f"/api/tools/attachments/{att.id}/")
        assert response.status_code == 204
        mock_del.assert_called_once_with("2026/03/27/staff.png")
        assert not Attachment.objects.filter(id=att.id).exists()

    def test_unauthenticated_delete_rejected(self, api_client):
        att = AttachmentFactory()
        response = api_client.delete(f"/api/tools/attachments/{att.id}/")
        assert response.status_code == 401
