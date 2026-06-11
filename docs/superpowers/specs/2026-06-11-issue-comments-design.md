# Issue 评论功能设计（IssueComment）

日期：2026-06-11
状态：已确认（用户审定）
范围：全栈 —— 后端模型 + API + issue 详情页评论区 UI，参考 GitHub issue 评论体验。

## 背景与目标

DevTrack 的 issue 目前只有系统事件记录（`Activity`、`IssueAssignment`），没有用户讨论能力。
本功能为 issue 增加 GitHub 风格的评论：Markdown 编辑、@提及、文件内联上传、作者可编辑删除。

明确不做（YAGNI，已与用户确认）：

- 「评论并关闭」按钮（状态变更仍走现有状态按钮）
- 评论软删除、编辑历史
- 表情回应（reactions）、嵌套回复
- 评论分页（单 issue 评论量预期很小）
- 评论附件同步到侧栏附件列表（文件只内联在评论 markdown 里，与 GitHub 一致）
- 负责人「每条评论都收通知」（后续按需再加，本期只做 @提及通知）

## 与 Activity 的关系（设计澄清）

`Activity` 是系统事件日志，**保持原样，不删不改语义**。它有两个在用的消费方：

1. Dashboard 最近动态（`DashboardRecentActivityView`，`backend/apps/issues/views.py`）
2. KPI 重修/回归指标（`backend/apps/kpi/metrics.py`）

评论是用户内容，独立建模。发评论时追加写一条 `Activity(action="commented")`，
让 dashboard 动态流可见「X 评论了 #123」。

## 1. 数据模型（backend/apps/issues/models.py）

```python
class IssueComment(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="issue_comments", verbose_name="作者",
    )
    content = models.TextField(verbose_name="内容")  # markdown 原文，附件以内联链接存在
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "问题评论"
        verbose_name_plural = "问题评论"
        ordering = ["created_at"]  # 旧→新，同 GitHub
        indexes = [models.Index(fields=["issue", "created_at"])]
```

要点：

- 整型自增主键，与 issues app 内其他模型一致（不学 kpi 的 UUID）
- `author` 用 `SET_NULL`：用户注销后讨论记录保留（同 `Activity.user` / `Issue.created_by` 模式）
- 硬删除；`updated_at > created_at`（容差 1 秒）即视为「已编辑」
- 需要 `makemigrations issues` 生成迁移；注册到 admin

## 2. API（backend/apps/issues/urls.py + views.py + serializers.py）

沿用现有子资源模式：APIView + `permission_classes = [IsAuthenticated]`
（与 `IssueAttachmentsView`、`IssueRelatedView` 一致），对象级权限在视图内显式判断。

| 方法与路径 | 行为 | 权限 |
|---|---|---|
| `GET /api/issues/{id}/comments/` | 全量列表，旧→新，`select_related("author")` | 登录即可 |
| `POST /api/issues/{id}/comments/` | 创建，`{content}` 非空、≤65536 字符 | 登录即可 |
| `PATCH /api/issues/{id}/comments/{cid}/` | 编辑 content | 仅作者，否则 403 |
| `DELETE /api/issues/{id}/comments/{cid}/` | 硬删除 | 作者本人或管理员（`is_superuser` 或 `管理员` 组），否则 403 |

副作用：

- POST 成功后：
  - `Activity.objects.create(user=actor, issue=issue, action="commented")`
  - 对 content 里的 @提及发通知（old_content=""）
  - **bump issue 的 `updated_at`**，让问题列表/看板的更新时间反映评论动态：
    `Issue.objects.filter(pk=issue.pk).update(updated_at=timezone.now())`。
    必须用 queryset `.update()` 而非 `issue.save()`——Issue 挂了 simple_history，
    `save()` 会写一条无字段变化的历史快照，污染「更新历史」卡。
    只动 `updated_at`、不动 `updated_by`：后者语义是「谁改了 issue 字段」，
    且在历史追踪范围内，绕过 history 修改会让下次真实编辑的 diff 出现虚假变更。
- PATCH 成功后：对**新增**的 @提及发通知（old/new content diff，同 description 现有处理）；
  不写 Activity、不 bump `updated_at`（编辑既有评论不算新讨论动态）
- DELETE：无副作用（已发出的通知不撤回，不 bump `updated_at`）

