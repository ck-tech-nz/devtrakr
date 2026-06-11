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
