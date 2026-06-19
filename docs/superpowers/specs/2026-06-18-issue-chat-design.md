# Issue Chat — 评论弹窗 + 可聊天 设计文档

- **日期**: 2026-06-18
- **状态**: 已批准设计，待实现计划
- **作者**: ck + Claude

## 1. 目标

当一个问题（Issue）有新评论时，**负责人（assignee）、协助人（helpers）、以及评论中被 `@` 提及的人**会在前端收到一个右下角聊天气泡式的提醒，并可以**直接在气泡里回复（即新增一条评论）**，形成类似微信/Intercom 的聊天体验。

回复 = 在该问题上新增一条 `IssueComment`。每个问题 = 一个会话。

## 2. 关键决策（已与用户确认）

| # | 决策 | 选择 |
|---|---|---|
| 1 | UI 形态 | **右下角聊天气泡**（微信/Intercom 风格），每个问题一个会话，回复=新增评论 |
| 2 | 实时性 | **WebSocket 真实时**（Django Channels + ASGI + Redis channel layer） |
| 3 | 会话列表范围 | **有我参与且有评论的问题**：我是负责人/协助人、被 `@`、或我评论过，且该问题有评论 |
| 4 | 与通知铃铛的关系 | **聊天独立于铃铛**：聊天自带按问题的未读追踪，不写 `Notification` 表；铃铛仍只管 `@`提及/广播/系统 |
| 5 | 新评论到达表现 | **预览条 + 声音 + 未读角标+1**；点预览直接打开该会话 |
| 6 | 回复输入框 | **轻量文本 + `@`提及**（复用 `MentionDropdown`），不支持附件/图片上传 |
| 7 | 数据模型（Fork 1） | **A1**：单表 `IssueChatParticipant` 同时承担成员关系 + 已读指针 |
| 8 | 发送路径（Fork 2） | **B1**：接收走 WebSocket，发送复用现有 REST `POST .../comments/`，WS 仅推送 |

## 3. 现状（已存在，复用）

- `IssueComment` 模型 + 完整评论 UI（`frontend/app/components/issue/IssueComments.vue`），含 Markdown 编辑器、`@[name](user:id)` 提及、增/改/删。
- `@` 提及**已会**为被提及者创建 `Notification`（`backend/apps/notifications/services.py` 的 `create_comment_mention_notifications`、`extract_mentioned_user_ids`）。本设计**保持该行为不变**——被提及者照常进铃铛，同时也进聊天气泡（两条平行通道）。
- 通知铃铛 + 下拉，60 秒轮询（`frontend/app/composables/useNotifications.ts`、`NotificationBell.vue`）。**与聊天无关，不改动。**
- `Issue.assignee`（FK，负责人，`related_name=assigned_issues`）、`Issue.helpers`（M2M，协助人，`related_name=helped_issues`）。
- `@`提及前端组件：`MentionDropdown.vue`、`MarkdownEditor.vue` 的 `@` 触发检测、`useMentionMarkdown.ts` 渲染。
- 后端**已用 uvicorn ASGI** 启动（`backend/Dockerfile` CMD `uvicorn config.asgi:application`）——加 Channels websocket 路由无需换服务器。
- Redis 已存在（Celery broker `redis://127.0.0.1:6379/0`）——channel layer 复用同一 Redis，另用 DB `/1`。

## 4. 后端设计

### 4.1 数据模型（`backend/apps/issues/models.py`）

```python
class IssueChatParticipant(models.Model):
    """聊天会话成员 + 已读指针。一行 = 某用户参与某问题的评论会话。"""
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="chat_participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="issue_chats")
    last_read_comment = models.ForeignKey(
        IssueComment, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("issue", "user")]
        indexes = [models.Index(fields=["user", "-updated_at"])]
```

- **未读数**（单会话）= `IssueComment.objects.filter(issue=issue, id__gt=last_read_comment_id).exclude(author=user).count()`。`IssueComment.id` 单调递增，故 `id__gt` 等价于"更新的"。`last_read_comment=None` → 全部计入。
- **成员关系** = 该行是否存在。会话列表 = `IssueChatParticipant.objects.filter(user=me).select_related("issue")`，按 `-updated_at` 排序。这天然覆盖"被 `@` 一次 → 一直留在我的列表"的情形。

迁移用 `makemigrations` 生成（遵循项目规范，不手写）。

### 4.2 服务（`backend/apps/issues/services.py`，新建或扩展）

