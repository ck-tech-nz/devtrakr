import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from apps.issues.models import IssueComment
from tests.factories import IssueCommentFactory, IssueFactory, UserFactory

pytestmark = pytest.mark.django_db


# ---------- 本文件公用夹具 ----------

@pytest.fixture
def author():
    return UserFactory()


@pytest.fixture
def author_client(author):
    client = APIClient()
    client.force_authenticate(user=author)
    return client


@pytest.fixture
def other_client():
    client = APIClient()
    client.force_authenticate(user=UserFactory())
    return client


@pytest.fixture
def admin_client():
    user = UserFactory()
    group, _ = Group.objects.get_or_create(name="管理员")
    user.groups.add(group)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def issue():
    return IssueFactory()


def mention(user) -> str:
    """构造一条 @提及 文本，格式同前端 MentionDropdown 插入的格式。"""
    return f"@[{user.name or user.username}](user:{user.id})"


class TestIssueCommentModel:
    def test_ordering_oldest_first(self, issue, author):
        from datetime import timedelta
        from django.utils import timezone
        c1 = IssueCommentFactory(issue=issue, author=author)
        c2 = IssueCommentFactory(issue=issue, author=author)
        # 把 c2 回拨到 c1 之前,验证排序确实按 created_at 而非插入顺序
        IssueComment.objects.filter(pk=c2.pk).update(
            created_at=timezone.now() - timedelta(minutes=5),
        )
        assert list(issue.comments.all()) == [c2, c1]

    def test_str(self, issue, author):
        c = IssueCommentFactory(issue=issue, author=author, content="x" * 100)
        assert str(c).startswith(f"#{issue.pk} ")


class TestCommentMentionService:
    def _call(self, comment, old_content, actor):
        from apps.notifications.services import create_comment_mention_notifications
        create_comment_mention_notifications(
            comment=comment, old_content=old_content,
            new_content=comment.content, actor=actor,
        )

    def test_notifies_newly_mentioned_user(self, issue, author):
        from apps.notifications.models import Notification
        target = UserFactory()
        comment = IssueCommentFactory(
            issue=issue, author=author, content=f"请看 {mention(target)}",
        )
        self._call(comment, old_content="", actor=author)

        n = Notification.objects.filter(
            notification_type=Notification.Type.MENTION, source_issue=issue,
        ).first()
        assert n is not None
        assert f"#{issue.pk} 的评论中提到了你" in n.title
        assert n.source_user == author
        assert n.recipients.filter(user=target).exists()
        assert Notification.objects.count() == 1

    def test_self_mention_not_notified(self, issue, author):
        from apps.notifications.models import Notification
        comment = IssueCommentFactory(
            issue=issue, author=author, content=f"自言自语 {mention(author)}",
        )
        self._call(comment, old_content="", actor=author)
        assert Notification.objects.count() == 0

    def test_already_mentioned_in_old_content_not_renotified(self, issue, author):
        from apps.notifications.models import Notification
        target = UserFactory()
        comment = IssueCommentFactory(
            issue=issue, author=author, content=f"再次 {mention(target)}",
        )
        self._call(comment, old_content=f"之前 {mention(target)}", actor=author)
        assert Notification.objects.count() == 0

    def test_inactive_user_not_notified(self, issue, author):
        from apps.notifications.models import Notification
        target = UserFactory(is_active=False)
        comment = IssueCommentFactory(
            issue=issue, author=author, content=mention(target),
        )
        self._call(comment, old_content="", actor=author)
        assert Notification.objects.count() == 0

    def test_multiple_mentions_notify_each_user_once(self, issue, author):
        from apps.notifications.models import Notification
        a, b = UserFactory(), UserFactory()
        comment = IssueCommentFactory(
            issue=issue, author=author,
            content=f"{mention(a)} 和 {mention(b)} 请跟进",
        )
        self._call(comment, old_content="", actor=author)
        assert Notification.objects.count() == 2
        for target in (a, b):
            n = Notification.objects.filter(recipients__user=target).first()
            assert n is not None
            assert n.recipients.count() == 1


