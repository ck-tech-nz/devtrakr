# 状态单元格 UX 改进设计

**日期**: 2026-06-24
**作者**: CK + Claude
**状态**: 设计 — 待评审

---

## 1. 目标

围绕详情页/列表的 UX 做五处独立改进,均为前端:

1. 详情页把状态改为「进行中」且当前无负责人时,弹窗询问是否同时把负责人设为自己。
2. 把「接单」文案改为「认领」。
3. 列表状态徽章去掉「点击筛选处理人」行为,消除与操作按钮的点击冲突。
4. 详情页侧栏新增/改造「变更历史」卡(置于「分配流转」之下),逐行显示修改人、修改时间、变更字段名。
5. 详情页侧栏「分配流转」「分析记录」「关联仓库」三张卡默认收起。

后端无行为变更(仅可选地同步一处 Django-admin 展示用枚举标签)。变更历史复用既有的
`GET /api/issues/{id}/history/` 端点,无需新增后端。

---

## 2. 范围

**做**
- 详情页 `进行中` 自动认领弹窗
- `接单` → `认领` 文案替换(前端两处 + 可选后端枚举标签一处)
- 列表状态徽章去掉筛选点击 + 清理相关死代码
- 修复并改造既有「更新历史」卡为「变更历史」卡(修复其从不显示的 bug,移到分配流转之下,内容改为仅字段名)
- 「分配流转」「分析记录」「关联仓库」三卡加可收起头部,默认收起

**显式不做**
- 不改动列表页顶部的「负责人」筛选下拉(保留,仍可按负责人筛选)
- 不引入 `IssueAssignment` 审计记录到详情页 PATCH 路径(详情页历来用通用 PATCH 直改 `status`/`assignee`,本次保持一致,不扩大范围)
- 不改动看板 `IssueCard.vue`(它从未接 `filter-assignee`)
- 不改动列表页 `认领`(原接单)按钮的后端 `claim` 工作流
- 不新增第二张历史卡(改造既有的,避免重复)
- 不改动后端 `GET /api/issues/{id}/history/` 的响应结构与权限(仍仅管理员)
- 不改动其它侧栏卡(关联附件 / 关联 Issues / 关联 PR / 外部来源 / AI 分析)的默认展开状态

---

## 3. 详细设计

### 3.1 Item 1 — 「进行中」自动认领弹窗(详情页)

**触发条件**: 在 `handleStatusClick`([`frontend/app/pages/app/issues/[id].vue`](../../../frontend/app/pages/app/issues/%5Bid%5D.vue) 第 1438 行)中,当
- 目标状态 `=== ISSUE_STATUS.IN_PROGRESS`(`进行中`),且
- 当前问题无负责人(`form.value.assignee === '_none'`)

时,不立即保存,而是打开确认弹窗。其余状态变更(待确认/已解决/已关闭/未计划/待分配)行为不变。已有的「已关闭 → 检查未关闭 GitHub issue」分支在前、互不影响。

**弹窗内容**(`UModal`):
- 文案: 「该问题还没有负责人,要同时把负责人设为你自己吗?」
- 主按钮「是,由我处理」→ 一次 PATCH `{ status: '进行中', assignee: selfUserId }`
- 次按钮「仅修改状态」→ PATCH `{ status: '进行中' }`(负责人保持为空)
- 关闭 / 点遮罩 / 取消 → 不做任何变更(安全默认)

**实现要点**:
- `selfUserId` 已在第 432 行计算(`Number(user.value?.id ?? 0)`),直接复用。
- 复用现有 PATCH + 重新拉取 + `populateForm` 的保存模式(同 `autoSave`)。新增一个能一次提交多个字段的小函数(如 `saveStatusWithAssignee`),或扩展现有保存逻辑接收字段对象。
- 负责人下拉 `assigneeItems` 已有「当前负责人不在开发者组也保留选项以回显」的兜底,因此即使当前用户不在开发者组,设为自己后也能正确回显,无需额外门槛判断。
- 新增响应式状态: `showSelfAssignPrompt: Ref<boolean>` 与 `pendingStatus: Ref<string>`(承载待确认的目标状态)。
- 需在详情页引入 `ISSUE_STATUS` 常量(`~/constants/issueStatus`)以替代字面量 `'进行中'`。

**状态流**:
```
点击「进行中」胶囊
  └─ assignee 为空?
        ├─ 否 → 直接 updateField('status','进行中')(原行为)
        └─ 是 → 打开弹窗
                 ├─ 「是,由我处理」 → PATCH {status:'进行中', assignee:self}
                 ├─ 「仅修改状态」   → PATCH {status:'进行中'}
                 └─ 取消/关闭        → 无变更
```

### 3.2 Item 2 — 「接单」→「认领」(消除该词所有用户可见处)

