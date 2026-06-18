import pytest

from apps.issues.models import IssueChatParticipant
from apps.issues.services_chat import participants_for_comment
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


def test_participants_union_assignee_helpers_mentions():
    assignee = UserFactory()
    helper = UserFactory()
    mentioned = UserFactory()
    author = UserFactory()
    issue = IssueFactory(assignee=assignee)
    issue.helpers.add(helper)
    content = f"看下 @[{mentioned.name}](user:{mentioned.id})"
    comment = IssueCommentFactory(issue=issue, author=author, content=content)

    result = participants_for_comment(comment)
    assert {assignee, helper, mentioned}.issubset(result)


def test_participants_includes_existing_participants_and_skips_inactive():
    issue = IssueFactory(assignee=None)
    existing = UserFactory()
    inactive = UserFactory(is_active=False)
    IssueChatParticipant.objects.create(issue=issue, user=existing)
    IssueChatParticipant.objects.create(issue=issue, user=inactive)
    comment = IssueCommentFactory(issue=issue)

    result = participants_for_comment(comment)
    assert existing in result
    assert inactive not in result
