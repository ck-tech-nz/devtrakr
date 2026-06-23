# 状态单元格 UX 改进设计

**日期**: 2026-06-24
**作者**: CK + Claude
**状态**: 设计 — 待评审

---

## 1. 目标

围绕「状态」交互做三处独立的 UX 改进,均为前端为主:

1. 详情页把状态改为「进行中」且当前无负责人时,弹窗询问是否同时把负责人设为自己。
2. 把「接单」文案改为「认领」。
3. 列表状态徽章去掉「点击筛选处理人」行为,消除与操作按钮的点击冲突。

后端无行为变更(仅可选地同步一处 Django-admin 展示用枚举标签)。

---

## 2. 范围

**做**
- 详情页 `进行中` 自动认领弹窗
- `接单` → `认领` 文案替换(前端两处 + 可选后端枚举标签一处)
- 列表状态徽章去掉筛选点击 + 清理相关死代码

**显式不做**
- 不改动列表页顶部的「负责人」筛选下拉(保留,仍可按负责人筛选)
- 不引入 `IssueAssignment` 审计记录到详情页 PATCH 路径(详情页历来用通用 PATCH 直改 `status`/`assignee`,本次保持一致,不扩大范围)
- 不改动看板 `IssueCard.vue`(它从未接 `filter-assignee`)
- 不改动列表页 `认领`(原接单)按钮的后端 `claim` 工作流

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

### 3.2 Item 2 — 「接单」→「认领」

- 列表状态单元格按钮文案: [`frontend/app/components/issue/StatusCell.vue`](../../../frontend/app/components/issue/StatusCell.vue) 第 83 行 `接单` → `认领`
- 详情页审计日志标签映射: `[id].vue` 第 1694 行 `claim: '接单'` → `claim: '认领'`
- 可选(为内部一致性): 后端 `apps/issues/models.py` 的 `AssignmentAction.CLAIM = 'claim', '接单'` → `'认领'`。该标签仅 Django admin / `get_action_display()` 用,SPA 不读;改动会经 `makemigrations` 生成一条 no-op `AlterField` 迁移。**默认包含此项**;如不希望动后端,去掉即可。
- 存储值 `'claim'` 保持不变(锁定值,前端按值映射文案)。

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
- 后端: 无行为变更,现有测试不受影响(若改 TextChoices 标签,仅为展示,无需新增测试)。

---

## 6. 风险与开放问题

- **详情页 PATCH 不写审计**: Item 1「设为我处理」走通用 PATCH,不产生 `IssueAssignment` 记录——与详情页现状一致(详情页历来直改 assignee/status 不写审计)。本次不修正该既有差异,以免扩大范围;如需审计可作为后续独立任务。
- **非开发者自我认领**: 详情页负责人下拉仅列「开发者」组,但本弹窗的「设为我处理」不加该门槛(认领本质是「我来处理」的动作,类似列表 `claim` 按项目成员而非开发者组判定)。`assigneeItems` 的回显兜底保证显示正常。如需限制为开发者组成员才弹窗,可后续收紧。