class TestCommentListCreate:
    def test_create_returns_201_with_payload(self, author_client, author, issue):
        resp = author_client.post(
            f"/api/issues/{issue.pk}/comments/", {"content": "第一条评论"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["content"] == "第一条评论"
        assert data["author"] == author.id
        assert data["author_name"] == (author.name or author.username)
        assert data["is_edited"] is False

    def test_list_returns_oldest_first(self, author_client, issue, author):
        c1 = IssueCommentFactory(issue=issue, author=author, content="老评论")
        c2 = IssueCommentFactory(issue=issue, author=author, content="新评论")
        resp = author_client.get(f"/api/issues/{issue.pk}/comments/")
        assert resp.status_code == 200
        assert [c["id"] for c in resp.json()] == [c1.id, c2.id]

    def test_blank_content_rejected(self, author_client, issue):
        resp = author_client.post(f"/api/issues/{issue.pk}/comments/", {"content": "   "})
        assert resp.status_code == 400

    def test_overlong_content_rejected(self, author_client, issue):
        resp = author_client.post(
            f"/api/issues/{issue.pk}/comments/", {"content": "x" * 65537},
        )
        assert resp.status_code == 400

    def test_unauthenticated_401(self, api_client, issue):
        assert api_client.get(f"/api/issues/{issue.pk}/comments/").status_code == 401
        assert api_client.post(
            f"/api/issues/{issue.pk}/comments/", {"content": "x"},
        ).status_code == 401

    def test_unknown_issue_404(self, author_client):
        assert author_client.get("/api/issues/999999/comments/").status_code == 404
        assert author_client.post(
            "/api/issues/999999/comments/", {"content": "x"},
        ).status_code == 404

    def test_create_writes_commented_activity(self, author_client, author, issue):
        from apps.issues.models import Activity
        author_client.post(f"/api/issues/{issue.pk}/comments/", {"content": "评论"})
        assert Activity.objects.filter(
            issue=issue, user=author, action="commented",
        ).exists()

    def test_create_bumps_updated_at_without_history_row(self, author_client, issue):
        old_updated = issue.updated_at
        old_history = issue.history.count()
        resp = author_client.post(f"/api/issues/{issue.pk}/comments/", {"content": "bump"})
        assert resp.status_code == 201
        issue.refresh_from_db()
        assert issue.updated_at > old_updated
        # 用 queryset.update 绕过 save() → 不允许产生 simple_history 快照
        assert issue.history.count() == old_history

    def test_create_with_mention_notifies(self, author_client, issue):
        from apps.notifications.models import Notification
        target = UserFactory()
        resp = author_client.post(
            f"/api/issues/{issue.pk}/comments/",
            {"content": f"请处理 {mention(target)}"},
        )
        assert resp.status_code == 201
        n = Notification.objects.filter(
            notification_type=Notification.Type.MENTION, source_issue=issue,
        ).first()
        assert n is not None and n.recipients.filter(user=target).exists()


class TestCommentEditDelete:
    def _backdate(self, comment, seconds=10):
        """把 created_at 回拨,使编辑后 is_edited 的 1 秒容差判定生效。"""
        from datetime import timedelta
        from django.utils import timezone
        IssueComment.objects.filter(pk=comment.pk).update(
            created_at=timezone.now() - timedelta(seconds=seconds),
        )

    def test_author_can_edit(self, author_client, author, issue):
        comment = IssueCommentFactory(issue=issue, author=author, content="原文")
        self._backdate(comment)
        resp = author_client.patch(
            f"/api/issues/{issue.pk}/comments/{comment.pk}/", {"content": "改过的"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "改过的"
        assert data["is_edited"] is True

    def test_non_author_cannot_edit(self, other_client, author, issue):
        comment = IssueCommentFactory(issue=issue, author=author)
        resp = other_client.patch(
            f"/api/issues/{issue.pk}/comments/{comment.pk}/", {"content": "篡改"},
        )
        assert resp.status_code == 403

    def test_admin_cannot_edit_others(self, admin_client, author, issue):
        # 管理员只可删不可改
        comment = IssueCommentFactory(issue=issue, author=author)
        resp = admin_client.patch(
            f"/api/issues/{issue.pk}/comments/{comment.pk}/", {"content": "篡改"},
        )
        assert resp.status_code == 403

    def test_edit_blank_content_rejected(self, author_client, author, issue):
        comment = IssueCommentFactory(issue=issue, author=author)
        resp = author_client.patch(
            f"/api/issues/{issue.pk}/comments/{comment.pk}/", {"content": " "},
        )
        assert resp.status_code == 400

    def test_author_can_delete(self, author_client, author, issue):
        comment = IssueCommentFactory(issue=issue, author=author)
        resp = author_client.delete(f"/api/issues/{issue.pk}/comments/{comment.pk}/")
        assert resp.status_code == 204
        assert not IssueComment.objects.filter(pk=comment.pk).exists()

    def test_admin_group_can_delete_any(self, admin_client, author, issue):
        comment = IssueCommentFactory(issue=issue, author=author)
        resp = admin_client.delete(f"/api/issues/{issue.pk}/comments/{comment.pk}/")
        assert resp.status_code == 204

    def test_superuser_can_delete_any(self, superuser_client, author, issue):
        comment = IssueCommentFactory(issue=issue, author=author)
        resp = superuser_client.delete(f"/api/issues/{issue.pk}/comments/{comment.pk}/")
        assert resp.status_code == 204

    def test_other_user_cannot_delete(self, other_client, author, issue):
        comment = IssueCommentFactory(issue=issue, author=author)
        resp = other_client.delete(f"/api/issues/{issue.pk}/comments/{comment.pk}/")
        assert resp.status_code == 403
        assert IssueComment.objects.filter(pk=comment.pk).exists()

    def test_comment_under_wrong_issue_404(self, author_client, author, issue):
        other_issue = IssueFactory()
        comment = IssueCommentFactory(issue=other_issue, author=author)
        resp = author_client.patch(
            f"/api/issues/{issue.pk}/comments/{comment.pk}/", {"content": "x"},
        )
        assert resp.status_code == 404

    def test_edit_notifies_only_new_mentions(self, author_client, author, issue):
        from apps.notifications.models import Notification
        first, second = UserFactory(), UserFactory()
        comment = IssueCommentFactory(
            issue=issue, author=author, content=f"已提及 {mention(first)}",
        )
        resp = author_client.patch(
            f"/api/issues/{issue.pk}/comments/{comment.pk}/",
            {"content": f"已提及 {mention(first)} 新增 {mention(second)}"},
        )
        assert resp.status_code == 200
        recipients = list(
            Notification.objects.filter(source_issue=issue)
            .values_list("recipients__user", flat=True)
        )
        assert second.id in recipients
        assert first.id not in recipients

    def test_list_serializes_deleted_author(self, author_client, issue):
        # on_delete=SET_NULL 后 author 为 None 的序列化分支
        IssueCommentFactory(issue=issue, author=None, content="孤儿评论")
        resp = author_client.get(f"/api/issues/{issue.pk}/comments/")
        assert resp.status_code == 200
        data = resp.json()[-1]
        assert data["author"] is None
        assert data["author_name"] is None
        assert data["author_avatar"] == ""
