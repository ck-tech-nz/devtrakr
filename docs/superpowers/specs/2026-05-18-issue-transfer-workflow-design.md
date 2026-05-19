# Issue 转单工作流设计

**日期**: 2026-05-18
**作者**: Chunkai (CK) + Claude
**状态**: 设计 — 待评审

---

## 1. 目标

引入「转单」工作流,让 issue 在不同负责人之间显式流转,留下完整审计链路供未来 KPI/计费使用,并把列表里的「负责人」字段合并到「状态」单元格做动态交互(接单、确认、转单)。

同时改造创建路径:Phase 2 默认由 AI 根据成员描述自动分配,失败时降级为「待分配」由人接单。

---

## 2. 范围(今天交付)

**Phase 1(基础)**
- 状态枚举重命名 + 新增「待确认」
- 新表 `IssueAssignment`(完整事件流)
- `ProjectMember.is_manager` + `Issue.manager`(创建时快照)
- 4 个 API endpoint:claim / confirm / transfer / assign
- 动态状态单元格 + 转单弹窗
- 删除列表「负责人」列

**Phase 2(AI 自动分配)**
- `auto_assign_issue()` 在 issue 创建后自动挑人
- 复用现有 `LLMConfig` 与 wizard pipeline
- 集成到两个创建入口(home AI 向导 / 新建问题表单)

**Phase 3(本次不做)**
- 计费/扣费 UI(数据结构已就绪,后续基于 `IssueAssignment` 表查询)

**显式不做**
- 转单审批/拒绝流程(被转方可继续再转)
- 撤销/回滚转单
- 通知系统改造(复用现有 signal/Activity)

---

## 3. 状态机

**状态列表**: `未计划 / 待分配 / 待确认 / 进行中 / 已解决 / 已发布 / 已关闭`

**改动**
- 旧 `待处理` → 新 `待分配`
- 新增 `待确认`

**转换规则**

| 当前状态 | 动作 | 触发者 | 下一状态 | `IssueAssignment.action` |
|---|---|---|---|---|
| 待分配 | 一键接单 | 该 issue 所属项目的任意成员 | 进行中 | `claim` |
| 待分配 | 指派 | issue.manager | 待确认 | `assign` |
| 待确认 | 一键接受 | 当前 assignee | 进行中 | `confirm` |
| 待确认 | 转单 | assignee 或 issue.manager | 待确认 | `transfer` |
| 进行中 | 转单 | assignee 或 issue.manager | 待确认 | `transfer` |
| 进行中 | 标记已解决 | assignee | 已解决 | (无,沿用现有) |
| (Phase 2) 创建 | AI 自动分配 | 系统 | 待确认 | `ai_assign` |
| (Phase 2) 创建 | AI 失败/无候选 | 系统 | 待分配 | (无事件) |

**核心不变式**: `Issue.assignee` 始终等于该 issue 最新一条 `IssueAssignment.to_user`(若无事件则为 NULL,状态必为 `待分配` 或 `未计划`)。

---

## 4. 数据模型

### 4.1 `Issue` 改动

- `assignee` 字段语义:「当前应处理人」(每次转单立即更新,即使在「待确认」也已经指向新人)
- `manager: FK(User, null=True)` — 新增。创建时快照 `project` 的经理,后续不变
- `status` 枚举常量更新

### 4.2 `ProjectMember` 改动

- `is_manager: BooleanField(default=False)`
- 部分唯一索引:`UniqueConstraint(fields=['project'], condition=Q(is_manager=True), name='one_manager_per_project')`

### 4.3 新表 `IssueAssignment`

```python
class AssignmentAction(models.TextChoices):
    CLAIM = 'claim', '接单'
    ASSIGN = 'assign', '指派'
    AI_ASSIGN = 'ai_assign', 'AI分配'
    TRANSFER = 'transfer', '转单'
    CONFIRM = 'confirm', '确认'

class IssueAssignment(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name='assignments')
    action = models.CharField(max_length=20, choices=AssignmentAction.choices)
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='+',
    )  # claim/assign/ai_assign 时为 NULL
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='+',
    )  # 始终设值;SET_NULL 保护账号删除场景
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='+',
    )  # 实际操作人;AI 时为 NULL,经理代转时 ≠ from_user
    reason = models.TextField(blank=True, default='')  # 转单原因 / AI 推荐理由
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['issue', '-created_at'])]
```

### 4.4 不变式保证

所有写入都走 `apps/issues/services.py`,在事务内同时更新 `Issue.assignee + Issue.status + IssueAssignment`。Admin/管理脚本若直连改 `Issue.assignee`,需另外手动写事件 —— 此约束在 service 文档说明,不在 model 层 enforced(避免 signal 隐式复杂度)。

