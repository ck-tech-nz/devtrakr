# TODOS

> 由 /ship 2026-06-11 创建。条目按组件分组、组内按优先级排序;来源是 feat/issue-comments 的多路 review(具体 file:line 见 PR #9 body 的 Follow-ups)。

## Issues / 评论

### 评论列表分页

**What:** GET /api/issues/{pk}/comments/ 接入 DefaultPagination(count/next/previous/results 信封),前端评论区改为分页/懒加载旧评论。

**Why:** 当前是全 API 唯一裸数组、无上限的列表端点;单条评论上限 64KB,热点 issue 积累后每次打开详情页都拉全量,载荷与渲染都失控(perf/api-contract/adversarial 三方确认)。

**Context:** backend/apps/issues/views.py IssueCommentsView.get 直接 `Response(serializer.data)`;frontend/app/components/issue/IssueComments.vue onMounted 一次性 loadComments。趁端点新、无旧消费者时改契约代价最小;改时同步考虑「评论加载提前并行」条目。

**Effort:** M
**Priority:** P1
**Depends on:** None

### 评论端点权限对齐 FullDjangoModelPermissions

**What:** IssueCommentsView / IssueCommentDetailView 接入项目权限体系(view/add/change/delete_issuecomment),并在 page_perms 中给相应组配权。

**Why:** 现在仅 IsAuthenticated:无 issues.view_issue 的用户能读任意 issue 的完整讨论,只读组(只读成员)能发/改/删评论——与项目「view_* 才能 GET」的惯例相悖(security/api-contract/adversarial 三方确认)。

**Context:** backend/apps/issues/views.py:547,582;附件/历史等兄弟子资源端点同样是裸 IsAuthenticated,属于同一个既有模式的缺口,对齐时应一并评估。会改变现有组的行为,需要产品确认只读组是否应能评论。

**Effort:** M
**Priority:** P1
**Depends on:** 产品确认只读组评论权

### 评论删除留痕

**What:** 删除评论时写 Activity(action="comment_deleted") 或改软删;至少管理员代删要可追溯。

**Why:** 现为无审计硬删,且发评论的副作用(commented Activity、updated_at bump)不回滚:动态流显示「评论了」但评论已不存在;KPI 首次响应可发评论得分后删除,信用保留(red-team)。

**Context:** backend/apps/issues/views.py IssueCommentDetailView.delete;KPI 侧 apps/kpi/metrics.py 首响以 Activity 计时。

**Effort:** M
**Priority:** P2
**Depends on:** None

### @提及通知正文清洗

**What:** 通知 content 在截断前剥离 issue 提及标记、图片/附件 markdown 语法(用户提及已还原)。

**Why:** 通知中心目前可能显示残缺的 markdown 源码,且 [:100] 截断会把语法拦腰截断;同文件 create_mention_notifications 用的是干净格式,两者不一致(red-team)。

**Context:** backend/apps/notifications/services.py create_comment_mention_notifications 的 `content=MENTION_RE.sub(...)[:100]`。

**Effort:** S
**Priority:** P2
**Depends on:** None

### 评论 is_edited 改用显式 edited_at 字段

**What:** 用 nullable edited_at 替代「updated_at - created_at > 1 秒」的容差判定。

**Why:** 创建后 1 秒内的真实编辑不会被标记「已编辑」;时间差启发式不如显式字段诚实(adversarial L6)。

**Context:** backend/apps/issues/serializers.py get_is_edited;需新建迁移(规则:Django 生成的迁移不可改,新建即可)。

**Effort:** S
**Priority:** P3
**Depends on:** None

## Issues / 看板

### kanban 列加载失败的可见反馈

**What:** reset/loadMore 失败时给该列可见的错误态+重试入口,而不是 console.error 后静默装空。

**Why:** 瞬时网络错误会让列显示 0 条且无任何提示,与「确实没有问题」无法区分;评论区已有 error+retry 范式可复用(adversarial M2 / red-team)。

**Context:** frontend/app/composables/useKanbanIssues.ts reset/loadMore 的 catch;loadMore 404 止损已在本分支修复,这里补 UI 反馈。

**Effort:** S
**Priority:** P2
**Depends on:** None

### 看板列虚拟滚动或保留上限

**What:** 为可滚动列加窗口化渲染(或对已加载项设上限),col.count 已提供真实总数。

**Why:** 无限滚动只增不减,大列(如数百条已关闭)在 4-8 列同时累积数千 DOM 节点,拖拽命中与滚动性能退化(performance)。

**Context:** frontend/app/components/shared/KanbanBoard.vue v-for + useKanbanIssues.loadMore push。

**Effort:** L
**Priority:** P3
**Depends on:** None

### 分页漂移的卡片丢失提示

**What:** 翻页期间他人改动导致跨页边界的卡片被跳过时,给「数据已变化,刷新」提示或改游标分页。

**Why:** 页码分页 + 并发编辑会静默漏卡,直到下次 reset 才恢复;现有 id 去重只解决重复、不解决遗漏(adversarial M4)。

**Context:** frontend/app/composables/useKanbanIssues.ts loadMore 注释已承认漂移;后端 DefaultPagination 为页码式。

**Effort:** M
**Priority:** P3
**Depends on:** None

## Issues / 通用

### 评论加载与页面主数据并行

**What:** IssueComments 的首次拉取不再等待详情页 5 路 Promise.all 完成(issue id 路由里已知)。

**Why:** 评论请求被串行在最慢的请求之后,白等一整轮(performance)。

**Context:** frontend/app/pages/app/issues/[id].vue 的 `v-if="!isNewIssue && issue?.id"` 门控;可改传 Number(route.params.id)。

**Effort:** S
**Priority:** P3
**Depends on:** 评论列表分页(顺手一起改)

### 管理员判定改用模型权限

**What:** 后端 _is_manager 的「管理员」组名字符串与前端 hasGroup('管理员') 改为 issues.delete_issuecomment 等模型权限判定,并入 page_perms 配组。

**Why:** 组名是管理界面可改的魔法字符串:改名静默失去管理能力,新建同名组凭空获得删任意评论权;失败方向是 fail-closed 所以不紧急(security)。

**Context:** backend/apps/issues/views.py _is_manager;frontend/app/components/issue/IssueComments.vue isAdmin。

**Effort:** M
**Priority:** P2
**Depends on:** 评论端点权限对齐(同一套配组)

## Settings / 站点配置

### 颜色 widget 往返保留未知键

**What:** get_context 改为保留原对象仅覆盖 value/label/background 三键,模板 JS 就地改键而非重建对象。

**Why:** 现在管理员每次保存都会静默抹掉 JSON 里的额外元数据键(未来加 description/foreground 等会被吃掉)(red-team)。

**Context:** backend/apps/settings/widgets.py ColorOptionListWidget.get_context + templates/widgets/color_option_list.html sync()。

**Effort:** S
**Priority:** P2
**Depends on:** None

### 站点设置加载统一入口

**What:** 抽 loadSiteOptionSettings() composable(拉 /api/settings/ 并调 setPrioritiesFromSettings/setStatusesFromSettings,带去重缓存),或登录后全局加载一次。

**Why:** 成对调用在 3 个页面重复,新页面漏调会静默渲染静态默认色(maintainability)。

**Context:** frontend/app/pages/app/issues/index.vue:1023、issues/[id].vue:1492、projects/[id].vue:537。

**Effort:** S
**Priority:** P3
**Depends on:** None

## Frontend / 结构清理

### useStatus/usePriority 抽通用工厂

**What:** 抽 createConfiguredOptions(defaults) 泛型工厂,两个 composable 实例化后各自补特有函数。

**Why:** 两文件是 ~50 行结构性复制(双格式解析/单例/取值器),行为修正需双写(maintainability)。

**Context:** frontend/app/composables/useStatus.ts、usePriority.ts,注释互相引用「同 usePriority」。

**Effort:** M
**Priority:** P3
**Depends on:** None

### markdown 共享样式抽全局

**What:** MarkdownView/MarkdownEditor 重复的 mention/file-card/task-list 样式段抽到 assets/css(统一 .markdown-body 类),组件内只留特有覆盖。

**Why:** ~140 行样式靠人工双向同步,已出现字面量重复,必然漂移(maintainability)。

**Context:** frontend/app/components/MarkdownView.vue:53 注释自述「保持同步」。

**Effort:** M
**Priority:** P3
**Depends on:** None

### modal 样式收敛

**What:** modal-form/header/body/footer 样式提升到 main.css 或封装 AppModal 组件,删除各页副本。

**Why:** IssueComments.vue 是全应用第 8 份副本,一致性靠复制维护(maintainability)。

**Context:** `grep -rln modal-form frontend/app` 8 个文件。

**Effort:** M
**Priority:** P3
**Depends on:** None

### USelect 空值哨兵统一

**What:** 封装支持空值的 USelect 包装(或 useNullableSelect 辅助),统一哨兵常量。

**Why:** 同一套映射在 5 处复制且各自发明哨兵('_all'/'_none'/'_default'),易错难改(maintainability)。

**Context:** kpi/index.vue:437、permissions.vue、profile.vue、issues/index.vue、issues/[id].vue。

**Effort:** S
**Priority:** P3
**Depends on:** None

### 表格行着色支持非 ASCII 档位值

**What:** priorityRowCss 用 CSS.escape 构造选择器,替换 /^[\w-]+$/ 白名单。

**Why:** 中文等自定义档位值在表格静默失去行着色,而看板照常着色,同一配置两视图行为不一致;档位值已锁定后基本 moot,留作记录(checklist/maintainability/adversarial 一致)。

**Context:** frontend/app/pages/app/issues/index.vue:403。

**Effort:** S
**Priority:** P4
**Depends on:** None

## Backend / 记录项

### IssueComment 冗余索引(仅记录)

**What:** issue FK 隐式索引与 Meta 复合索引 (issue, created_at) 前导列重叠,写放大无读收益。

**Why:** 表新且小,影响可忽略;按仓库规则 Django 生成的迁移不改,如要处理需新建迁移设 db_index=False(data-migration)。

**Context:** backend/apps/issues/migrations/0014_issuecomment.py + models.py Meta.indexes。

**Effort:** S
**Priority:** P4
**Depends on:** None

## Completed
