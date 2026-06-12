# Issue 评论功能（IssueComment）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 issue 增加 GitHub 风格的评论：后端 `IssueComment` 模型 + 嵌套 REST API，前端详情页评论区（Markdown、@提及通知、作者编辑删除/管理员删除、评论刷新 issue.updated_at）。

**Architecture:** 后端在 `apps/issues` 内新增模型与两个 APIView（沿用现有子资源模式 `IsAuthenticated` + 视图内对象级权限），@提及通知在 `apps/notifications/services.py` 新增独立函数；前端新增自治组件 `IssueComments.vue`（自己加载/维护数据），由详情页挂载。设计文档：`docs/superpowers/specs/2026-06-11-issue-comments-design.md`（已用户审定）。

**Tech Stack:** Django 5 + DRF + pytest/factory-boy；Nuxt 4 + Nuxt UI + vitest (@nuxt/test-utils)。

**分支:** `feat/issue-comments`（已自 main 切出）。后端命令在 `backend/` 下执行，前端命令在 `frontend/` 下执行。

**关键既有事实（实现时直接引用，不要再发明）：**

- @提及的文本格式是 `@[显示名](user:用户ID)`，解析正则 `MENTION_RE` 已存在于 `backend/apps/notifications/services.py:11`
- `backend/apps/issues/views.py` 顶部已 `from django.utils import timezone`（line 15）、已导入 `Issue, IssueStatus, Activity`（line 24）
- Issue 挂了 `simple_history`：**任何 `issue.save()` 都会写历史快照**。bump `updated_at` 必须用 `Issue.objects.filter(pk=...).update(updated_at=timezone.now())`
- 管理员判定惯例：`user.is_superuser or user.groups.filter(name="管理员").exists()`（见 `serializers.py` `_user_can_edit_estimated_hours`）
- 测试夹具（`backend/tests/conftest.py`）：`api_client`（未认证）、`regular_client`（普通用户）、`auth_client`（管理员组用户）、`superuser_client`。本功能测试需要拿到“作者”用户对象，故在测试文件内自建夹具
- 前端 `components/issue/` 下的组件按惯例**显式导入**（如 `import StatusCell from '~/components/issue/StatusCell.vue'`），不是自动导入
- 前端组件测试模式参考 `frontend/tests/headerBulletinCarousel.test.ts`：`// @vitest-environment nuxt` + `mountSuspended` + `mockNuxtImport` + `vi.hoisted`
- `frontend/` typecheck（`npx nuxi typecheck`）在 main 上本来就是红的（Nuxt UI 升级遗留），**门禁是 `npm run test`**

---

### Task 1: IssueComment 模型 + 迁移 + admin + factory

**Files:**
- Modify: `backend/apps/issues/models.py`（文件末尾追加）
- Modify: `backend/apps/issues/admin.py`
- Modify: `backend/tests/factories.py`
- Create: `backend/tests/test_issue_comments.py`
- Create: `backend/apps/issues/migrations/00XX_issuecomment.py`（makemigrations 生成）

- [ ] **Step 1: 写失败的模型测试**

创建 `backend/tests/test_issue_comments.py`：

```python
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
        c1 = IssueCommentFactory(issue=issue, author=author)
        c2 = IssueCommentFactory(issue=issue, author=author)
        assert list(issue.comments.all()) == [c1, c2]

    def test_str(self, issue, author):
        c = IssueCommentFactory(issue=issue, author=author, content="x" * 100)
        assert str(c).startswith(f"#{issue.pk} ")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && uv run pytest tests/test_issue_comments.py -v
```

Expected: FAIL —— `ImportError: cannot import name 'IssueComment'`

- [ ] **Step 3: 添加模型**

在 `backend/apps/issues/models.py` 文件末尾（`IssueAssignment` 之后）追加：