序列化器 `IssueCommentSerializer` 字段：
`id, author, author_name, content, created_at, updated_at, is_edited`。
`author_name` 取 `user.name or user.username`（同现有惯例）；
`is_edited = updated_at - created_at > 1s`。

视图拆两个类：`IssueCommentsView`（GET/POST，挂 `<int:pk>/comments/`）、
`IssueCommentDetailView`（PATCH/DELETE，挂 `<int:pk>/comments/<int:comment_id>/`）。
comment 必须属于该 issue（双键查询，跨 issue 的 comment_id 返回 404）。

管理员判断与 `IssueCreateUpdateSerializer._user_can_edit_estimated_hours` 同款：
`user.is_superuser or user.groups.filter(name="管理员").exists()`。

## 3. @提及通知（backend/apps/notifications/services.py）

新增：

```python
def create_comment_mention_notifications(*, comment, old_content: str, new_content: str, actor):
```

- 复用 `extract_mentioned_user_ids`，只对「新增提及 − actor 本人」发
- `Notification.Type.MENTION`，`source_issue=comment.issue`（前端点击可跳转 issue）
- 标题：「{actor 名} 在 #{issue.pk} 的评论中提到了你」，content 取评论前 100 字摘要

不改动现有 `create_mention_notifications`（description 用）的签名和行为。

## 4. 前端（Nuxt）

新组件 `frontend/app/components/issue/IssueComments.vue`：

- props 只有 `issueId: number`，组件自治：自己加载 `GET /api/issues/{id}/comments/`、
  维护本地列表状态（useApi）
- 放置位置：`pages/app/issues/[id].vue` 主栏（左侧 2 列）底部，AI 分析卡之后
- 标题「评论 (N)」

每条评论（GitHub 风格卡片）：

- 头部：作者头像/名字 + 绝对时间 + 「已编辑」标记（is_edited 时）
- 正文：`MarkdownView` 渲染（@提及高亮、附件卡片均已支持）
- 操作：本人 → 编辑 + 删除；管理员 → 删除；其他人无操作入口
  （前端用 `useAuth` 的当前用户 id + `hasGroup('管理员')` 判断显隐，后端为最终权威）
- 编辑：该条就地切换为 `MarkdownEditor`，保存（PATCH）/取消
- 删除：确认对话框（复用页面现有确认模式）后 DELETE

底部评论框：

- `MarkdownEditor`（默认 edit 模式，自带 Write/Preview、@提及、工具栏、拖拽/粘贴/选择上传）
- 「评论」主按钮，内容为空或提交中时禁用
- 提交成功：清空编辑器、新评论追加到列表底部
- 提交失败：保留草稿内容，toast 报错

UI 文案全部中文。不涉及新页面/导航/路由，无需改 `sync_page_perms`、
`useNavigation.ts`、`auth.global.ts`。

## 5. 错误处理

- 后端：content 空白/超长 → 400；非作者 PATCH、非作者非管理员 DELETE → 403；
  comment 不属于该 issue 或不存在 → 404；未登录 → 401
- 前端：加载失败显示重试提示；提交/编辑/删除失败 toast 并保留用户输入

## 6. 测试

后端 `backend/tests/test_issue_comments.py`（pytest + factory-boy，复用 conftest fixtures）：

- 创建评论 → 201，列表按时间正序返回
- content 空 / 超长 → 400
- 作者编辑自己的评论 → 200，is_edited 翻转
- 他人编辑 → 403；管理员编辑他人评论 → 403（管理员只可删不可改）
- 作者删除 → 204；管理员删除他人评论 → 204；普通他人删除 → 403
- POST 后产生 `Activity(action="commented")`
- POST 后 issue 的 `updated_at` 被刷新，且**不**新增 issue 历史快照
  （`issue.history.count()` 不变，更新历史不被污染）
- content 含 @提及 → 产生 MENTION 通知；编辑新增提及 → 只对新增者发；@自己不发
- 跨 issue 的 comment_id → 404；未登录 → 401

前端：`IssueComments` 组件测试（@nuxt/test-utils，mock API）：渲染评论列表、
发表评论流程、权限按钮显隐。

## 实施备注

- 分支：`feat/issue-comments`（自 main 切出）
- 后端先行（模型→迁移→API→测试），前端随后（组件→接入详情页→组件测试）