```python
def participants_for_comment(comment) -> set[User]:
    issue = comment.issue
    users = set()
    if issue.assignee_id:
        users.add(issue.assignee)
    users.update(issue.helpers.all())                                       # 协助人
    users.update(User.objects.filter(id__in=extract_mentioned_user_ids(comment.content)))  # @提及
    users.update(u for u in existing_chat_participants(issue))              # 已在会话里的人继续收到
    return {u for u in users if u.is_active}

def broadcast_comment(comment):
    recipients = participants_for_comment(comment)
    author = comment.author
    # upsert 成员行；作者自己的消息自动已读
    for user in recipients | {author}:
        p, _ = IssueChatParticipant.objects.get_or_create(issue=comment.issue, user=user)
        if user == author:
            p.last_read_comment = comment
        p.save(update_fields=["last_read_comment", "updated_at"])           # bump updated_at
    # 推送给除作者外的所有人
    for user in recipients - {author}:
        _push_ws(user.id, comment)                                          # group_send → chat_user_<id>
```

行为保证：
- **作者排除**于推送，且对自己的消息自动已读。
- **去重天然**：既是协助人又被 `@` 的人只在集合里出现一次，只推一次。
- **已在会话者持续接收**：会话一旦开始，后续评论所有参与者都继续收到，即便某条评论没 `@` 他们。

`_push_ws` 用 `asgiref.sync.async_to_sync(channel_layer.group_send)(f"chat_user_{user_id}", {...})` 从同步 Django 推入 Channels。channel layer 不可用时（如无 Redis 的 headless 环境）须优雅降级：评论照常保存，仅跳过推送。

### 4.3 WebSocket 层（Django Channels）

- **依赖**：`backend/pyproject.toml` 增 `channels`、`channels-redis`。
- **channel layer 配置**（`settings.py`）：`channels_redis.core.RedisChannelLayer`，地址 `CHANNEL_REDIS_URL`（默认 `redis://127.0.0.1:6379/1`，与 Celery 的 `/0` 分库）。测试用 `channels.layers.InMemoryChannelLayer`。
- **`backend/config/asgi.py`** 改为：
  ```python
  application = ProtocolTypeRouter({
      "http": get_asgi_application(),
      "websocket": JWTAuthMiddleware(URLRouter(chat_ws_urlpatterns)),
  })
  ```
  uvicorn 已是 ASGI 服务器，**无需更换**。
- **JWT 鉴权中间件**（新）：从 WS query string 读 `?token=<access>`，用 SimpleJWT（与 REST 同一 `AccessToken`）校验，设 `scope["user"]`；无效则 `close(code=4401)`。此处用 JWT 而非 cookie/session（项目认证即 JWT）。
- **`ChatConsumer`**（`AsyncWebsocketConsumer`）：连接时加入组 `chat_user_<id>`；**仅推送**（把 `comment.new` 事件转发到 socket）；忽略入站消息（回复走 REST，见 B1）。路径 `/ws/chat/`。

### 4.4 REST 端点（扩展 `backend/apps/issues/`）

| 方法与路径 | 用途 |
|---|---|
| `GET /api/issues/chat/conversations/` | 我的会话列表：`[{issue_id, issue_number, issue_title, last_comment:{author_name, snippet, created_at}, unread_count}]`，按 `-updated_at` 排序，分页 |
| `GET /api/issues/chat/unread-total/` | 单个整数，供气泡角标初始加载 |
| `POST /api/issues/chat/conversations/<issue_id>/read/` | 把 `last_read_comment` 推进到最新评论 |
| `GET /api/issues/<id>/comments/` | **（已存在）** 加载会话完整消息历史 |
| `POST /api/issues/<id>/comments/` | **（已存在）** 发送回复——创建后新增调用 `broadcast_comment(comment)` |

- 全部限定为已认证用户，且限定其可见的问题（复用现有 issue 权限/queryset 范围限定）。
- 会话列表的 `unread_count` 用单条带注解（annotate）查询计算，避免 N+1。

## 5. 前端设计

### 5.1 `useChat.ts`（新组合式，`frontend/app/composables/`）

唯一状态来源：
- 已认证时在 app 挂载阶段开 WebSocket：`wss?://…/ws/chat/?token=<access>`。带退避的自动重连；遇 `4401` 关闭时刷新 JWT（复用 `useApi` 的刷新逻辑）后重连。
- 状态（`useState`）：`conversations[]`、`activeIssueId`、打开会话的 `messages[]`、`unreadTotal`。
- 收到 `comment.new` 事件：
  - 若其 issue == `activeIssueId` 且面板打开 → 追加消息，自动标已读（`POST …/read/`）；
  - 否则 → 该会话置顶、`unread_count++`、`unreadTotal++`，并弹**预览条 + 声音**。
- 方法：`loadConversations()`、`openConversation(issueId)`（用已有 `GET …/comments/` 加载线程并标已读）、`sendReply(issueId, content)`（REST `POST …/comments/`，即 B1）、`markRead(issueId)`。

### 5.2 `ChatBubble.vue`（新组件，全局）

- 右下角浮动按钮 + 未读角标。
- 面板两个视图：**会话列表** ↔ **当前会话线程**（聊天布局：他人消息靠左、我的靠右，经 `useMentionMarkdown()` 渲染）。
- **轻量回复输入**：`textarea` 接入已有 `MentionDropdown.vue` + 从 `MarkdownEditor.vue` 抽出的 `@` 触发检测（若尚不可复用则抽成小组合式）。回车发送；无附件上传（按决策 6）。
- 在已认证布局/`app.vue` 挂载一次，常驻所有 `/app` 页面。