---

## 5. API

新增 4 个 endpoint,挂在 `IssueViewSet` 上,使用 `@action` 装饰器:

```
POST /api/issues/{id}/claim/      # 待分配 → 进行中
POST /api/issues/{id}/confirm/    # 待确认 → 进行中
POST /api/issues/{id}/transfer/   # 待确认/进行中 → 待确认
   body: {"to_user": int, "reason": str}
POST /api/issues/{id}/assign/     # 待分配 → 待确认 (经理用)
   body: {"to_user": int}
```

返回:更新后的 issue(同 list serializer 结构)。

### 5.1 Service 层签名(`apps/issues/services.py`)

```python
def claim_issue(issue: Issue, actor: User) -> IssueAssignment
def confirm_issue(issue: Issue, actor: User) -> IssueAssignment
def transfer_issue(issue: Issue, actor: User, to_user: User, reason: str) -> IssueAssignment
def assign_issue(issue: Issue, actor: User | None, to_user: User,
                 action: AssignmentAction = AssignmentAction.ASSIGN,
                 reason: str = '') -> IssueAssignment
def auto_assign_issue(issue: Issue) -> IssueAssignment | None  # Phase 2(Phase 1 留 stub)
def create_issue(*, project, title, ..., actor: User, assignee: User | None) -> Issue  # Phase 1 起就需要(unified create entry)
```

每个方法:
1. 校验状态-动作合法性 → 不合法 `raise InvalidTransition`
2. 校验权限 → 不通过 `raise PermissionDenied`
3. 事务内更新 + 写 `IssueAssignment` + 写 `Activity`

### 5.2 权限

| 动作 | 允许的 actor |
|---|---|
| claim | `actor` 是该 issue 所属项目的成员(经理也是成员) |
| confirm | `actor == issue.assignee` |
| transfer | `actor == issue.assignee` 或 `actor == issue.manager` |
| assign | `actor == issue.manager` |
| ai_assign | 系统调用(actor=None),无外部接口 |

「项目经理」判定:`ProjectMember.objects.filter(project=p, user=u, is_manager=True).exists()`,但具体 issue 用 `issue.manager == u`(快照)。

### 5.3 列表序列化器追加字段

- `can_claim: bool`
- `can_confirm: bool`
- `can_transfer: bool`
- `can_assign: bool`
- `manager_name: str | None`
- `assignments_count: int`(可选,用于详情页展开提示)

`can_*` 由 serializer 根据 `self.context['request'].user` 算好,前端 v-if 直接用。

---

## 6. 前端 UI

### 6.1 新组件 `IssueStatusCell.vue`

放在 `frontend/app/components/issue/StatusCell.vue`,接收 `{ issue, canClaim, canConfirm, canTransfer, canAssign }` props,emit `claim / confirm / transfer / assign` 事件。

渲染规则:

| 状态 | 当前用户视角 | 渲染 |
|---|---|---|
| 待分配 | can_claim | 主按钮「+ 接单」 |
| 待分配 | can_assign(经理) | 按钮「+ 接单」+ 副按钮「指派」 |
| 待分配 | 其他 | badge「待分配」 |
| 待确认 | assignee == self | 主按钮「✓ 接受」+ 副按钮「↪ 转单」 |
| 待确认 | issue.manager(且 assignee 不是 self) | badge「{name} 待确认」+ 副按钮「↪」 |
| 待确认 | 其他 | badge「{name} 待确认」 |
| 进行中 | assignee == self | badge「我处理中」+ 副按钮「↪」 |
| 进行中 | issue.manager(且 assignee 不是 self) | badge「{name} 处理中」+ 副按钮「↪」 |
| 进行中 | 其他 | badge「{name} 处理中」 |
| 已解决/已发布/已关闭 | 任何 | badge「{name} 已解决」(无操作) |
| 未计划 | 任何 | badge「未计划」(无 name) |

### 6.2 转单弹窗 `IssueTransferDialog.vue`

`UModal` 内:
- `USelect` 转给谁(候选 = 该 project 的所有 members,排除自己,显示 name + role)
- `UTextarea` 转单原因(必填,maxlength=500)
- 按钮「取消 / 确定转单」
- 提交成功后关闭并 emit `transferred` 让父组件 refresh

### 6.3 列表页 `pages/app/issues/index.vue`

- 删除「负责人」列
- 「状态」列宽扩大到容纳「{name} 处理中 ↪」(约 160px)
- 看板视图 `IssueCard.vue` 替换状态展示为同一 `StatusCell` 组件
- 抽取常量到 `frontend/app/constants/issueStatus.ts`(状态值、颜色映射、看板列顺序)

