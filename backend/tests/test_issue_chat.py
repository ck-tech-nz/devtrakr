import pytest

from apps.issues.models import IssueChatParticipant
from tests.factories import IssueFactory, IssueCommentFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_unread_count_excludes_own_and_counts_newer():
    issue = IssueFactory()
    me = UserFactory()
    other = UserFactory()
    c1 = IssueCommentFactory(issue=issue, author=other)
    part = IssueChatParticipant.objects.create(issue=issue, user=me, last_read_comment=c1)
    # 一条别人的新评论 + 一条自己的评论
    IssueCommentFactory(issue=issue, author=other)   # 未读 +1
    IssueCommentFactory(issue=issue, author=me)       # 自己的不计
    assert part.unread_count() == 1


def test_unread_count_none_pointer_counts_all_others():
    issue = IssueFactory()
    me = UserFactory()
    other = UserFactory()
    IssueCommentFactory(issue=issue, author=other)
    IssueCommentFactory(issue=issue, author=other)
    part = IssueChatParticipant.objects.create(issue=issue, user=me, last_read_comment=None)
    assert part.unread_count() == 2