用户诉求是「不要用『接单』这个词」,因此替换**所有用户可见**的出现处(存储值 `'claim'` 保持不变):

**前端**
- `frontend/app/components/issue/StatusCell.vue` 第 83 行按钮文案 `接单` → `认领`
- `[id].vue` 第 1694 行审计标签映射 `claim: '接单'` → `claim: '认领'`
- `frontend/app/pages/app/issues/index.vue` 第 766 行创建后 toast `已创建，等待人工接单` → `已创建，等待人工认领`

**后端**(`apps/issues/services.py` — 用户可见的错误信息与活动详情)
- 第 186 行错误 `只有「待分配」可被接单,当前 …` → `…可被认领…`
- 第 189 行错误 `仅项目成员可接单` → `仅项目成员可认领`
- 第 205 行活动详情 `f"{actor…} 接单"` → `f"{actor…} 认领"`(仅影响新生成的活动记录,历史记录不变)
- 第 218 行错误 `仅当前负责人可确认接单` → `仅当前负责人可确认认领`
- 第 233 行活动详情 `确认接单` → `确认认领`
- 第 183 行 docstring(内部)一并改为 `认领`,保持一致

**后端枚举 + 迁移**
- `apps/issues/models.py` 第 36 行 `AssignmentAction.CLAIM = 'claim', '接单'` → `'认领'`(仅 Django admin / `get_action_display()` 用)
- 经 `makemigrations issues` 生成一条新的 `AlterField` 迁移(改 `IssueAssignment.action` 的 choices 标签);**不可手改既有 0010 迁移**(其中 `("claim","接单")` 是冻结的历史,保持原样)

**测试 docstring**(可选,内部)
- `tests/test_assignment_api.py` 第 10、22 行 docstring 里的「接单」改为「认领」(仅注释,无断言依赖)

**不改**: `dashboardLayout.ts` 的「直接单测」是误匹配(子串),保持原样。

### 3.3 Item 3 — 去掉状态徽章的筛选点击

**`StatusCell.vue` 清理**:
- 删除 emit 声明 `(e: 'filter-assignee'): void`(第 24 行)
- 删除 `canFilterAssignee` 计算属性(第 33 行)与 `onFilterAssignee` 函数(第 34–36 行)
- 三处 `UBadge` 去掉 `@click.stop="onFilterAssignee"`、`cursor-pointer hover:opacity-80` 动态 class、以及 `title`(筛选提示)绑定:
  - 「待确认/进行中: 别人的」分支(约 110–118 行)
  - 「进行中: 自己的」分支(约 128–136 行)
  - 「已解决/已发布/已关闭/未计划」分支(约 144–154 行)
- 徽章变为纯展示(不可点击);只有操作按钮(认领/接受/转单/指派/↪)响应点击,点击冲突消除。

**`index.vue` 清理**:
- 删除第 340 行 `@filter-assignee="filterByAssignee(row.original)"`
- 删除现已无引用的 `filterByAssignee` 函数(第 478 行)
- 顶部「负责人」筛选下拉(第 25 行)保留,按负责人筛选能力不丢失。

**`IssueCard.vue`**: 无需改动(从未接 `filter-assignee`)。

### 3.4 Item 4 — 「变更历史」卡(修复并改造既有「更新历史」卡)

**现状(bug)**: `[id].vue` 第 612–654 行已有「更新历史」卡,但 `loadHistory()` 仅在 `toggleHistory()`(点击卡头)里调用,而卡头被 `v-if="isManager && (historyLoading || history.length)"` 挡住——历史未加载前卡不渲染,卡不渲染就无法点击加载,形成死循环,该卡**从不显示**。后端 `GET /api/issues/{id}/history/`(`IssueHistoryView`,仅管理员)本身正常,返回:

```json
[{ "id": 1, "type": "~", "date": "...", "user": "...", "changes": [{ "field": "status", "label": "状态", "before": "进行中", "after": "已解决" }] }]
```

**改造方案**:
- **位置**: 从「分配流转」之上移到其**之下**(侧栏最末)。
- **标题**: 「更新历史」→「变更历史」。
- **可见性修复**: `v-if` 改为仅 `isManager`(卡头恒渲染);并在 `onMounted` 中,当 `isManager` 时调用 `loadHistory()`(因默认展开,进页即加载)。`toggleHistory` 保留(折叠/展开;展开且未加载时兜底再拉)。
- **默认状态**: 展开(`showHistory = ref(true)`)。
- **每行内容(仅字段名)**: 用一个 `changeSummary(entry)` 计算:
  - `type === '+'` 或首个变更 `field === '_created'` → 「创建」
  - `type === '-'` → 「删除」
  - 否则 → `entry.changes.map(c => c.label).join('、')`(如「状态、描述、负责人」);若为空兜底「更新」