### 6.4 新建问题表单

- 「指派给」字段保留为**可选**
- 提交时:
  - 选中人 → 后端 `create_issue(assignee=...)`,事件 `assign`,状态 `待确认`
  - 留空(Phase 1)→ 状态 `待分配`
  - 留空(Phase 2)→ 后端调 `auto_assign_issue()`,成功 → `待确认`+`ai_assign`,失败 → `待分配`
- 创建后 toast 根据响应里 `issue.assignee` 是否为空决定:
  - 有 assignee → 「已创建,分配给 {assignee_name}」(不区分人工/AI,语言一致)
  - 无 assignee → 「已创建,等待人工接单」

---

## 7. Phase 2 — AI 自动分配

### 7.1 公共入口

在 `apps/issues/services.py` 提供 `create_issue(...)`:

```python
def create_issue(*, project, actor: User, title, description, priority,
                 assignee: User | None = None, ...) -> Issue:
    issue = Issue.objects.create(
        project=project,
        manager=_resolve_project_manager(project),  # 快照
        title=title, description=description, priority=priority,
        status='待分配',  # 默认值,可能被下方流程改写
        created_by=actor,
        ...
    )
    if assignee is not None:
        assign_issue(issue, actor=actor, to_user=assignee)  # → 待确认 + assign
    else:
        auto_assign_issue(issue)  # Phase 1 = stub no-op;Phase 2 实现;失败时保持 待分配
    return issue
```

被两个入口调用:
1. `services_ai_wizard.py` 的 commit 步骤
2. `IssueViewSet.create()`

### 7.2 `auto_assign_issue` 细节

```python
def auto_assign_issue(issue: Issue) -> IssueAssignment | None:
    members = ProjectMember.objects.filter(project=issue.project)\
        .exclude(personal_description='')\
        .select_related('user', 'role')
    if not members.exists():
        return None
    
    config = LLMConfig.objects.filter(is_default=True, is_active=True).first()
    if not config:
        return None
    
    prompt = _build_assign_prompt(issue, members)
    try:
        result = _call_llm_json(config, prompt, timeout=15)  # {assignee_id: int, reason: str}
    except Exception as e:
        logger.warning("auto_assign LLM failed: %s", e)
        return None
    
    user = User.objects.filter(
        id=result.get('assignee_id'),
        project_memberships__project=issue.project,
    ).first()
    if not user:
        return None
    
    return assign_issue(
        issue, actor=None, to_user=user,
        action=AssignmentAction.AI_ASSIGN,
        reason=str(result.get('reason', ''))[:500],
    )
```

### 7.3 Prompt 模板

```
你是项目工单分配助手。请根据问题描述,从候选项目成员中挑选最合适的一位。
只返回 JSON 对象:{"assignee_id": <整数>, "reason": "<不超过200字的推荐理由>"}
不要输出 markdown 代码块,不要输出 JSON 之外的任何内容。

【问题】
标题: {title}
描述: {description}
标签: {labels}
优先级: {priority}

【候选成员】
{for m in members}
- id={m.user_id}, 姓名={m.user.username}, 角色={m.role.name or '未设置'}, 描述="{m.personal_description}"
{endfor}
```

### 7.4 失败降级

任何错误(timeout / JSON 解析失败 / 返回非项目成员 id / LLM 未配置)→ `auto_assign_issue` 返回 `None`,issue 已经以 `待分配` 状态创建,流程不阻断。前端按返回数据(`issue.status` 与 `issue.assignee`)显示对应 toast。

---

## 8. 数据迁移

### 8.1 Schema 迁移 `0010_assignment_workflow.py`

- 新建 `IssueAssignment` 表
- 给 `ProjectMember` 加 `is_manager` 字段 + 部分唯一索引
- 给 `Issue` 加 `manager` FK

### 8.2 Data 迁移(同一 migration,RunPython)

1. 所有 `Issue.status == '待处理'` → `'待分配'`
2. 所有现有 `Issue` 若 `assignee` 非空 → 创建一条 seed `IssueAssignment`:
   - `action='assign'`, `from_user=NULL`, `to_user=issue.assignee`, `actor=NULL`, `reason='历史数据 seed'`, `created_at=issue.created_at`
3. `Issue.manager` 保持 NULL(Phase 1 无历史经理数据;之后新建项目设经理后再追)

### 8.3 SiteSettings 迁移 `apps/settings/migrations/0007_update_issue_statuses.py`