### 5.3 预览条 + 声音

- 自定义小预览组件（头像 + 名字 + 摘要，约 5 秒自动消失，点击 → `openConversation`）。
- 声音 = 打包的短音频，经 `new Audio()` 播放，受浏览器自动播放策略约束（首次用户交互后才能响）。

## 6. 基础设施 / 代理

- **开发**：`nuxt.config.ts` 的 `nitro.devProxy` 增 `/ws/`，`ws: true`，target `${apiBase}`。
- **生产**：增 `/ws/**` 的 `routeRules` 代理（nitro 转发 upgrade）；默认走 nitro 代理保持同源。部署时前置（nginx/traefik）须放行 WebSocket upgrade 头——交付时标注。可选公开 `NUXT_PUBLIC_WS_URL` 直连（同 server-monitor URL 模式）作为后备。
- **Redis**：复用现有实例（Celery broker），DB `/1`，经 `CHANNEL_REDIS_URL`。当前 `docker-compose.yml` 无 `redis` service（外部提供），故这是 env/`.env` 事项，非 compose 改动——交付时文档化。

## 7. 测试

- **后端**（`pytest-django`）：`participants_for_comment` 的接收者/去重/自我排除逻辑；未读数计算；conversations + read 端点；`ChatConsumer` 连接/鉴权/接收推送（`channels.testing.WebsocketCommunicator` + `InMemoryChannelLayer`）。
- **前端**（`npm run test`，`@nuxt/test-utils`——项目实际门禁）：`ChatBubble` 渲染、未读角标、回复发送、打开即标已读。
  - 注：`nuxi typecheck` 因 Nuxt UI 升级在 `main` 上已红；不把既有报错当新错误。

## 8. 明确不做（YAGNI）

不构建：正在输入指示器、在线/在场状态、已读回执（"已被谁看过"）、消息表情/反应、气泡内编辑或删除评论（编辑仍在问题页）、快速回复内的附件/图片上传、与问题无关的群聊/私聊、超出应用内 toast+声音的推送/桌面通知、消息搜索。

## 9. 已知问题与处理

- **JWT 连接期内过期**：连接在 open 时鉴权；token 刷新或 `4401` 关闭时用新 token 重连。
- **离线期间漏事件**（WS 曾断）：（重）连时 `loadConversations()` 从 DB 重新水合未读数——WS 负责活跃推送，DB 才是真相源，不会永久丢失。
- **headless/CI 无 channel layer**：回落 `InMemoryChannelLayer`；`broadcast_comment` 在 layer/Redis 不可用时优雅降级（评论仍保存）。

## 10. 部署 / Deploy

### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CHANNEL_REDIS_URL` | `redis://127.0.0.1:6379/1` | Django Channels channel layer 使用的 Redis 地址。测试/生产须指向可达的 Redis；复用 Celery 同一实例，DB 用 `/1`（Celery broker 占 `/0`）。 |

在 `backend/.env.example` 中已注明此变量。

### ASGI 服务器

后端已以 `uvicorn config.asgi:application` 启动（`backend/Dockerfile` CMD），原生支持 ASGI。加入 Django Channels 的 `ProtocolTypeRouter` 后**无需更换服务器**，uvicorn 直接处理 WebSocket 升级。

- **生产**：`uvicorn config.asgi:application`（现有 Dockerfile CMD，不变）。
- **开发 runserver**：`daphne`（由 `channels` 添加到 `INSTALLED_APPS` 后自动替换 `manage.py runserver`，仅本地开发使用）。

### 反向代理（nginx / traefik）

前置代理**必须**将 `/ws/` 路径的 WebSocket 升级头透传给后端，否则浏览器 WebSocket 连接将被拒绝（HTTP 101 协商失败）。

**nginx 示例**（在 backend upstream 的 `location` 块中追加）：

```nginx
location /ws/ {
    proxy_pass http://backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 86400s;
}
```

**traefik**：确认中间件或路由规则未剥离 `Upgrade` / `Connection` 头（默认 traefik 会透传，无需额外配置）。

### 前端代理

- **开发**：`nuxt.config.ts` 的 `nitro.devProxy` 已添加 `/ws/`（`ws: true`），见第 6 节。
- **生产**：Nitro `routeRules` 转发 `/ws/**` upgrade，或由前置代理直接将 `/ws/` 指向后端。

### 启动验证

部署后检查：

```bash
# uvicorn 无报错启动（ProtocolTypeRouter + consumer 导入正常）
uv run uvicorn config.asgi:application --port 8001

# HTTP 端点响应正常
curl http://localhost:8001/api/about/

# WebSocket 握手（需 Redis 在线 + 有效 JWT）
wscat -c "ws://localhost:8001/ws/chat/?token=<access_token>"
```
