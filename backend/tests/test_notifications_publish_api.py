import pytest
from tests.factories import NotificationFactory, UserFactory

pytestmark = pytest.mark.django_db


class TestManagePublishEndpoint:
    """回归覆盖 ManagePublishView.post —— 该端点此前误调用未定义的
    _generate_recipients,发布任意草稿都会抛 NameError(且无测试守护)。"""

    def url(self, pk):
        return f"/api/notifications/manage/{pk}/publish/"

    def test_publish_draft_generates_recipients(self, auth_client):
        UserFactory()  # 额外 active 用户,作为 target_type=all 的接收人
        notif = NotificationFactory(target_type="all", is_draft=True)
        res = auth_client.post(self.url(notif.id))
        assert res.status_code == 200
        assert res.data["recipients"] >= 1
        notif.refresh_from_db()
        assert notif.is_draft is False

    def test_publish_already_published_rejected(self, auth_client):
        notif = NotificationFactory(target_type="all", is_draft=False)
        res = auth_client.post(self.url(notif.id))
        assert res.status_code == 400

    def test_publish_missing_notification_404(self, auth_client):
        import uuid
        res = auth_client.post(self.url(uuid.uuid4()))
        assert res.status_code == 404

    def test_publish_forbidden_without_permission(self, regular_client):
        notif = NotificationFactory(target_type="all", is_draft=True)
        res = regular_client.post(self.url(notif.id))
        assert res.status_code == 403