模仿现有 `0006_update_issue_statuses.py`,把单例的 `issue_statuses` JSON 替换为新列表:
```python
NEW = ["未计划", "待分配", "待确认", "进行中", "已解决", "已发布", "已关闭"]
OLD = ["未计划", "待处理", "进行中", "已解决", "已发布", "已关闭"]
```

### 8.4 全局替换清单

**Backend Python**
- `apps/issues/models.py`: IssueStatus 枚举
- `apps/issues/views.py`: `status_order` Case-When 硬编码
- `apps/settings/models.py`: `default_issue_statuses()`
- `apps/issues/services_ai_wizard.py`(若有)
- 所有 `tests/test_*.py` 中 hardcoded `"待处理"`(~15 文件)
- `tests/factories.py`

**Frontend**
- `frontend/app/pages/app/issues/index.vue`: `statusColor`, 看板列, 创建表单默认状态, filter options
- `frontend/app/pages/app/issues/[id].vue`(详情页)
- `frontend/app/components/IssueCard.vue`
- `frontend/app/data/mock.ts`
- 抽取到 `frontend/app/constants/issueStatus.ts`

---

## 9. 测试

新文件 `backend/tests/test_assignment_workflow.py`:

- 每种合法转换 → 正确更新 `Issue.assignee`、`Issue.status`,正确写入 `IssueAssignment`
- 每种非法转换 → `InvalidTransition`
- 权限矩阵:
  - 非项目成员 claim 失败
  - 非 assignee confirm 失败
  - 非 assignee 且非 manager transfer 失败
  - 经理在「待分配」上能 assign,在「进行中」上不能 confirm
- 不变式:任意操作后 `Issue.assignee == issue.assignments.last().to_user`
- 转单链:A→B→C→D,验证 `assignments` 顺序与 from/to 配对正确
- Data migration:旧 `待处理` issue 被迁移到 `待分配` + seed assignment 创建

新文件 `backend/tests/test_project_manager.py`:
- 部分唯一索引拦截「一个项目两个经理」
- `Issue.manager` 创建时正确快照
- 项目换经理后,旧 issue.manager 不变

新文件 `backend/tests/test_auto_assign.py`(Phase 2):
- mock `_call_llm_json` 返回合法 → 创建事件
- mock LLM 失败 → `status='待分配'`
- mock LLM 返回非成员 id → 降级
- 无成员 / 无 LLMConfig → 降级

更新现有测试,把 `"待处理"` 替换为 `"待分配"`(约 15 文件)。

---

## 10. 向后兼容

- API:接收旧 `status="待处理"` 时,序列化器自动映射为 `"待分配"`,response 始终返回新值。保留 2 个 release 后移除。
- 外部 API(`apps/issues/external/`)同样处理。
- Frontend 不读旧值。

---

## 11. 风险与开放问题

- **AI 同步调用阻塞创建**:`auto_assign_issue` 最长 15s 超时,creation 接口可能阻塞最多 15s。可接受 → MVP 不引入 celery。后续若超时反馈差,改异步 + websocket 通知。
- **Issue.manager NULL 兼容性**:历史 issue 全部 `manager=NULL` → 没人能在它们上面 assign/transfer 来自「经理」路径,只能走 assignee 路径。可接受(老 issue 通常已经在进行中或已解决)。
- **看板视图组件复用**:`StatusCell` 同时用于表格和看板卡,要保证两种容器下排版自适应。设计阶段确认尺寸约束。
- **AI prompt 注入风险**:`personal_description` 由用户填,理论上可以注入 prompt 改变 AI 输出。Phase 2 用 system+user role 分离 + 在 prompt 里明确「仅返回 JSON」缓解;不做内容审查。

---

## 12. 验收标准

**Phase 1 完成**
- [ ] 列表中所有 `待处理` 已变为 `待分配`,新增 `待确认` 出现在筛选下拉
- [ ] 「负责人」列消失,「状态」列展示动态形态(按钮/badge with name)
- [ ] 待分配 → 一键接单 → 进行中,assignee 是自己
- [ ] 经理在新建表单选择某人 → 该 issue 进入「待确认」
- [ ] 该人看到「✓ 接受 / ↪ 转单」按钮
- [ ] 转单弹窗能选成员 + 填原因,提交后该 issue 进入新人的「待确认」
- [ ] `IssueAssignment` 表里完整记录链路
- [ ] 一个项目只能设一个经理

**Phase 2 完成**
- [ ] 新建问题(留空指派给)→ AI 自动选了某成员,状态变 `待确认`
- [ ] 若 LLM 不可用 → 创建成功,状态 `待分配`
- [ ] home 页 AI 向导创建的 issue 同样走自动分配