```python
class IssueComment(models.Model):
    issue = models.ForeignKey(
        Issue, on_delete=models.CASCADE, related_name="comments",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="issue_comments", verbose_name="作者",
    )
    content = models.TextField(verbose_name="内容")  # markdown 原文,附件以内联链接存在
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "问题评论"
        verbose_name_plural = "问题评论"
        ordering = ["created_at"]  # 旧→新,同 GitHub
        indexes = [models.Index(fields=["issue", "created_at"])]

    def __str__(self):
        return f"#{self.issue_id} {self.author}: {self.content[:30]}"
```

- [ ] **Step 4: 生成并应用迁移**

```bash
cd backend && uv run python manage.py makemigrations issues && uv run python manage.py migrate
```

Expected: 生成 `apps/issues/migrations/00XX_issuecomment.py`（含 model + index），migrate OK

- [ ] **Step 5: 添加 factory**

`backend/tests/factories.py`：把顶部 `from apps.issues.models import Issue, Activity` 改为
`from apps.issues.models import Issue, Activity, IssueComment`，然后在 `ActivityFactory` 之后追加：

```python
class IssueCommentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = IssueComment

    issue = factory.SubFactory(IssueFactory)
    author = factory.SubFactory(UserFactory)
    content = factory.Sequence(lambda n: f"评论内容 {n}")
```

- [ ] **Step 6: 注册 admin**

`backend/apps/issues/admin.py`：把 `from .models import Issue, Activity, IssueAssignment` 改为
`from .models import Issue, Activity, IssueAssignment, IssueComment`，文件末尾追加：

```python
@admin.register(IssueComment)
class IssueCommentAdmin(ModelAdmin):
    list_display = ("id", "issue", "author", "created_at")
    search_fields = ("issue__title", "content", "author__username")
    raw_id_fields = ("issue", "author")
    readonly_fields = ("created_at", "updated_at")
```

- [ ] **Step 7: 运行测试确认通过**

```bash
cd backend && uv run pytest tests/test_issue_comments.py -v
```

Expected: 2 passed

- [ ] **Step 8: Commit**

```bash
git add backend/apps/issues/models.py backend/apps/issues/migrations backend/apps/issues/admin.py backend/tests/factories.py backend/tests/test_issue_comments.py
git commit -m "feat(issues): IssueComment 模型 + 迁移 + admin + factory"
```

---

### Task 2: 评论 @提及通知服务（create_comment_mention_notifications）

**Files:**
- Modify: `backend/apps/notifications/services.py`（末尾追加）
- Modify: `backend/tests/test_issue_comments.py`

- [ ] **Step 1: 写失败的服务测试**

在 `test_issue_comments.py` 末尾追加：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && uv run pytest tests/test_issue_comments.py::TestCommentMentionService -v
```

Expected: FAIL —— `ImportError: cannot import name 'create_comment_mention_notifications'`

- [ ] **Step 3: 实现服务函数**

`backend/apps/notifications/services.py` 末尾（`create_mention_notifications` 之后）追加。
不改动现有 `create_mention_notifications` 的签名和行为：

```python
def create_comment_mention_notifications(*, comment, old_content: str, new_content: str, actor):
    """评论中 @提及 的站内通知。只对本次新增的提及发，@自己不发。"""
    old_ids = extract_mentioned_user_ids(old_content)
    new_ids = extract_mentioned_user_ids(new_content)
    added_ids = new_ids - old_ids - {actor.id}
    if not added_ids:
        return

    issue = comment.issue
    users = User.objects.filter(id__in=added_ids, is_active=True)
    for user in users:
        notification = Notification.objects.create(
            notification_type=Notification.Type.MENTION,
            title=f"{actor.name or actor.username} 在 #{issue.pk} 的评论中提到了你",
            content=comment.content[:100],
            source_user=actor,
            source_issue=issue,
            target_type=Notification.TargetType.USER,
        )
        NotificationRecipient.objects.create(notification=notification, user=user)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && uv run pytest tests/test_issue_comments.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/apps/notifications/services.py backend/tests/test_issue_comments.py