- **每行展示**: 左 `修改人`(`entry.user || '系统'`)、右 `修改时间`(`formatRelative(entry.date)`,`title` 为完整时间),下一行 `changeSummary`。保留左侧 `border-l-2` 颜色按 `type` 区分(创建绿/删除红/更新灰)。
- **移除**: 原来逐字段 before→after 的明细块(645–649 行那段),以及 `_created` 的特殊分支判断(并入 `changeSummary`)。
- 仍仅管理员可见(后端 403 兜底);非管理员不渲染该卡。

### 3.5 Item 5 — 三张侧栏卡默认收起

为「分配流转」「分析记录」「关联仓库」三卡加可收起头部,复用「变更历史」卡的头部范式
(`<button class="flex items-center justify-between w-full">` + `<h3>` + `chevron` 图标),
body 用 `v-if="showXxx"` 包裹,默认收起。

| 卡片 | 模板位置 | 折叠状态 ref(默认值) | 包裹的 body |
|---|---|---|---|
| 分析记录 | 第 291–316 行,`<h3>`@292 | `showAnalysis = ref(false)` | `.space-y-4`(293–315) |
| 关联仓库 | 第 358–400 行,`<h3>`@359 | `showRepo = ref(false)` | `.space-y-2`(361–389) + 仓库链接块(391–399) |
| 分配流转 | 第 657–668 行,`<h3>`@658 | `showAssignments = ref(false)` | `<ol>`(659–667) |

- 折叠用内联 `@click="showXxx = !showXxx"` 即可,无需额外函数(不像历史卡需懒加载)。
- 各卡原有外层 `v-if`(如分配流转的 `issue?.assignments?.length`)保留。
- 收起态仅显示标题 + chevron(本次不做收起态摘要;如需「关联仓库显示当前仓库名/分配流转显示条数」可后续加)。

---

## 4. 后端影响

- Item 1: 复用现有 `PATCH /api/issues/{id}/`,接受 `{status, assignee}` 组合,无新增端点、无行为变更。
- Item 2(可选项): 仅 `AssignmentAction.CLAIM` 展示标签,生成 no-op 迁移;不影响序列化输出与既有逻辑。
- Item 3: 纯前端。

---

## 5. 测试

- 前端类型检查: `npx nuxi typecheck`
- 手动验证(`bot` 账号,`/qa` 或 `/browse`):
  1. 无负责人的问题点「进行中」→ 弹窗出现;「是,由我处理」后状态为进行中且负责人为我;「仅修改状态」后状态为进行中、负责人仍为空;取消后无变更。
  2. 已有负责人的问题点「进行中」→ 不弹窗,直接生效。
  3. 列表/详情中原「接单」文案均显示为「认领」。
  4. 列表状态徽章点击不再触发按负责人筛选;操作按钮点击正常;顶部负责人下拉筛选仍可用。
  5. 以管理员账号打开任一问题详情:侧栏底部「变更历史」卡默认展开并显示历史(进页即加载);每行有修改人、相对时间、变更字段名(如「状态、描述」),创建行显示「创建」。
  6. 「分配流转」「分析记录」「关联仓库」三卡默认收起,点击卡头可展开/收起;展开后内容(含可编辑字段、仓库选择器)正常工作。
  7. 以非管理员账号打开详情:不出现「变更历史」卡(后端 403 兜底)。
- 后端: 无行为变更,现有测试不受影响(若改 TextChoices 标签,仅为展示,无需新增测试)。变更历史复用既有端点,无新增后端测试。

---

## 6. 风险与开放问题

- **详情页 PATCH 不写审计**: Item 1「设为我处理」走通用 PATCH,不产生 `IssueAssignment` 记录——与详情页现状一致(详情页历来直改 assignee/status 不写审计)。本次不修正该既有差异,以免扩大范围;如需审计可作为后续独立任务。
- **非开发者自我认领**: 详情页负责人下拉仅列「开发者」组,但本弹窗的「设为我处理」不加该门槛(认领本质是「我来处理」的动作,类似列表 `claim` 按项目成员而非开发者组判定)。`assigneeItems` 的回显兜底保证显示正常。如需限制为开发者组成员才弹窗,可后续收紧。
- **变更历史仅管理员可见**: 沿用既有后端 `_is_manager`(超级用户或「管理员」组)。普通成员看不到该卡;若未来希望负责人/创建人也能看自己问题的变更历史,需放宽后端权限,属独立改动。
- **变更历史进页即加载**: 默认展开 → 管理员每次打开详情都会多一次 `/history/` 请求。可接受(仅管理员、单次、量小);若量大可改为默认收起 + 懒加载。
- **字段名依赖后端 `FIELD_LABELS`**: 变更内容只展示 `change.label`(后端映射的中文字段名);若出现未映射字段,后端已兜底回退为原始 `field` 名,前端无需处理。