git commit -m "feat(notifications): 评论 @提及 通知 create_comment_mention_notifications"
```

---

### Task 3: 评论列表 + 创建 API（GET/POST /api/issues/{id}/comments/）

**Files:**
- Modify: `backend/apps/issues/serializers.py`
- Modify: `backend/apps/issues/views.py`
- Modify: `backend/apps/issues/urls.py`
- Modify: `backend/tests/test_issue_comments.py`

- [ ] **Step 1: 写失败的 API 测试**

在 `test_issue_comments.py` 末尾追加：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && uv run pytest tests/test_issue_comments.py::TestCommentListCreate -v
```

Expected: FAIL —— 全部 404（路由不存在）

- [ ] **Step 3: 添加序列化器**

`backend/apps/issues/serializers.py`：把 `from .models import Issue, IssueStatus, Activity, IssueAssignment`
改为 `from .models import Issue, IssueStatus, Activity, IssueAssignment, IssueComment`，
在 `IssueAssignmentSerializer` 之后追加：

```python
class IssueCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    author_avatar = serializers.SerializerMethodField()
    is_edited = serializers.SerializerMethodField()

    class Meta:
        model = IssueComment
        fields = [
            "id", "author", "author_name", "author_avatar",
            "content", "created_at", "updated_at", "is_edited",
        ]
        read_only_fields = ["id", "author", "created_at", "updated_at"]

    def get_author_name(self, obj):
        if obj.author:
            return obj.author.name or obj.author.username
        return None

    def get_author_avatar(self, obj):
        return obj.author.avatar if obj.author else ""

    def get_is_edited(self, obj):
        # auto_now 与 auto_now_add 在创建时存在微小差异,用 1 秒容差判定
        return (obj.updated_at - obj.created_at).total_seconds() > 1

    def validate_content(self, value):
        if not value.strip():
            raise serializers.ValidationError("评论内容不能为空")
        if len(value) > 65536:
            raise serializers.ValidationError("评论内容过长（上限 65536 字符）")
        return value
```

- [ ] **Step 4: 添加视图**

`backend/apps/issues/views.py`：

1. line 24 的 `from .models import Issue, IssueStatus, Activity` 追加 `IssueComment`
2. `from .serializers import (...)` 列表里追加 `IssueCommentSerializer`
3. 顶部追加 `from apps.notifications.services import create_comment_mention_notifications`
4. 在 `IssueAttachmentsView` 之后插入：

```python
def _can_moderate_comments(user) -> bool:
    """管理员（superuser 或「管理员」组）可删除任意评论。"""
    return user.is_superuser or user.groups.filter(name="管理员").exists()


class IssueCommentsView(APIView):
    """GET: 评论列表（旧→新）。POST: 发表评论。"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        issue = Issue.objects.filter(pk=pk).first()
        if not issue:
            return Response({"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)
        comments = issue.comments.select_related("author")
        return Response(IssueCommentSerializer(comments, many=True).data)

    def post(self, request, pk):
        issue = Issue.objects.filter(pk=pk).first()
        if not issue:
            return Response({"detail": "问题不存在"}, status=status.HTTP_404_NOT_FOUND)
        serializer = IssueCommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = IssueComment.objects.create(
            issue=issue, author=request.user,
            content=serializer.validated_data["content"],
        )
        Activity.objects.create(user=request.user, issue=issue, action="commented")
        # bump updated_at 让问题列表/看板反映评论动态;
        # 必须用 queryset.update 绕过 save() → 不产生 simple_history 快照
        Issue.objects.filter(pk=issue.pk).update(updated_at=timezone.now())
        create_comment_mention_notifications(
            comment=comment, old_content="", new_content=comment.content,
            actor=request.user,
        )
        return Response(
            IssueCommentSerializer(comment).data, status=status.HTTP_201_CREATED,
        )
```

- [ ] **Step 5: 添加路由**

`backend/apps/issues/urls.py`：import 列表追加 `IssueCommentsView`，
在 `path("<int:pk>/attachments/", ...)` 之后插入：

```python
    path("<int:pk>/comments/", IssueCommentsView.as_view(), name="issue-comments"),
```

- [ ] **Step 6: 运行测试确认通过**

```bash
cd backend && uv run pytest tests/test_issue_comments.py -v
```

Expected: 15 passed

- [ ] **Step 7: Commit**

```bash
git add backend/apps/issues/serializers.py backend/apps/issues/views.py backend/apps/issues/urls.py backend/tests/test_issue_comments.py
git commit -m "feat(issues): 评论列表/创建 API + Activity + updated_at bump + 提及通知"
```

---

### Task 4: 评论编辑 + 删除 API（PATCH/DELETE /api/issues/{id}/comments/{cid}/）

**Files:**
- Modify: `backend/apps/issues/views.py`
- Modify: `backend/apps/issues/urls.py`
- Modify: `backend/tests/test_issue_comments.py`

- [ ] **Step 1: 写失败的 API 测试**

在 `test_issue_comments.py` 末尾追加。注意 `is_edited` 用 1 秒容差判定，
测试里"创建后立刻编辑"间隔是毫秒级，必须先把 `created_at` 回拨再编辑：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && uv run pytest tests/test_issue_comments.py::TestCommentEditDelete -v
```

Expected: FAIL —— 全部 404（detail 路由不存在）

- [ ] **Step 3: 添加视图**

`backend/apps/issues/views.py` 在 `IssueCommentsView` 之后插入：

```python
class IssueCommentDetailView(APIView):
    """PATCH: 仅作者可编辑。DELETE: 作者或管理员。"""
    permission_classes = [IsAuthenticated]

    def _get_comment(self, pk, comment_id):
        return (
            IssueComment.objects.select_related("author", "issue")
            .filter(pk=comment_id, issue_id=pk)
            .first()
        )

    def patch(self, request, pk, comment_id):
        comment = self._get_comment(pk, comment_id)
        if not comment:
            return Response({"detail": "评论不存在"}, status=status.HTTP_404_NOT_FOUND)
        if comment.author_id != request.user.id:
            return Response({"detail": "只能编辑自己的评论"}, status=status.HTTP_403_FORBIDDEN)
        serializer = IssueCommentSerializer(comment, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        old_content = comment.content
        comment.content = serializer.validated_data.get("content", comment.content)
        comment.save(update_fields=["content", "updated_at"])
        # 编辑不写 Activity、不 bump issue.updated_at（既有评论的修订不算新讨论动态）
        create_comment_mention_notifications(
            comment=comment, old_content=old_content, new_content=comment.content,
            actor=request.user,
        )
        return Response(IssueCommentSerializer(comment).data)

    def delete(self, request, pk, comment_id):
        comment = self._get_comment(pk, comment_id)
        if not comment:
            return Response({"detail": "评论不存在"}, status=status.HTTP_404_NOT_FOUND)
        if comment.author_id != request.user.id and not _can_moderate_comments(request.user):
            return Response({"detail": "无权删除该评论"}, status=status.HTTP_403_FORBIDDEN)
        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 4: 添加路由**

`backend/apps/issues/urls.py`：import 追加 `IssueCommentDetailView`，
在 comments 路由之后插入：

```python
    path(
        "<int:pk>/comments/<int:comment_id>/",
        IssueCommentDetailView.as_view(),
        name="issue-comment-detail",
    ),
```

- [ ] **Step 5: 运行本文件全部测试确认通过**

```bash
cd backend && uv run pytest tests/test_issue_comments.py -v
```

Expected: 25 passed

- [ ] **Step 6: 跑后端全量回归**

```bash
cd backend && uv run pytest -x -q
```

Expected: 全部通过（如有失败，先修复再继续）

- [ ] **Step 7: Commit**

```bash
git add backend/apps/issues/views.py backend/apps/issues/urls.py backend/tests/test_issue_comments.py
git commit -m "feat(issues): 评论编辑/删除 API（作者可改删,管理员可删）"
```

---

### Task 5: 前端 IssueComments 组件 + 组件测试

**Files:**
- Create: `frontend/app/components/issue/IssueComments.vue`
- Create: `frontend/tests/issueComments.test.ts`

- [ ] **Step 1: 写失败的组件测试**

创建 `frontend/tests/issueComments.test.ts`：

```ts
// @vitest-environment nuxt
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { ref } from 'vue'
import IssueComments from '../app/components/issue/IssueComments.vue'

const { apiMock, authBox } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  authBox: {
    user: { id: '1', name: '我', is_superuser: false },
    groups: [] as string[],
  },
}))

mockNuxtImport('useApi', () => () => ({ api: apiMock }))
mockNuxtImport('useAuth', () => () => ({
  user: ref(authBox.user),
  hasGroup: (g: string) => authBox.groups.includes(g),
}))

// MarkdownEditor/MarkdownView 依赖重(mention 拉用户列表、markdown-it),stub 掉
const stubs = {
  MarkdownEditor: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    // 注意: 运行时模板不支持 TS 类型断言,这里必须是纯 JS 表达式
    template: `<textarea data-testid="editor" :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />`,
  },
  MarkdownView: { props: ['text'], template: '<div class="md-view">{{ text }}</div>' },
}

function comment(over: Record<string, unknown> = {}) {
  return {
    id: 1, author: 1, author_name: '张三', author_avatar: '',
    content: '第一条评论', created_at: '2026-06-11T10:00:00+08:00',
    updated_at: '2026-06-11T10:00:00+08:00', is_edited: false, ...over,
  }
}

const flush = () => new Promise<void>(resolve => setTimeout(resolve))

async function mount() {
  const w = await mountSuspended(IssueComments, {
    props: { issueId: 5 },
    global: { stubs },
  })
  await flush()
  return w
}

beforeEach(() => {
  apiMock.mockReset()
  authBox.user = { id: '1', name: '我', is_superuser: false }
  authBox.groups = []
})

describe('IssueComments', () => {
  it('renders comments returned by the API with count', async () => {
    apiMock.mockResolvedValue([
      comment({ id: 1, content: '第一条评论' }),
      comment({ id: 2, content: '第二条评论', is_edited: true }),
    ])
    const w = await mount()
    expect(apiMock).toHaveBeenCalledWith('/api/issues/5/comments/')
    expect(w.text()).toContain('评论 (2)')
    expect(w.text()).toContain('第一条评论')
    expect(w.text()).toContain('已编辑')
    w.unmount()
  })

  it('shows empty hint when there are no comments', async () => {
    apiMock.mockResolvedValue([])
    const w = await mount()
    expect(w.text()).toContain('暂无评论')
    w.unmount()
  })

  it('posts a new comment and appends it to the list', async () => {
    apiMock.mockImplementation((url: string, opts?: { method?: string; body?: { content: string } }) => {
      if (opts?.method === 'POST') {
        return Promise.resolve(comment({ id: 9, content: opts.body!.content }))
      }
      return Promise.resolve([])
    })
    const w = await mount()
    await w.find('[data-testid="new-comment"] [data-testid="editor"]').setValue('新评论内容')
    await w.find('[data-testid="submit-comment"]').trigger('click')
    await flush()
    expect(apiMock).toHaveBeenCalledWith('/api/issues/5/comments/', {
      method: 'POST', body: { content: '新评论内容' },
    })
    expect(w.text()).toContain('新评论内容')
    expect(w.text()).toContain('评论 (1)')
    w.unmount()
  })

  it('hides edit/delete for non-author, shows delete only for admin', async () => {
    apiMock.mockResolvedValue([comment({ id: 1, author: 99, author_name: '别人' })])
    let w = await mount()
    expect(w.find('[data-testid="edit-comment"]').exists()).toBe(false)
    expect(w.find('[data-testid="delete-comment"]').exists()).toBe(false)
    w.unmount()

    authBox.groups = ['管理员']
    w = await mount()
    expect(w.find('[data-testid="edit-comment"]').exists()).toBe(false)
    expect(w.find('[data-testid="delete-comment"]').exists()).toBe(true)
    w.unmount()
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd frontend && npm run test -- tests/issueComments.test.ts
```

Expected: FAIL —— 找不到 `../app/components/issue/IssueComments.vue`

- [ ] **Step 3: 实现组件**

创建 `frontend/app/components/issue/IssueComments.vue`：

```vue
<template>
  <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 p-5 space-y-4">
    <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">评论 ({{ comments.length }})</h3>

    <div v-if="loading" class="text-xs text-gray-400 dark:text-gray-500">加载中...</div>
    <div v-else-if="loadError" class="text-xs text-rose-500 flex items-center gap-2">
      <span>评论加载失败</span>
      <UButton size="xs" variant="link" @click="loadComments">重试</UButton>
    </div>
    <p v-else-if="!comments.length" class="text-xs text-gray-400 dark:text-gray-500">暂无评论</p>

    <div v-else class="space-y-3">
      <div
        v-for="c in comments"
        :key="c.id"
        data-testid="comment-item"
        class="border border-gray-100 dark:border-gray-800 rounded-lg"
      >
        <div class="flex items-center justify-between px-3 py-1.5 bg-gray-50 dark:bg-gray-800/60 rounded-t-lg">
          <div class="flex items-center gap-2 min-w-0">
            <img v-if="c.author_avatar" :src="resolveAvatarUrl(c.author_avatar)" class="w-5 h-5 rounded-full shrink-0" />
            <span class="text-xs font-medium text-gray-700 dark:text-gray-300 truncate">{{ c.author_name || '已注销用户' }}</span>
            <time class="text-[11px] text-gray-400 dark:text-gray-500 shrink-0" :title="c.created_at">{{ timeAgo(c.created_at) }}</time>
            <span v-if="c.is_edited" class="text-[11px] text-gray-400 dark:text-gray-500 shrink-0">已编辑</span>
          </div>
          <div class="flex items-center gap-1 shrink-0">
            <UButton
              v-if="canEdit(c)"
              data-testid="edit-comment"
              size="xs" variant="ghost" color="neutral" icon="i-heroicons-pencil-square"
              @click="startEdit(c)"
            />
            <UButton
              v-if="canDelete(c)"
              data-testid="delete-comment"
              size="xs" variant="ghost" color="error" icon="i-heroicons-trash"
              @click="pendingDelete = c"
            />
          </div>
        </div>
        <div class="p-3">
          <template v-if="editingId === c.id">
            <MarkdownEditor v-model="editDraft" min-height="120px" />
            <div class="flex justify-end gap-2 mt-2">
              <UButton size="xs" variant="ghost" color="neutral" @click="cancelEdit">取消</UButton>
              <UButton size="xs" :loading="savingEdit" :disabled="!editDraft.trim()" @click="saveEdit(c)">保存</UButton>
            </div>
          </template>
          <MarkdownView v-else :text="c.content" />
        </div>
      </div>
    </div>

    <!-- 新评论输入框 -->
    <div data-testid="new-comment" class="space-y-2">
      <MarkdownEditor v-model="draft" placeholder="发表评论... 支持 Markdown 和 @提及" min-height="120px" />
      <div class="flex justify-end">
        <UButton data-testid="submit-comment" size="sm" :loading="submitting" :disabled="!draft.trim()" @click="submit">评论</UButton>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <UModal :open="!!pendingDelete" @update:open="(v: boolean) => { if (!v) pendingDelete = null }">
      <template #content>
        <div class="modal-form">
          <div class="modal-header">
            <h3>删除评论</h3>
            <UButton icon="i-heroicons-x-mark" variant="ghost" color="neutral" size="sm" @click="pendingDelete = null" />
          </div>
          <div class="modal-body">
            <p class="text-sm text-gray-700 dark:text-gray-300">确认删除这条评论？此操作不可恢复。</p>
          </div>
          <div class="modal-footer">
            <UButton variant="outline" color="neutral" @click="pendingDelete = null">取消</UButton>
            <UButton color="error" :loading="deleting" @click="confirmDelete">删除</UButton>
          </div>
        </div>
      </template>
    </UModal>
  </div>
</template>

<script setup lang="ts">
import { timeAgo } from '~/utils/timeAgo'

interface IssueCommentItem {
  id: number
  author: number | null
  author_name: string | null
  author_avatar: string
  content: string
  created_at: string
  updated_at: string
  is_edited: boolean
}

const props = defineProps<{ issueId: number }>()

const { api } = useApi()
const { user, hasGroup } = useAuth()
const { resolveAvatarUrl } = useAvatars()
const toast = useToast()

const comments = ref<IssueCommentItem[]>([])
const loading = ref(true)
const loadError = ref(false)

const draft = ref('')
const submitting = ref(false)

const editingId = ref<number | null>(null)
const editDraft = ref('')
const savingEdit = ref(false)

const pendingDelete = ref<IssueCommentItem | null>(null)
const deleting = ref(false)

const isAdmin = computed(() => hasGroup('管理员') || !!user.value?.is_superuser)

function isAuthor(c: IssueCommentItem): boolean {
  return !!user.value && Number(user.value.id) === c.author
}
function canEdit(c: IssueCommentItem): boolean {
  return isAuthor(c)
}
function canDelete(c: IssueCommentItem): boolean {
  return isAuthor(c) || isAdmin.value
}

async function loadComments() {
  loading.value = true
  loadError.value = false
  try {
    comments.value = await api<IssueCommentItem[]>(`/api/issues/${props.issueId}/comments/`)
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!draft.value.trim() || submitting.value) return
  submitting.value = true
  try {
    const created = await api<IssueCommentItem>(`/api/issues/${props.issueId}/comments/`, {
      method: 'POST', body: { content: draft.value },
    })
    comments.value.push(created)
    draft.value = ''
  } catch (e: any) {
    toast.add({ title: e?.data?.detail || '评论发表失败', color: 'error' })
  } finally {
    submitting.value = false
  }
}

function startEdit(c: IssueCommentItem) {
  editingId.value = c.id
  editDraft.value = c.content
}
function cancelEdit() {
  editingId.value = null
  editDraft.value = ''
}
async function saveEdit(c: IssueCommentItem) {
  if (!editDraft.value.trim() || savingEdit.value) return
  savingEdit.value = true
  try {
    const updated = await api<IssueCommentItem>(`/api/issues/${props.issueId}/comments/${c.id}/`, {
      method: 'PATCH', body: { content: editDraft.value },
    })
    const idx = comments.value.findIndex(x => x.id === c.id)
    if (idx !== -1) comments.value[idx] = updated
    cancelEdit()
  } catch (e: any) {
    toast.add({ title: e?.data?.detail || '评论保存失败', color: 'error' })
  } finally {
    savingEdit.value = false
  }
}

async function confirmDelete() {
  const target = pendingDelete.value
  if (!target || deleting.value) return
  deleting.value = true
  try {
    await api(`/api/issues/${props.issueId}/comments/${target.id}/`, { method: 'DELETE' })
    comments.value = comments.value.filter(x => x.id !== target.id)
    pendingDelete.value = null
  } catch (e: any) {
    toast.add({ title: e?.data?.detail || '评论删除失败', color: 'error' })
  } finally {
    deleting.value = false
  }
}

onMounted(loadComments)
</script>
```

实现说明：

- `MarkdownEditor`/`MarkdownView` 是 `components/` 根目录组件，自动导入，无需 import
- `useAvatars().resolveAvatarUrl` 把头像 id 解析为本地 SVG（同 `AppHeader.vue:32` 用法）
- `timeAgo` 来自 `~/utils/timeAgo`（dashboard Activity 组件同款）
- `user.value.id` 是 string（`useAuth.ts` AuthUser 接口），与 `c.author`（number）比较要 `Number()`
- `modal-form/header/body/footer` class 是项目现有弹窗样式（参考 `[id].vue:663-684` 删除附件弹窗）

- [ ] **Step 4: 运行测试确认通过**

```bash
cd frontend && npm run test -- tests/issueComments.test.ts
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/app/components/issue/IssueComments.vue frontend/tests/issueComments.test.ts
git commit -m "feat(issues): IssueComments 评论区组件 + 组件测试"
```

---

### Task 6: 详情页接入 + dashboard 动态流「评论」标签

**Files:**
- Modify: `frontend/app/pages/app/issues/[id].vue`
- Modify: `frontend/app/pages/app/dashboard.vue`
- Modify: `frontend/app/components/dashboard/Activity.vue`

- [ ] **Step 1: 详情页挂载组件**

`frontend/app/pages/app/issues/[id].vue`：

1. script 里（line 830 附近的 import 区域）追加：

```ts
import IssueComments from '~/components/issue/IssueComments.vue'
```

2. 模板主栏（`<div class="lg:col-span-2 space-y-4">`）内、「分析记录」卡片（line 83 `</div>`）之后、主栏闭合 `</div>`（line 84）之前插入：

```vue
        <!-- 评论 -->
        <IssueComments v-if="!isNewIssue && issue?.id" :issue-id="issue.id" />
```

- [ ] **Step 2: dashboard.vue 增加 commented 标签**

`frontend/app/pages/app/dashboard.vue`：

`activityIcon`（line 110）switch 里 `case 'priority_changed'` 之后加：

```ts
    case 'commented': return 'i-heroicons-chat-bubble-left-ellipsis'
```

`activityMessage`（line 121）switch 里 `case 'priority_changed'` 之后加：

```ts
    case 'commented': return `${name} 评论了问题 ${issueRef}${item.issue_title ? '「' + item.issue_title + '」' : ''}`
```

- [ ] **Step 3: dashboard/Activity.vue（首页小组件）增加 commented 标签**

`frontend/app/components/dashboard/Activity.vue` `activityMessage`（line 41）switch 里
`case 'priority_changed'` 之后加：

```ts
    case 'commented': return `${name} 评论了 ${issueRef}${title}`
```

- [ ] **Step 4: 跑前端全部测试**

```bash
cd frontend && npm run test
```

Expected: 全部通过（包含既有测试，确认无回归）

- [ ] **Step 5: Commit**

```bash
git add frontend/app/pages/app/issues/\[id\].vue frontend/app/pages/app/dashboard.vue frontend/app/components/dashboard/Activity.vue
git commit -m "feat(issues): 详情页接入评论区; dashboard 动态流显示「评论了」"
```

---

### Task 7: 全量回归 + 手动验收

- [ ] **Step 1: 后端全量测试**

```bash
cd backend && uv run pytest -q
```

Expected: 全部通过

- [ ] **Step 2: 前端全量测试**

```bash
cd frontend && npm run test
```

Expected: 全部通过（注：`npx nuxi typecheck` 在 main 上本来就红，不作为本功能门禁）

- [ ] **Step 3: 手动验收（dev 环境冒烟）**

启动 `backend: uv run python manage.py runserver` 与 `frontend: npm run dev`（:3004），
打开任一 issue 详情页验证：

1. 评论区出现在主栏底部，发一条带 `@提及` 和图片粘贴的评论 → 列表追加、Markdown 渲染、被提及人收到通知（铃铛）
2. 编辑自己的评论 → 显示「已编辑」；删除有确认弹窗
3. 回到问题列表 → 该 issue 的更新时间已刷新
4. 详情页「更新历史」卡 → **没有**因评论产生的空白历史记录
5. dashboard 最近动态 → 出现「X 评论了问题 #N」

- [ ] **Step 4: 最终提交（如有验收修复）**

```bash
git add -A && git commit -m "fix(issues): 评论功能验收修复"
```

（无修复则跳过。）
